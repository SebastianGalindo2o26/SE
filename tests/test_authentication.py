from pathlib import Path

import httpx
import pytest
from cryptography.fernet import Fernet
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.application.authentication import configure_authentication
from app.infrastructure.credentials import CredentialError, decrypt_secret, encrypt_secret
from app.infrastructure.database import Base, get_db
from app.infrastructure import http_monitor
from app.infrastructure.knowledge import seed_rules
from app.infrastructure.models import ApiCredential, ApiEndpoint, MonitorRun
from app.infrastructure.scheduler import monitor_due_apis
from app.main import app
from scripts import setup_credentials


@pytest.fixture
def database(monkeypatch):
    monkeypatch.setenv("CREDENTIALS_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield session_factory
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.mark.parametrize(
    ("auth_type", "header_name", "username", "secret", "expected_header", "expected_value"),
    [
        ("bearer", "", "", "token-private", "authorization", "Bearer token-private"),
        ("api_key_header", "X-API-Key", "", "key-private", "x-api-key", "key-private"),
        ("basic", "", "usuario", "clave-private", "authorization", "Basic dXN1YXJpbzpjbGF2ZS1wcml2YXRl"),
    ],
)
def test_authenticated_get_sends_expected_header_without_persisting_it(
    database, monkeypatch, auth_type, header_name, username, secret, expected_header, expected_value
):
    api = ApiEndpoint(name="Protegida", url="http://localhost:8000/demo/status/200")
    configure_authentication(api, auth_type, header_name, username, secret)
    assert secret not in api.credential.encrypted_secret

    def respond(request):
        assert request.method == "GET"
        assert request.headers[expected_header] == expected_value
        return httpx.Response(200)

    real_client = httpx.Client
    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(http_monitor.httpx, "Client", lambda **kwargs: real_client(transport=transport, **kwargs))
    result = http_monitor.check_api(api.url, api.credential)
    assert result["status_code"] == 200
    assert secret not in str(result)


def test_web_form_encrypts_rotates_and_removes_secret(database, monkeypatch):
    def override_db():
        with database() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app, base_url="http://localhost")
        client.get("/").raise_for_status()
        csrf = client.cookies["csrf_token"]
        form = {
            "name": "API protegida", "url": "http://localhost:8000/demo/status/200",
            "expected_status": 200, "interval_minutes": 5, "auth_type": "bearer",
            "auth_secret": "no-mostrar-123", "csrf_token": csrf,
        }
        assert client.post("/apis", data=form, follow_redirects=False).status_code == 303
        api_id = client.get("/api/apis").json()[0]["id"]
        with database() as db:
            credential = db.get(ApiCredential, api_id)
            encrypted = credential.encrypted_secret
            assert encrypted != "no-mostrar-123"
            assert decrypt_secret(encrypted) == "no-mostrar-123"
        assert "no-mostrar-123" not in client.get("/").text
        assert "no-mostrar-123" not in client.get("/api/apis").text
        assert client.get("/api/apis").json()[0]["auth_type"] == "bearer"

        seen = []

        def fake_check(_url, credential):
            seen.append(decrypt_secret(credential.encrypted_secret))
            return {"status_code": 200, "latency_ms": 10, "error_type": None, "error_message": None}

        monkeypatch.setattr("app.application.monitoring.check_api", fake_check)
        assert client.post(f"/apis/{api_id}/monitor", data={"csrf_token": csrf}, follow_redirects=False).status_code == 303
        assert seen == ["no-mostrar-123"]
        assert "no-mostrar-123" not in client.get("/api/history").text

        update = {**form, "auth_secret": ""}
        assert client.post(f"/apis/{api_id}/update", data=update, follow_redirects=False).status_code == 303
        with database() as db:
            assert db.get(ApiCredential, api_id).encrypted_secret == encrypted

        update["auth_secret"] = "clave-nueva-456"
        assert client.post(f"/apis/{api_id}/update", data=update, follow_redirects=False).status_code == 303
        with database() as db:
            assert decrypt_secret(db.get(ApiCredential, api_id).encrypted_secret) == "clave-nueva-456"
        assert "clave-nueva-456" not in client.get("/").text

        update["auth_type"] = "none"
        update["auth_secret"] = ""
        assert client.post(f"/apis/{api_id}/update", data=update, follow_redirects=False).status_code == 303
        with database() as db:
            assert db.get(ApiCredential, api_id) is None
        assert client.get("/api/apis").json()[0]["auth_type"] == "none"
    finally:
        app.dependency_overrides.clear()


def test_invalid_auth_is_rejected_without_saving_or_leaking_secret(database, monkeypatch):
    api = ApiEndpoint(name="No válida", url="http://example.com/health")
    with pytest.raises(CredentialError, match="HTTPS"):
        configure_authentication(api, "bearer", "", "", "secret-value")
    api.url = "https://example.com/health"
    with pytest.raises(CredentialError, match="header válido"):
        configure_authentication(api, "api_key_header", "Host", "", "secret-value")
    with pytest.raises(CredentialError, match="Ingresa la clave"):
        configure_authentication(api, "basic", "", "user", "")
    encrypted = encrypt_secret("secret-value")
    monkeypatch.setenv("CREDENTIALS_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    with pytest.raises(CredentialError, match="No se pudo descifrar") as error:
        decrypt_secret(encrypted)
    assert "secret-value" not in str(error.value)


def test_automatic_monitor_uses_saved_credential(database, monkeypatch):
    with database() as db:
        seed_rules(db)
        api = ApiEndpoint(name="Automática", url="http://localhost:8000/demo/status/200", interval_minutes=1)
        configure_authentication(api, "api_key_header", "X-API-Key", "", "saved-key")
        db.add(api)
        db.commit()
    seen = []

    def fake_check(_url, credential):
        seen.append((credential.auth_type, decrypt_secret(credential.encrypted_secret)))
        return {"status_code": 200, "latency_ms": 20, "error_type": None, "error_message": None}

    monkeypatch.setattr("app.infrastructure.scheduler.SessionLocal", database)
    monkeypatch.setattr("app.application.monitoring.check_api", fake_check)
    monitor_due_apis()
    with database() as db:
        assert db.scalar(select(func.count(MonitorRun.id))) == 1
    assert seen == [("api_key_header", "saved-key")]


def test_transport_error_does_not_expose_secret(database, monkeypatch):
    credential = ApiCredential(auth_type="bearer", encrypted_secret=encrypt_secret("very-private-token"))

    def fail(_request):
        raise httpx.ConnectError("very-private-token")

    real_client = httpx.Client
    transport = httpx.MockTransport(fail)
    monkeypatch.setattr(http_monitor.httpx, "Client", lambda **kwargs: real_client(transport=transport, **kwargs))
    result = http_monitor.check_api("http://localhost:8000/health", credential)
    assert result["error_type"] == "connection"
    assert "very-private-token" not in str(result)


def test_setup_key_replaces_blank_example_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CREDENTIALS_ENCRYPTION_KEY", raising=False)
    Path(".env.example").write_text("DATABASE_URL=sqlite:///./test.db\nCREDENTIALS_ENCRYPTION_KEY=\n", encoding="utf-8")
    setup_credentials.main()
    contents = Path(".env").read_text(encoding="utf-8")
    key = dotenv_values(".env")["CREDENTIALS_ENCRYPTION_KEY"]
    assert contents.count("CREDENTIALS_ENCRYPTION_KEY=") == 1
    assert Fernet(key).decrypt(Fernet(key).encrypt(b"works")) == b"works"
    setup_credentials.main()
    assert Path(".env").read_text(encoding="utf-8") == contents
