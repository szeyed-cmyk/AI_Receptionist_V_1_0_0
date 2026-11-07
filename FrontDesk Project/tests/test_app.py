"""Core app and auth tests."""
from __future__ import annotations

import re


def test_health_and_chat_page(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

    r = client.get("/")
    assert r.status_code == 200
    assert "html" in r.headers.get("content-type", "")


def test_admin_pages_redirect_when_not_logged_in(client):
    for path in (
        "/admin",
        "/admin/knowledge",
        "/admin/settings",
        "/admin/appointments",
        "/admin/conversations",
    ):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 303, path
        assert "/admin/login" in r.headers.get("location", ""), path


def test_forged_admin_cookie_rejected(client):
    """A plain admin=true cookie must not grant access."""
    client.cookies.set("admin", "true")
    r = client.get("/admin", follow_redirects=False)
    assert r.status_code == 303
    assert "/admin/login" in r.headers.get("location", "")


def test_login_works(client, csrf_and_session):
    r = client.post(
        "/admin/login",
        data={"username": "admin", "password": "wrong", "csrf_token": csrf_and_session},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "error=1" in r.headers.get("location", "")

    # Refresh CSRF after failed attempt (same session)
    page = client.get("/admin/login")
    m = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    token = m.group(1)

    r = client.post(
        "/admin/login",
        data={"username": "admin", "password": "testpass123", "csrf_token": token},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/admin"

    r = client.get("/admin", follow_redirects=False)
    assert r.status_code == 200


def test_logout_clears_session(admin_client):
    r = admin_client.get("/admin", follow_redirects=False)
    assert r.status_code == 200
    r = admin_client.get("/admin/logout", follow_redirects=False)
    assert r.status_code == 303
    r = admin_client.get("/admin", follow_redirects=False)
    assert r.status_code == 303
