"""Setup token, SECRET_KEY enforcement, plaintext password rejection, cascade delete."""
from __future__ import annotations

import re
import pytest


def _csrf(html: str) -> str:
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert m
    return m.group(1)


def test_setup_requires_token(fresh_client):
    page = fresh_client.get("/admin/setup")
    assert page.status_code == 200
    token = _csrf(page.text)

    r = fresh_client.post(
        "/admin/setup",
        data={
            "username": "admin",
            "password": "goodpass1",
            "confirm_password": "goodpass1",
            "setup_token": "wrong-token",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert r.status_code == 403


def test_setup_works_with_token_then_disabled(fresh_client):
    page = fresh_client.get("/admin/setup")
    token = _csrf(page.text)
    r = fresh_client.post(
        "/admin/setup",
        data={
            "username": "admin",
            "password": "goodpass1",
            "confirm_password": "goodpass1",
            "setup_token": "test-setup-token-xyz",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/admin"

    r2 = fresh_client.get("/admin/setup", follow_redirects=False)
    assert r2.status_code == 303
    assert "/admin/login" in r2.headers.get("location", "")


def test_placeholder_secret_key_refused(monkeypatch):
    from app import config

    monkeypatch.setattr(config.settings, "secret_key", "change-this-to-a-long-random-string-in-production")
    monkeypatch.setattr(config, "_testing", lambda: False)
    with pytest.raises(SystemExit):
        config.enforce_secret_key()


def test_plaintext_password_rejected():
    from app.auth import verify_password, hash_password

    assert verify_password("secret", "secret") is False
    assert verify_password("secret", hash_password("secret")) is True


def test_cascade_delete_messages(client, admin_client):
    from app.database import SessionLocal
    from app.models import Conversation, Message

    db = SessionLocal()
    conv = Conversation(channel="web", visitor_token="tok")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    db.add(Message(conversation_id=conv.id, role="user", content="hi"))
    db.add(Message(conversation_id=conv.id, role="assistant", content="hello"))
    db.commit()
    cid = conv.id
    db.close()

    settings_page = admin_client.get("/admin/settings")
    m = re.search(r'name="csrf_token" value="([^"]+)"', settings_page.text)
    assert m
    csrf = m.group(1)

    r = admin_client.post(
        f"/admin/conversations/{cid}/delete",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303

    db = SessionLocal()
    assert db.query(Conversation).filter(Conversation.id == cid).first() is None
    assert db.query(Message).filter(Message.conversation_id == cid).count() == 0
    db.close()
