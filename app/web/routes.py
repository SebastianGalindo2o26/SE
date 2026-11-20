import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, joinedload

from ..application.authentication import configure_authentication
from ..application.monitoring import run_monitor, serialize_monitor as _serialize
from ..infrastructure.credentials import CredentialError
from ..infrastructure.database import get_db
from ..infrastructure.models import ApiEndpoint, Diagnosis, MonitorRun, Rule
from ..infrastructure.http_monitor import UnsafeDestination, validate_destination
from .security import CSRF_COOKIE, csrf_for_page, require_csrf

APP_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))
router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    apis = db.scalars(select(ApiEndpoint).options(joinedload(ApiEndpoint.credential)).where(ApiEndpoint.active.is_(True)).order_by(ApiEndpoint.id)).all()
    inactive_apis = db.scalars(select(ApiEndpoint).where(ApiEndpoint.active.is_(False)).order_by(ApiEndpoint.id)).all()
    recent = db.scalars(select(MonitorRun).options(joinedload(MonitorRun.api), joinedload(MonitorRun.diagnosis).joinedload(Diagnosis.fired_rules)).order_by(desc(MonitorRun.checked_at), desc(MonitorRun.id)).limit(25)).unique().all()
    serialized = [_serialize(run) for run in recent]
    latest_by_api = {}
    for api in apis:
        latest = db.execute(select(MonitorRun).options(joinedload(MonitorRun.api), joinedload(MonitorRun.diagnosis).joinedload(Diagnosis.fired_rules)).where(MonitorRun.api_id == api.id).order_by(desc(MonitorRun.checked_at), desc(MonitorRun.id)).limit(1)).unique().scalar_one_or_none()
        latest_by_api[api.id] = _serialize(latest) if latest else None
    total = db.scalar(select(func.count(MonitorRun.id))) or 0
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today = db.scalar(select(func.count(MonitorRun.id)).where(MonitorRun.checked_at >= today_start)) or 0
    successful = sum(1 for item in serialized if item["status_code"] == item["expected_status"])
    availability = round(successful / len(serialized) * 100) if serialized else 0
    critical = sum(1 for item in serialized if item["severity"] == "alta")
    recent_points = list(reversed(serialized[-12:]))
    availability_points = " ".join(f"{index * 10},{8 if item['status_code'] == item['expected_status'] else 28}" for index, item in enumerate(recent_points))
    csrf_token, set_cookie = csrf_for_page(request)
    response = templates.TemplateResponse(request, "index.html", {"apis": apis, "inactive_apis": inactive_apis, "runs": serialized, "latest_by_api": latest_by_api, "availability_points": availability_points, "total_checks": total, "checks_today": today, "availability": availability, "critical": critical, "rule_count": db.scalar(select(func.count(Rule.id)).where(Rule.active.is_(True))) or 0, "error": request.query_params.get("error"), "csrf_token": csrf_token})
    if set_cookie:
        response.set_cookie(CSRF_COOKIE, csrf_token, httponly=True, samesite="strict", secure=request.url.scheme == "https")
    return response


@router.post("/apis")
def create_api(name: str = Form(...), url: str = Form(...), expected_status: int = Form(200), interval_minutes: int = Form(5), auth_type: str = Form("none"), auth_header_name: str = Form(""), auth_username: str = Form(""), auth_secret: str = Form(""), db: Session = Depends(get_db), _: None = Depends(require_csrf)):
    name = name.strip()
    url = url.strip()
    if not name or len(name) > 120 or expected_status < 100 or expected_status > 599 or interval_minutes not in (1, 5, 10):
        return RedirectResponse("/?error=" + quote("Revisa el nombre, código esperado o intervalo de monitoreo."), status_code=303)
    try:
        validate_destination(url)
    except UnsafeDestination as exc:
        return RedirectResponse("/?error=" + quote(str(exc)), status_code=303)
    api = ApiEndpoint(name=name, url=url, expected_status=expected_status, interval_minutes=interval_minutes)
    try:
        configure_authentication(api, auth_type, auth_header_name, auth_username, auth_secret)
    except CredentialError as exc:
        return RedirectResponse("/?error=" + quote(str(exc)), status_code=303)
    db.add(api)
    db.commit()
    return RedirectResponse("/", status_code=303)


@router.post("/apis/{api_id}/update")
def update_api(api_id: int, name: str = Form(...), url: str = Form(...), expected_status: int = Form(200), interval_minutes: int = Form(5), auth_type: str | None = Form(None), auth_header_name: str = Form(""), auth_username: str = Form(""), auth_secret: str = Form(""), db: Session = Depends(get_db), _: None = Depends(require_csrf)):
    api = db.get(ApiEndpoint, api_id)
    if api is None:
        raise HTTPException(status_code=404, detail="API no encontrada.")
    name, url = name.strip(), url.strip()
    if not name or len(name) > 120 or not 100 <= expected_status <= 599 or interval_minutes not in (1, 5, 10):
        return RedirectResponse("/?error=" + quote("Revisa los datos de la API."), status_code=303)
    try:
        validate_destination(url)
    except UnsafeDestination as exc:
        return RedirectResponse("/?error=" + quote(str(exc)), status_code=303)
    api.name, api.url, api.expected_status, api.interval_minutes = name, url, expected_status, interval_minutes
    if auth_type is not None:
        try:
            configure_authentication(api, auth_type, auth_header_name, auth_username, auth_secret)
        except CredentialError as exc:
            db.rollback()
            return RedirectResponse("/?error=" + quote(str(exc)), status_code=303)
    db.commit()
    return RedirectResponse("/", status_code=303)


@router.post("/apis/{api_id}/monitor")
def monitor_api(api_id: int, db: Session = Depends(get_db), _: None = Depends(require_csrf)):
    api = db.get(ApiEndpoint, api_id)
    if api is None or not api.active:
        raise HTTPException(status_code=404, detail="API no encontrada o desactivada.")
    try:
        run_monitor(api, db)
    except (UnsafeDestination, CredentialError) as exc:
        return RedirectResponse("/?error=" + quote(str(exc)), status_code=303)
    return RedirectResponse("/", status_code=303)


@router.post("/apis/{api_id}/deactivate")
def deactivate_api(api_id: int, db: Session = Depends(get_db), _: None = Depends(require_csrf)):
    api = db.get(ApiEndpoint, api_id)
    if api is None:
        raise HTTPException(status_code=404, detail="API no encontrada.")
    api.active = False
    db.commit()
    return RedirectResponse("/", status_code=303)


@router.post("/apis/{api_id}/activate")
def activate_api(api_id: int, db: Session = Depends(get_db), _: None = Depends(require_csrf)):
    api = db.get(ApiEndpoint, api_id)
    if api is None:
        raise HTTPException(status_code=404, detail="API no encontrada.")
    api.active = True
    db.commit()
    return RedirectResponse("/#services", status_code=303)


@router.get("/api/apis")
def list_apis(db: Session = Depends(get_db)):
    return [{"id": a.id, "name": a.name, "url": a.url, "expected_status": a.expected_status, "interval_minutes": a.interval_minutes, "active": a.active, "auth_type": a.credential.auth_type if a.credential else "none"} for a in db.scalars(select(ApiEndpoint).options(joinedload(ApiEndpoint.credential)).order_by(ApiEndpoint.id)).all()]


@router.get("/api/rules")
def list_rules(db: Session = Depends(get_db)):
    rows = db.scalars(select(Rule).order_by(Rule.id)).all()
    return [{"id": row.id, "name": row.name, "description": row.description, "priority": row.priority, "active": row.active, "definition": row.definition} for row in rows]


@router.get("/api/history")
def history(limit: int = 50, db: Session = Depends(get_db)):
    if not 1 <= limit <= 200:
        raise HTTPException(status_code=422, detail="limit debe estar entre 1 y 200.")
    runs = db.scalars(select(MonitorRun).options(joinedload(MonitorRun.api), joinedload(MonitorRun.diagnosis).joinedload(Diagnosis.fired_rules)).order_by(desc(MonitorRun.checked_at)).limit(limit)).unique().all()
    return [_serialize(run) for run in runs]


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/demo/status/{status_code}")
def demo_status(status_code: int):
    """Controlled endpoint for classroom scenarios; it never writes application data."""
    if not 100 <= status_code <= 599:
        raise HTTPException(status_code=422, detail="El código HTTP debe estar entre 100 y 599.")
    return JSONResponse(status_code=status_code, content={"demo": True, "status_code": status_code})


@router.get("/demo/auth")
def demo_auth(x_demo_key: str | None = Header(default=None)):
    """Endpoint local de clase para comprobar el envío de una API key."""
    if x_demo_key != "sentinel-demo":
        return JSONResponse(status_code=401, content={"demo": True, "authorized": False})
    return {"demo": True, "authorized": True}


@router.get("/demo/delay/{milliseconds}")
def demo_delay(milliseconds: int):
    """Local endpoint to demonstrate latency and timeout rules."""
    if not 0 <= milliseconds <= 30000:
        raise HTTPException(status_code=422, detail="El retraso debe estar entre 0 y 30000 milisegundos.")
    time.sleep(milliseconds / 1000)
    return {"demo": True, "delay_ms": milliseconds}
