"""Test fixtures. Sets env before importing the app so SQLite uses a temp file."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_TEST_DB = ROOT / "data" / "test_ai_receptionist.db"
os.environ["FRONTDESK_TESTING"] = "1"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-only-not-production"
os.environ["HTTPS_ONLY"] = "false"
os.environ["ADMIN_USERNAME"] = ""
os.environ["ADMIN_PASSWORD"] = ""
os.environ["SETUP_TOKEN"] = "test-setup-token-xyz"
os.environ["DEMO_MODE"] = "false"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("FRONTDESK_TESTING", "1")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-pytest-only-not-production")
    monkeypatch.setenv("HTTPS_ONLY", "false")
    monkeypatch.setenv("ADMIN_USERNAME", "")
    monkeypatch.setenv("ADMIN_PASSWORD", "")
    monkeypatch.setenv("SETUP_TOKEN", "test-setup-token-xyz")
    monkeypatch.setenv("DEMO_MODE", "false")

    for mod in list(sys.modules):
        if (
            mod == "app"
            or mod.startswith("app.")
            or mod == "main"
            or mod == "routes"
            or mod.startswith("routes.")
        ):
            del sys.modules[mod]

    from app.database import Base, engine, SessionLocal
    from app import app as fastapi_app
    from app.models import Setting  # noqa: F401
    from app.ai_service import set_setting
    from app.auth import hash_password

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    set_setting(db, "admin_username", "admin")
    set_setting(db, "admin_password", hash_password("testpass123"))
    set_setting(db, "admin_role", "admin")
    set_setting(db, "business_name", "Test Clinic")
    set_setting(db, "opening_hour", "9")
    set_setting(db, "closing_hour", "18")
    set_setting(db, "closed_days", "sunday")
    set_setting(db, "holiday_dates", "2099-12-25")
    db.close()

    from fastapi.testclient import TestClient

    with TestClient(fastapi_app) as c:
        yield c

    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def fresh_client(tmp_path, monkeypatch):
    """Client with an empty database (no admin) for setup-flow tests."""
    db_path = tmp_path / "fresh.db"
    monkeypatch.setenv("FRONTDESK_TESTING", "1")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-pytest-only-not-production")
    monkeypatch.setenv("HTTPS_ONLY", "false")
    monkeypatch.setenv("ADMIN_USERNAME", "")
    monkeypatch.setenv("ADMIN_PASSWORD", "")
    monkeypatch.setenv("SETUP_TOKEN", "test-setup-token-xyz")
    monkeypatch.setenv("DEMO_MODE", "false")

    for mod in list(sys.modules):
        if (
            mod == "app"
            or mod.startswith("app.")
            or mod == "main"
            or mod == "routes"
            or mod.startswith("routes.")
        ):
            del sys.modules[mod]

    from app.database import Base, engine
    from app import app as fastapi_app

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    from fastapi.testclient import TestClient

    with TestClient(fastapi_app) as c:
        yield c

    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def csrf_and_session(client):
    r = client.get("/admin/login")
    assert r.status_code == 200
    import re

    m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    assert m, "csrf_token missing from login page"
    return m.group(1)


@pytest.fixture()
def admin_client(client, csrf_and_session):
    r = client.post(
        "/admin/login",
        data={"username": "admin", "password": "testpass123", "csrf_token": csrf_and_session},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/admin"
    return client


@pytest.fixture()
def demo_client(tmp_path, monkeypatch):
    """A strict, credential-free demo instance (v1.0.6 refuses mixed config)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FRONTDESK_TESTING", "1")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DEMO_SEED", "pytest-demo")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-pytest-only-not-production")
    monkeypatch.setenv("HTTPS_ONLY", "false")
    for name in ("ADMIN_USERNAME", "ADMIN_PASSWORD", "SETUP_TOKEN", "AI_API_KEY", "AI_BASE_URL"):
        monkeypatch.setenv(name, "")
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("app.") or mod == "main" or mod == "routes" or mod.startswith("routes."):
            del sys.modules[mod]
    from app import app as fastapi_app
    from fastapi.testclient import TestClient
    with TestClient(fastapi_app, base_url="http://demo.test") as c:
        yield c
