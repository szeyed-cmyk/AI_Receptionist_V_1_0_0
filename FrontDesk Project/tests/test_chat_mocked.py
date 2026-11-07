"""Chat endpoint with mocked AI."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch


def test_chat_with_mocked_ai(client):
    with patch("app.chat_service.generate_reply", new_callable=AsyncMock) as mock_reply:
        mock_reply.return_value = "Hello from mock"
        r = client.post("/chat", data={"message": "Hi there"})
        assert r.status_code == 200
        data = r.json()
        assert data["reply"] == "Hello from mock"
        assert "conversation_id" in data
        mock_reply.assert_awaited()
