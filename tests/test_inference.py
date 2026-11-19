from app.domain.rules import RULES, infer
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base
from app.infrastructure.scheduler import monitor_due_apis
from app.application.monitoring import run_monitor
from app.infrastructure.models import ApiEndpoint, Diagnosis, DiagnosisRule, MonitorRun, Rule


def facts(status, latency=300, failures=0, error=None):
    return {"api_id": 1, "status_code": status, "expected_status": 200, "latency_ms": latency,
            "slow_threshold_ms": 1500, "error_type": error, "consecutive_failures": failures}


def test_healthy_response_is_explained():
    result = infer(facts(200))
    assert [rule.id for rule in result.fired_rules] == ["R01"]
    assert result.severity == "normal"


def test_single_500_does_not_become_persistent():
    result = infer(facts(500))
    assert {rule.id for rule in result.fired_rules} == {"R02"}
    assert result.severity == "media"


def test_three_500_responses_chain_to_high_priority_and_recommendation():
    result = infer(facts(500, failures=3))
    assert {rule.id for rule in result.fired_rules} == {"R02", "R12", "R13", "R15"}
    assert result.severity == "alta"
    assert any("guardia" in recommendation for recommendation in result.recommendations)


def test_slow_expected_response_activates_performance_rule():
    result = infer(facts(200, latency=2800))
    assert {rule.id for rule in result.fired_rules} == {"R10"}
    assert result.severity == "baja"


def test_connection_timeout_activates_connection_rule():
    result = infer(facts(None, error="timeout"))
    assert {rule.id for rule in result.fired_rules} == {"R11"}


def test_401_recommends_reviewing_authentication():
    result = infer(facts(401))
    assert {rule.id for rule in result.fired_rules} == {"R06"}
    assert any("credenciales" in recommendation for recommendation in result.recommendations)


def test_three_503_responses_escalate_service_unavailability():
    result = infer(facts(503, failures=3))
    assert {rule.id for rule in result.fired_rules} == {"R04", "R12", "R14", "R15"}
    assert result.severity == "alta"


def test_endpoint_expected_404_is_treated_as_healthy():
    expected = facts(404)
    expected["expected_status"] = 404
    result = infer(expected)
    assert [rule.id for rule in result.fired_rules] == ["R01"]
    assert result.severity == "normal"


def test_rule_set_has_fifteen_unique_ids():
    assert len(RULES) == 15
    assert len({rule.id for rule in RULES}) == 15


def test_disabling_all_rules_does_not_reenable_defaults():
    result = infer(facts(500), [])
    assert result.fired_rules == []
    assert result.severity == "informativa"


def test_integrated_monitor_persists_explanation_and_escalates(monkeypatch):
    test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    db = TestSession()
    try:
        for definition in RULES:
            db.add(Rule(id=definition.id, name=definition.name, description=definition.description,
                        priority=definition.priority, active=True,
                        definition={"condition": definition.condition, "conclusion": definition.conclusion,
                                    "recommendation": definition.recommendation}))
        api = ApiEndpoint(name="API simulada", url="http://localhost:9999", expected_status=200)
        db.add(api)
        db.commit()
        monkeypatch.setattr("app.application.monitoring.check_api", lambda _url: {"status_code": 500, "latency_ms": 120, "error_type": None, "error_message": None})
        for _ in range(3):
            payload = run_monitor(api, db)
        assert payload["severity"] == "alta"
        assert {row.rule_id for row in db.scalars(select(DiagnosisRule)).all()} >= {"R02", "R12", "R13", "R15"}
        latest = db.scalars(select(Diagnosis).order_by(Diagnosis.id.desc())).first()
        assert latest.facts["consecutive_failures"] == 3

        api.url = "http://localhost:9997"
        db.commit()
        changed_target = run_monitor(api, db)
        assert changed_target["facts"]["consecutive_failures"] == 1
        assert {rule["id"] for rule in changed_target["rules"]} == {"R02"}

        other = ApiEndpoint(name="Otra API", url="http://localhost:9998", expected_status=200)
        db.add(other)
        db.commit()
        monkeypatch.setattr("app.application.monitoring.check_api", lambda _url: {"status_code": None, "latency_ms": 80, "error_type": "connection", "error_message": "Sin conexión"})
        for _ in range(3):
            other_payload = run_monitor(other, db)
        assert {rule["id"] for rule in other_payload["rules"]} == {"R11"}
        assert other_payload["facts"]["consecutive_failures"] == 0
    finally:
        db.close()
        Base.metadata.drop_all(test_engine)


def test_periodic_monitoring_respects_interval_and_inactive_services(monkeypatch):
    test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr("app.infrastructure.scheduler.SessionLocal", TestSession)
    monkeypatch.setattr("app.application.monitoring.check_api", lambda _url: {"status_code": 200, "latency_ms": 20, "error_type": None, "error_message": None})
    try:
        with TestSession() as db:
            active = ApiEndpoint(name="Activa", url="http://localhost:9000", interval_minutes=1)
            inactive = ApiEndpoint(name="Inactiva", url="http://localhost:9001", active=False, interval_minutes=1)
            db.add_all([active, inactive])
            db.commit()
            active_id = active.id

        monitor_due_apis()
        monitor_due_apis()
        with TestSession() as db:
            assert db.scalar(select(func.count(MonitorRun.id))) == 1
            first = db.scalar(select(MonitorRun).where(MonitorRun.api_id == active_id))
            first.checked_at = datetime.now(timezone.utc) - timedelta(minutes=2)
            db.commit()

        monitor_due_apis()
        with TestSession() as db:
            assert db.scalar(select(func.count(MonitorRun.id))) == 2
            assert {run.api_id for run in db.scalars(select(MonitorRun))} == {active_id}
    finally:
        Base.metadata.drop_all(test_engine)
