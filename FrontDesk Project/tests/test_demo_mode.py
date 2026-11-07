"""Testing the public sandbox boundary; no production database or integrations."""
from __future__ import annotations

import base64
import itsdangerous
import json
import re
import pytest
from unittest.mock import AsyncMock, patch


def csrf(client):
    page = client.get("/admin/login")
    assert page.status_code == 200
    return re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)


def enter_demo(client):
    token = csrf(client)
    response = client.post("/admin/demo-login", data={"csrf_token": token}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin"
    return client


def test_demo_database_is_separate_and_never_uses_env_credentials(demo_client, tmp_path):
    from app.config import settings
    from app.database import SessionLocal
    from app.ai_service import get_setting
    assert "demo-pytest-demo" in settings.database_url and "_bootstrap.db" in settings.database_url
    assert "production-must-not-open" not in settings.database_url
    assert settings.ai_api_key == "" and settings.ai_base_url == ""
    assert settings.admin_password == ""
    db = SessionLocal()
    assert get_setting(db, "business_name") == "Lumen Dental Studio"
    assert not get_setting(db, "ai_api_key", "")
    db.close()
    assert not (tmp_path / "production-must-not-open.db").exists()
    page = demo_client.get("/admin/login")
    assert "Enter Admin demo" in page.text and "production-password-must-not-be-used" not in page.text
    response = demo_client.post("/admin/login", data={"username": "production-admin-must-not-be-used", "password": "production-password-must-not-be-used", "csrf_token": csrf(demo_client)}, follow_redirects=False)
    assert response.status_code == 403


def test_only_real_admin_role_and_demo_csrf(demo_client):
    response = demo_client.post("/admin/demo-login", data={"csrf_token": "forged"}, follow_redirects=False)
    # v1.0.7: rejected with a safe redirect to a fresh form, never a session.
    assert response.status_code == 303 and response.headers["location"] == "/admin/login?error=expired"
    assert demo_client.get("/admin", follow_redirects=False).headers["location"] == "/admin/login"
    enter_demo(demo_client)
    page = demo_client.get("/admin")
    assert page.status_code == 200
    assert "Admin demo" in page.text
    assert "Lumen Dental Studio" in page.text
    for path in ("/admin/appointments", "/admin/conversations", "/admin/knowledge", "/admin/settings"):
        response = demo_client.get(path)
        assert response.status_code == 200, path
    assert "External AI key" not in demo_client.get("/admin/settings").text
    assert demo_client.get("/health").json()["version"] == "1.0.8"


def test_demo_sensitive_writes_and_setup_guards_always_apply(demo_client):
    enter_demo(demo_client)
    page = demo_client.get("/admin/settings")
    csrf_value = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    values = {"business_name": "Injected production name", "ai_base_url": "https://should-not-be-used.invalid", "ai_api_key": "new-key", "ai_model": "new-model", "opening_hour": "8", "closing_hour": "18", "closed_days": "sunday", "holiday_dates": "", "csrf_token": csrf_value}
    assert demo_client.post("/admin/settings", data=values).status_code == 403
    assert demo_client.post("/admin/change-password", data={"current_password": "x", "new_password": "newpass1234", "confirm_password": "newpass1234", "csrf_token": csrf_value}).status_code == 403
    assert demo_client.get("/admin/setup", follow_redirects=False).headers["location"] == "/admin/login"
    assert demo_client.post("/admin/setup", data={"username": "new-admin", "password": "new-password123", "confirm_password": "new-password123", "setup_token": "", "csrf_token": csrf_value}).status_code == 403
    from app.database import SessionLocal
    from app.ai_service import get_setting
    db = SessionLocal()
    assert get_setting(db, "business_name") == "Lumen Dental Studio"
    assert not get_setting(db, "ai_api_key", "")
    db.close()


def test_demo_local_responses_never_create_network_client(demo_client):
    with patch("app.ai_service.httpx.AsyncClient", side_effect=AssertionError("network forbidden")) as no_network:
        response = demo_client.post("/chat", data={"message": "What are your opening hours?"})
        assert response.status_code == 200
        assert "9 AM to 6 PM" in response.json()["reply"]
        no_network.assert_not_called()
    assert "60-minute" in demo_client.post("/chat", data={"message": "How long is an appointment?"}).json()["reply"]
    assert "provide your name" in demo_client.post("/chat", data={"message": "I would like to book an appointment"}).json()["reply"]


def test_demo_can_manage_own_rows_not_seed_or_other_reviewers(demo_client):
    from fastapi.testclient import TestClient
    from app import app
    from app.models import KnowledgeItem
    enter_demo(demo_client)
    token = csrf(demo_client)
    r = demo_client.post("/admin/knowledge", data={"question": "My own sandbox question", "answer": "A test answer", "category": "Testing", "csrf_token": token}, follow_redirects=False)
    assert r.status_code == 303
    from app.database import bind_for_session
    from app.config import settings
    from starlette.middleware.sessions import SessionMiddleware
    from fastapi import FastAPI
    probe = FastAPI()
    probe.add_middleware(SessionMiddleware, secret_key=settings.secret_key + "|frontdesk-demo|" + settings.demo_seed, session_cookie="frontdesk_demo_session")
    middleware = next(m for m in probe.user_middleware if m.cls is SessionMiddleware)
    serializer = next(iter(middleware.kwargs["secret_key"] if isinstance(middleware.kwargs["secret_key"], list) else [middleware.kwargs["secret_key"]]), None)
    # Match SessionMiddleware's own TaggedJSONSerializer implementation.
    import itsdangerous
    signer = itsdangerous.TimestampSigner(str(middleware.kwargs["secret_key"]), )
    cookie = demo_client.cookies.get("frontdesk_demo_session")
    payload = json.loads(base64.urlsafe_b64decode(signer.unsign(cookie).decode() + "=="))
    _, ScopedSession = bind_for_session(payload["demo_scope"])
    db = ScopedSession()
    own_id = db.query(KnowledgeItem).filter_by(question="My own sandbox question").one().id
    seed_id = db.query(KnowledgeItem).filter(KnowledgeItem.question.like("%opening hours%")).first().id
    db.close()
    assert demo_client.get(f"/admin/knowledge/{own_id}/edit").status_code == 200
    assert demo_client.post(f"/admin/knowledge/{own_id}/edit", data={"question": "Edited own question", "answer": "Edited own answer", "category": "Testing", "csrf_token": token}, follow_redirects=False).status_code == 303
    assert demo_client.post(f"/admin/knowledge/{seed_id}/edit", data={"question": "Override seed", "answer": "Bad", "category": "Bad", "csrf_token": token}, follow_redirects=False).status_code == 403
    assert demo_client.post(f"/admin/knowledge/{seed_id}/delete", data={"csrf_token": token}, follow_redirects=False).status_code == 403
    chat = demo_client.post("/chat", data={"message": "Reviewer-owned conversation"})
    own_conv = chat.json()["conversation_id"]
    assert demo_client.post(f"/admin/conversations/{own_conv}/delete", data={"csrf_token": token}, follow_redirects=False).status_code == 303
    assert demo_client.post("/admin/conversations/1/delete", data={"csrf_token": token}, follow_redirects=False).status_code == 403
    # A second signed-in reviewer on the same isolated DB cannot delete my FAQ.
    with TestClient(app, base_url="http://reviewer-two.test") as other:
        enter_demo(other)
        other_token = csrf(other)
        assert other.post(f"/admin/knowledge/{own_id}/edit", data={"question": "Not mine", "answer": "Not mine", "category": "Bad", "csrf_token": other_token}, follow_redirects=False).status_code == 403
        assert other.post(f"/admin/knowledge/{own_id}/delete", data={"csrf_token": other_token}, follow_redirects=False).status_code == 403
    assert demo_client.post(f"/admin/knowledge/{own_id}/delete", data={"csrf_token": token}, follow_redirects=False).status_code == 303


def test_demo_booking_makes_only_local_fictional_rows(demo_client, monkeypatch):
    enter_demo(demo_client)
    # Next Monday is a weekday, so this structured request is always testable.
    response = demo_client.post("/chat", data={"message": "Demo Visitor, 555-0199, dental checkup, next Monday at 3pm"})
    assert response.status_code == 200
    assert "confirmed" in response.json()["reply"].lower()
    from app.database import SessionLocal
    from app.models import Appointment
    from app.config import settings
    cookie = demo_client.cookies.get("frontdesk_demo_session")
    import itsdangerous
    payload = json.loads(base64.urlsafe_b64decode(itsdangerous.TimestampSigner(settings.secret_key + "|frontdesk-demo|" + settings.demo_seed, ).unsign(cookie).decode() + "=="))
    from app.database import bind_for_session
    _, ScopedSession = bind_for_session(payload.get("demo_scope"))
    db = ScopedSession()
    appointment = db.query(Appointment).filter_by(customer_name="Demo Visitor", customer_phone="555-0199").one()
    assert appointment.service == "dental checkup"
    assert appointment.duration_minutes == 60
    db.close()


def test_signed_cookies_cannot_cross_demo_and_production(tmp_path, monkeypatch):
    """A valid cookie issued under the other deployment mode is rejected."""
    import os, sys
    from fastapi.testclient import TestClient

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FRONTDESK_TESTING", "1")
    monkeypatch.setenv("SECRET_KEY", "same-test-signing-key-on-restart")
    monkeypatch.setenv("HTTPS_ONLY", "false")
    monkeypatch.setenv("DEMO_SEED", "restart-test")

    def load(demo):
        monkeypatch.setenv("DEMO_MODE", "true" if demo else "false")
        # v1.0.6: a demo instance must not carry production DSN/setup token.
        monkeypatch.setenv("DATABASE_URL", "" if demo else f"sqlite:///{tmp_path}/production.db")
        monkeypatch.setenv("SETUP_TOKEN", "" if demo else "test-setup-token")
        for mod in list(sys.modules):
            if mod == "app" or mod.startswith("app.") or mod == "main" or mod == "routes" or mod.startswith("routes."):
                del sys.modules[mod]
        from app import app
        return app

    with TestClient(load(True), base_url="http://mode.test") as demo:
        enter_demo(demo)
        demo_cookie = demo.cookies.get("frontdesk_demo_session")
        assert demo_cookie is not None
    with TestClient(load(False), base_url="http://mode.test") as production:
        # Production Cookie2 legacy name accepts an explicitly forged demo value;
        # it is still rejected by the session signature/mode check.
        production.cookies.set("frontdesk_session", demo_cookie)
        response = production.get("/admin", follow_redirects=False)
        assert demo_cookie is not None
        assert response.status_code == 303 and response.headers["location"] == "/admin/login"
        production.cookies.clear()
        token = csrf(production)
        assert production.post("/admin/login", data={"username": "production-admin-must-not-be-used", "password": "production-password-must-not-be-used", "csrf_token": token}, follow_redirects=False).status_code == 303
        real_cookie = production.cookies.get("frontdesk_session")
        assert real_cookie is not None
    with TestClient(load(True), base_url="http://mode.test") as demo:
        # Replaying the production value under either cookie name is invalid.
        demo.cookies.set("frontdesk_demo_session", real_cookie)
        demo.cookies.set("frontdesk_session", real_cookie)
        response = demo.get("/admin", follow_redirects=False)
        assert response.status_code == 303 and response.headers["location"] == "/admin/login"
    # Independently assert the production signature is invalid under demo salt.
    import itsdangerous
    signer = itsdangerous.TimestampSigner("same-test-signing-key-on-restart|frontdesk-demo|restart-test", )
    with pytest.raises(itsdangerous.exc.BadSignature):
        signer.unsign(real_cookie)


def test_old_production_cookie_name_rejected_when_demo_enabled(demo_client):
    from fastapi.testclient import TestClient
    from app import app
    with TestClient(app, base_url="http://stale-cookie.test") as stale:
        stale.cookies.set("frontdesk_session", "untrusted-production-session")
        response = stale.get("/admin", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"


def test_demo_capacity_limit_is_server_side(demo_client, monkeypatch):
    from app.config import settings
    from app.database import registry
    monkeypatch.setattr(settings, "demo_max_sessions", 1)
    token = csrf(demo_client)
    # The public anonymous chat binds a legitimate scope, not production.
    assert demo_client.post("/chat", data={"message": "hello"}).status_code == 200
    assert len(registry.demo_scopes) == 1
    assert registry.can_create_demo("another-test-scope-not-secret") is False
    response = demo_client.post("/admin/demo-login", data={"csrf_token": token}, follow_redirects=False)
    assert response.status_code == 303 and "error=busy" in response.headers["location"]
    assert len(registry.demo_scopes) == 1


def test_all_admin_routes_guarded_even_in_demo_when_non_admin_cookie(demo_client):
    for path in ("/admin", "/admin/knowledge", "/admin/settings", "/admin/appointments", "/admin/conversations"):
        response = demo_client.get(path, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"
