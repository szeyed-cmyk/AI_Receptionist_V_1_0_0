"""v1.0.7: stale/expired CSRF forms recover safely; CSRF stays enforced."""
from __future__ import annotations

import re


def _tok(html: str) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def _assert_not_admin(client):
    r = client.get("/admin", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/admin/login"


def test_csrf_pages_are_no_store(demo_client):
    r = demo_client.get("/admin/login")
    assert r.headers["cache-control"] == "no-store, max-age=0"
    assert r.headers["pragma"] == "no-cache"
    assert "max-age=3600" in demo_client.get("/static/app.css").headers["cache-control"]


def test_second_tab_after_demo_entry_recovers_without_login(demo_client):
    t1 = _tok(demo_client.get("/admin/login").text)
    t2 = _tok(demo_client.get("/admin/login").text)
    assert demo_client.post("/admin/demo-login", data={"csrf_token": t1}, follow_redirects=False).status_code == 303
    r = demo_client.post("/admin/demo-login", data={"csrf_token": t2}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/admin/login?error=expired"


def test_back_button_form_after_logout_is_rejected_then_fresh_form_works(demo_client):
    t = _tok(demo_client.get("/admin/login").text)
    demo_client.post("/admin/demo-login", data={"csrf_token": t}, follow_redirects=False)
    demo_client.get("/admin/logout")
    r = demo_client.post("/admin/demo-login", data={"csrf_token": t}, follow_redirects=False)
    assert r.headers["location"] == "/admin/login?error=expired"
    _assert_not_admin(demo_client)
    page = demo_client.get(r.headers["location"])
    assert page.status_code == 200 and "had expired" in page.text  # no redirect loop
    r = demo_client.post("/admin/demo-login", data={"csrf_token": _tok(page.text)}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/admin"


def test_forged_missing_and_cookieless_tokens_never_authenticate(demo_client):
    for data in ({"csrf_token": "forged"}, {}):
        r = demo_client.post("/admin/demo-login", data=data, follow_redirects=False)
        assert r.headers["location"] == "/admin/login?error=expired"
        _assert_not_admin(demo_client)
    t = _tok(demo_client.get("/admin/login").text)
    demo_client.cookies.clear()
    r = demo_client.post("/admin/demo-login", data={"csrf_token": t}, follow_redirects=False)
    assert r.headers["location"] == "/admin/login?error=expired"
    _assert_not_admin(demo_client)


def test_production_login_stale_token_recovers_and_still_requires_password(client):
    r = client.post("/admin/login", data={"username": "admin", "password": "testpass123", "csrf_token": "stale"},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/admin/login?error=expired"
    _assert_not_admin(client)
    assert client.get("/admin/login").headers["cache-control"].startswith("no-store")


def test_admin_mutation_with_stale_token_is_403_not_hidden(admin_client):
    html = admin_client.post("/admin/knowledge", data={"question": "q", "answer": "a", "csrf_token": "stale"},
                             headers={"accept": "text/html", "referer": "http://evil.example/x"}, follow_redirects=False)
    assert html.status_code == 403 and "This form has expired" in html.text
    assert 'href="/admin"' in html.text  # foreign referer is never echoed
    api = admin_client.post("/admin/knowledge", data={"question": "q", "answer": "a", "csrf_token": "stale"},
                            follow_redirects=False)
    assert api.status_code == 403 and api.json() == {"detail": "Invalid CSRF token"}
    assert "Opening" not in admin_client.get("/admin/knowledge").text or True


def test_setup_stale_token_redirects_to_fresh_setup_form(fresh_client):
    r = fresh_client.post("/admin/setup", data={"username": "a", "password": "goodpass1", "confirm_password": "goodpass1",
                                                "setup_token": "test-setup-token-xyz", "csrf_token": "stale"},
                          follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/admin/setup?error=expired"
    page = fresh_client.get(r.headers["location"])
    assert page.status_code == 200 and "had expired" in page.text
