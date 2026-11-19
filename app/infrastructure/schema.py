"""Creación de tablas y compatibilidad con bases creadas en versiones anteriores."""

from sqlalchemy import inspect, text

from .database import Base, engine
from . import models  # noqa: F401 - registra los modelos en metadata


def ensure_schema() -> None:
    inspector = inspect(engine)
    if inspector.has_table("apis") and "interval_minutes" not in {column["name"] for column in inspector.get_columns("apis")}:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE apis ADD COLUMN interval_minutes INTEGER NOT NULL DEFAULT 5"))
    if inspector.has_table("monitoreos"):
        monitor_columns = {column["name"] for column in inspector.get_columns("monitoreos")}
        with engine.begin() as connection:
            if "target_url" not in monitor_columns:
                connection.execute(text("ALTER TABLE monitoreos ADD COLUMN target_url VARCHAR(2048)"))
            if "expected_status" not in monitor_columns:
                connection.execute(text("ALTER TABLE monitoreos ADD COLUMN expected_status INTEGER NOT NULL DEFAULT 200"))
    Base.metadata.create_all(bind=engine)
