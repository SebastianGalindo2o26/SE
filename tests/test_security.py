import pytest
import httpx
from fastapi.testclient import TestClient

from app.infrastructure.database import secure_database_url
from app.main import app
from app.infrastructure import http_monitor
from app.infrastructure.http_monitor import UnsafeDestination, validate_destination


def test_public_target_needs_no_host_allowlist(monkeypatch):
    monkeypatch.setenv("ALLOWED_TARGET_HOSTS", "localhost,127.0.0.1")
    monkeypatch.setattr(http_monitor.socket, "getaddrinfo", lambda _host, port: [(None, None, None, None, ("8.8.8.8", port))])
    validate_destination("https://api.example.test/health")
    validate_destination("http://127.0.0.1:8000/health")


def test_private_or_metadata_target_stays_blocked(monkeypatch):
    monkeypatch.setenv("ALLOWED_PRIVATE_HOSTS", "localhost,127.0.0.1,::1")
    with pytest.raises(UnsafeDestination, match="ALLOWED_PRIVATE_HOSTS"):
        validate_destination("http://169.254.169.254/latest/meta-data/")
    monkeypatch.setattr(http_monitor.socket, "getaddrinfo", lambda _host, port: [(None, None, None, None, ("10.0.0.5", port))])
    with pytest.raises(UnsafeDestination, match="ALLOWED_PRIVATE_HOSTS"):
        validate_destination("https://api.example.test/health")


def test_mixed_public_and_private_dns_answers_are_blocked(monkeypatch):
    monkeypatch.setattr(http_monitor.socket, "getaddrinfo", lambda _host, port: [
        (None, None, None, None, ("8.8.8.8", port)),
        (None, None, None, None, ("10.0.0.5", port)),
    ])
    with pytest.raises(UnsafeDestination, match="ALLOWED_PRIVATE_HOSTS"):
        validate_destination("https://api.example.test/health")


def test_url_with_embedded_credentials_is_rejected():
    with pytest.raises(UnsafeDestination, match="sin credenciales"):
        validate_destination("https://@api.example.test/health")


def test_get_connects_to_validated_ip_with_original_host_and_sni(monkeypatch):
    monkeypatch.setattr(http_monitor.socket, "getaddrinfo", lambda _host, port: [(None, None, None, None, ("8.8.8.8", port))])

    def respond(request):
        assert request.url.host == "8.8.8.8"
        assert request.headers["host"] == "api.example.test"
        assert request.extensions["sni_hostname"] == "api.example.test"
        return httpx.Response(200)

    real_client = httpx.Client
    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(http_monitor.httpx, "Client", lambda **kwargs: real_client(transport=transport, **kwargs))
    assert http_monitor.check_api("https://api.example.test/health")["status_code"] == 200


def test_postgresql_requires_encrypted_connection():
    with pytest.raises(ValueError, match="sslmode"):
        secure_database_url("postgresql://user:password@host/db")
    assert secure_database_url("postgresql://user:password@host/db?sslmode=require").startswith("postgresql+psycopg://")


def test_dashboard_rejects_untrusted_host_header():
    client = TestClient(app, base_url="http://untrusted.example")
    assert client.get("/").status_code == 400
