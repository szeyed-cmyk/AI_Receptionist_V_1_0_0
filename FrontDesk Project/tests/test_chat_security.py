"""Public chat ownership, rate limit, and message length tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch


def test_chat_binds_to_session_and_rejects_foreign_id(client):
    with patch("app.chat_service.generate_reply", new_callable=AsyncMock) as mock_reply:
        mock_reply.return_value = "Hello"
        r = client.post("/chat", data={"message": "Hi"})
        assert r.status_code == 200
        mine = r.json()["conversation_id"]

        # Guess a different sequential id
        foreign = mine + 99
        r2 = client.post(
            "/chat",
            data={"message": "Hack?", "conversation_id": str(foreign)},
        )
        assert r2.status_code == 403


def test_chat_ignores_client_id_when_matching_session(client):
    with patch("app.chat_service.generate_reply", new_callable=AsyncMock) as mock_reply:
        mock_reply.return_value = "Hello"
        r = client.post("/chat", data={"message": "Hi"})
        assert r.status_code == 200
        cid = r.json()["conversation_id"]

        r2 = client.post(
            "/chat",
            data={"message": "Again", "conversation_id": str(cid)},
        )
        assert r2.status_code == 200
        assert r2.json()["conversation_id"] == cid


def test_chat_message_too_long_rejected(client):
    with patch("app.chat_service.generate_reply", new_callable=AsyncMock) as mock_reply:
        mock_reply.return_value = "ok"
        huge = "x" * 2001
        r = client.post("/chat", data={"message": huge})
        # FastAPI Form max_length → 422, or our manual check → 413
        assert r.status_code in {413, 422}


def test_chat_rate_limit(client, monkeypatch):
    monkeypatch.setenv("CHAT_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("CHAT_WINDOW_SEC", "60")
    # Reload settings / rate limiter by patching settings values
    from app import config as cfg

    monkeypatch.setattr(cfg.settings, "chat_max_attempts", 3)
    monkeypatch.setattr(cfg.settings, "chat_window_sec", 60)

    # Clear previous chat attempts
    from app import security as sec

    sec._ATTEMPTS.clear()

    with patch("app.chat_service.generate_reply", new_callable=AsyncMock) as mock_reply:
        mock_reply.return_value = "ok"
        codes = []
        for i in range(5):
            r = client.post("/chat", data={"message": f"msg {i}"})
            codes.append(r.status_code)
        assert 429 in codes, codes
