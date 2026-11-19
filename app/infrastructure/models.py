from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow():
    return datetime.now(timezone.utc)


class ApiEndpoint(Base):
    __tablename__ = "apis"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    expected_status: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    monitors: Mapped[list["MonitorRun"]] = relationship(back_populates="api", cascade="all, delete-orphan")


class Rule(Base):
    __tablename__ = "reglas"

    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    definition: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class MonitorRun(Base):
    __tablename__ = "monitoreos"

    id: Mapped[int] = mapped_column(primary_key=True)
    api_id: Mapped[int] = mapped_column(ForeignKey("apis.id"), nullable=False, index=True)
    target_url: Mapped[str | None] = mapped_column(String(2048))
    expected_status: Mapped[int] = mapped_column(Integer, nullable=False, default=200)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    status_code: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    error_type: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    api: Mapped[ApiEndpoint] = relationship(back_populates="monitors")
    diagnosis: Mapped["Diagnosis | None"] = relationship(back_populates="monitor", cascade="all, delete-orphan", uselist=False)


class Diagnosis(Base):
    __tablename__ = "diagnosticos"

    id: Mapped[int] = mapped_column(primary_key=True)
    monitor_id: Mapped[int] = mapped_column(ForeignKey("monitoreos.id"), unique=True, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="informativa", nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    facts: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    recommendations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    monitor: Mapped[MonitorRun] = relationship(back_populates="diagnosis")
    fired_rules: Mapped[list["DiagnosisRule"]] = relationship(back_populates="diagnosis", cascade="all, delete-orphan")
    recommendation_rows: Mapped[list["Recommendation"]] = relationship(back_populates="diagnosis", cascade="all, delete-orphan")


class Recommendation(Base):
    __tablename__ = "recomendaciones"

    id: Mapped[int] = mapped_column(primary_key=True)
    diagnosis_id: Mapped[int] = mapped_column(ForeignKey("diagnosticos.id", ondelete="CASCADE"), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    diagnosis: Mapped[Diagnosis] = relationship(back_populates="recommendation_rows")


class DiagnosisRule(Base):
    __tablename__ = "diagnostico_reglas"

    diagnosis_id: Mapped[int] = mapped_column(ForeignKey("diagnosticos.id"), primary_key=True)
    rule_id: Mapped[str] = mapped_column(ForeignKey("reglas.id"), primary_key=True)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    diagnosis: Mapped[Diagnosis] = relationship(back_populates="fired_rules")
    rule: Mapped[Rule] = relationship()
