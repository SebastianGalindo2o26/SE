"""Composición de FastAPI, persistencia y monitoreo periódico."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .infrastructure.database import SessionLocal
from .infrastructure.knowledge import seed_rules
from .infrastructure.schema import ensure_schema
from .infrastructure.scheduler import monitor_due_apis
from .web.routes import router

WEB_DIR = Path(__file__).resolve().parent / "web"
scheduler = BackgroundScheduler(timezone="UTC")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_schema()
    with SessionLocal() as db:
        seed_rules(db)
    scheduler.add_job(monitor_due_apis, "interval", minutes=1, id="monitor-due-apis", replace_existing=True, max_instances=1)
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Sistema Experto para Monitoreo y Diagnóstico de APIs REST", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=[host.strip() for host in os.getenv("ALLOWED_APP_HOSTS", "localhost,127.0.0.1").split(",") if host.strip()])
app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")
app.include_router(router)
