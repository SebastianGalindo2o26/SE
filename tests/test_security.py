import pytest
from fastapi.testclient import TestClient

from app.infrastructure.database import secure_database_url
from app.main import app
from app.infrastructure.http_monitor import UnsafeDestination, validate_destination


def test_outbound_host_must_be_explicitly_authorized(monkeypatch):
    monkeypatch.setenv("ALLOWED_TARGET_HOSTS", "localhost,127.0.0.1")
    with pytest.raises(UnsafeDestination, match="ALLOWED_TARGET_HOSTS"):
        validate_destination("https://example.com/health")
    validate_destination("http://127.0.0.1:8000/health")


def test_postgresql_requires_encrypted_connection():
    with pytest.raises(ValueError, match="sslmode"):
        secure_database_url("postgresql://user:password@host/db")
    assert secure_database_url("postgresql://user:password@host/db?sslmode=require").startswith("postgresql+psycopg://")


def test_dashboard_rejects_untrusted_host_header():
    client = TestClient(app, base_url="http://untrusted.example")
    assert client.get("/").status_code == 400
