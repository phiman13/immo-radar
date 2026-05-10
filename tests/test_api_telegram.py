"""Tests for Telegram API endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch


def test_telegram_test_no_config(client, monkeypatch):
    """Without token/chat_id, should return success=False gracefully."""
    from app import config as config_module

    monkeypatch.setattr(config_module.settings, "telegram_bot_token", "")
    monkeypatch.setattr(config_module.settings, "telegram_chat_id", "")

    resp = client.post("/api/telegram/test")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "configured" in data["message"].lower() or "missing" in data["message"].lower()


def test_telegram_test_sends(client, monkeypatch):
    """With valid config, should call Telegram API and return success."""
    from app import config as config_module

    monkeypatch.setattr(config_module.settings, "telegram_bot_token", "fake_token_123")
    monkeypatch.setattr(config_module.settings, "telegram_chat_id", "12345")

    with patch("app.web.api.telegram.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = lambda: None  # Synchronous method
        mock_client.post = AsyncMock(return_value=mock_response)

        resp = client.post("/api/telegram/test")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "successfully" in data["message"].lower()

    # Verify the client was called with correct URL and payload
    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert "fake_token_123" in call_args[0][0]
    assert call_args[1]["json"]["chat_id"] == "12345"


def test_telegram_test_api_error(client, monkeypatch):
    """On Telegram API error, should return success=False with status code."""
    from app import config as config_module

    monkeypatch.setattr(config_module.settings, "telegram_bot_token", "fake_token")
    monkeypatch.setattr(config_module.settings, "telegram_chat_id", "12345")

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        # Mock a 401 Unauthorized response
        mock_response = AsyncMock()
        mock_response.status_code = 401

        def raise_http_error():
            raise Exception("401 Client Error: Unauthorized")

        mock_response.raise_for_status = mock_response.raise_for_status
        mock_client.post = AsyncMock(side_effect=Exception("401 Client Error: Unauthorized"))

        resp = client.post("/api/telegram/test")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "error" in data["message"].lower()
