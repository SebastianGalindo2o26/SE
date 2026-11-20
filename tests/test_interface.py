from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base, get_db
from app.main import app
from app.infrastructure.models import ApiEndpoint
from app.infrastructure import http_monitor


def test_deactivated_service_can_be_restored_from_dashboard():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    def override_db():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with Session() as db:
            api = ApiEndpoint(name="Servicio recuperable", url="http://localhost:9000", active=True)
            db.add(api)
            db.commit()
            api_id = api.id

        client = TestClient(app, base_url="http://localhost")
        assert client.post(f"/apis/{api_id}/deactivate", follow_redirects=False).status_code == 403
        client.get("/").raise_for_status()
        token = client.cookies["csrf_token"]
        assert client.post(f"/apis/{api_id}/deactivate", data={"csrf_token": token}, follow_redirects=False).status_code == 303
        page = client.get("/")
        assert "Servicios desactivados (1)" in page.text
        assert f"/apis/{api_id}/activate" in page.text
        assert client.post(f"/apis/{api_id}/activate", data={"csrf_token": token}, follow_redirects=False).status_code == 303
        assert "Servicios desactivados (1)" not in client.get("/").text
        assert client.get("/api/apis").json()[0]["active"] is True
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)


def test_public_api_can_be_registered_without_editing_host_list(monkeypatch):
    monkeypatch.setenv("ALLOWED_TARGET_HOSTS", "localhost,127.0.0.1")
    monkeypatch.setattr(http_monitor.socket, "getaddrinfo", lambda _host, port: [(None, None, None, None, ("8.8.8.8", port))])
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    def override_db():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app, base_url="http://localhost")
        client.get("/").raise_for_status()
        response = client.post("/apis", data={
            "name": "API pública", "url": "https://api.example.test/health",
            "expected_status": 200, "interval_minutes": 5,
            "csrf_token": client.cookies["csrf_token"],
        }, follow_redirects=False)
        assert response.status_code == 303
        assert client.get("/api/apis").json()[0]["url"] == "https://api.example.test/health"
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
