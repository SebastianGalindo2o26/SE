"""Adaptador de APScheduler para ejecutar el caso de uso de monitoreo."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from ..application.monitoring import run_monitor
from .database import SessionLocal
from .models import ApiEndpoint, MonitorRun

logger = logging.getLogger(__name__)


def monitor_due_apis() -> None:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        apis = db.scalars(select(ApiEndpoint).where(ApiEndpoint.active.is_(True))).all()
        for api in apis:
            last = db.scalar(select(func.max(MonitorRun.checked_at)).where(MonitorRun.api_id == api.id))
            if last is not None:
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                if now - last < timedelta(minutes=api.interval_minutes):
                    continue
            try:
                run_monitor(api, db)
            except Exception:
                db.rollback()
                logger.exception("Scheduled monitoring failed for API %s", api.id)
    finally:
        db.close()
