"""Caso de uso: tomar una medición, inferir y guardar un diagnóstico explicable."""

import os

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..domain.monitoring import count_consecutive_failures
from ..domain.rules import infer
from ..infrastructure.http_monitor import check_api
from ..infrastructure.knowledge import active_rules
from ..infrastructure.models import ApiEndpoint, Diagnosis, DiagnosisRule, MonitorRun, Recommendation


def serialize_monitor(monitor: MonitorRun) -> dict:
    diagnosis = monitor.diagnosis
    return {
        "id": monitor.id, "api_id": monitor.api_id, "api_name": monitor.api.name,
        "url": monitor.api.url, "checked_at": monitor.checked_at,
        "target_url": monitor.target_url or monitor.api.url, "expected_status": monitor.expected_status,
        "status_code": monitor.status_code, "latency_ms": monitor.latency_ms,
        "error_type": monitor.error_type, "error_message": monitor.error_message,
        "severity": diagnosis.severity if diagnosis else "informativa",
        "summary": diagnosis.summary if diagnosis else "Sin diagnóstico",
        "facts": diagnosis.facts if diagnosis else {},
        "recommendations": diagnosis.recommendations if diagnosis else [],
        "rules": [{"id": fired.rule_id, "explanation": fired.explanation} for fired in diagnosis.fired_rules] if diagnosis else [],
    }


def run_monitor(api: ApiEndpoint, db: Session) -> dict:
    measurement = check_api(api.url)
    monitor = MonitorRun(api_id=api.id, target_url=api.url, expected_status=api.expected_status, **measurement)
    db.add(monitor)
    db.flush()
    previous = db.scalars(select(MonitorRun).where(
        MonitorRun.api_id == api.id, MonitorRun.id != monitor.id,
    ).order_by(desc(MonitorRun.checked_at), desc(MonitorRun.id)).limit(2)).all()

    consecutive_failures = count_consecutive_failures([monitor, *previous], api.url)

    facts = {
        "api_id": api.id,
        "status_code": monitor.status_code,
        "expected_status": api.expected_status,
        "latency_ms": monitor.latency_ms,
        "slow_threshold_ms": float(os.getenv("SLOW_RESPONSE_MS", "1500")),
        "error_type": monitor.error_type,
        "consecutive_failures": consecutive_failures,
    }
    result = infer(facts, active_rules(db))
    diagnosis = Diagnosis(
        monitor_id=monitor.id,
        severity=result.severity,
        summary=result.summary,
        facts=result.facts,
        recommendations=result.recommendations,
    )
    db.add(diagnosis)
    db.flush()
    for position, recommendation in enumerate(result.recommendations):
        db.add(Recommendation(diagnosis_id=diagnosis.id, content=recommendation, position=position))
    for rule in result.fired_rules:
        db.add(DiagnosisRule(
            diagnosis_id=diagnosis.id,
            rule_id=rule.id,
            explanation=f"{rule.id}: {rule.description}",
        ))
    db.commit()
    db.refresh(monitor)
    return serialize_monitor(monitor)
