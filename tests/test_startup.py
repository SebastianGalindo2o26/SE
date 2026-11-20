"""Comprueba el arranque completo sin acceder a la base Neon configurada."""

import os
import subprocess
import sys
from pathlib import Path


def test_startup_creates_schema_and_serves_dashboard(tmp_path):
    workspace = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["DATABASE_URL"] = f"sqlite:///{(tmp_path / 'startup.db').as_posix()}"
    script = """
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select
from app.main import app
from app.infrastructure.database import SessionLocal, engine
from app.infrastructure.models import Rule

with TestClient(app, base_url='http://localhost') as client:
    assert client.get('/health').json() == {'status': 'ok'}
    page = client.get('/')
    assert page.status_code == 200
    assert 'name="auth_type"' in page.text
    assert '.demo-examples' in client.get('/static/app.css').text
    assert client.get('/static/auth.css').status_code == 200
    assert len(inspect(engine).get_table_names()) == 7
    with SessionLocal() as db:
        assert db.scalar(select(func.count(Rule.id))) == 15
"""
    subprocess.run([sys.executable, "-c", script], cwd=workspace, env=environment, check=True, capture_output=True, text=True)
