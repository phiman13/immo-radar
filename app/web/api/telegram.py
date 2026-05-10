from __future__ import annotations

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings

router = APIRouter()


class TelegramTestResult(BaseModel):
    success: bool
    message: str


@router.post("/test", response_model=TelegramTestResult)
async def test_telegram():
    """Send a test message to the configured Telegram chat."""
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return TelegramTestResult(
            success=False,
            message="Telegram not configured (missing bot token or chat ID)",
        )

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": "✅ immo-radar Test-Nachricht — API funktioniert.",
        "parse_mode": "HTML",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return TelegramTestResult(success=True, message="Test message sent successfully")
    except httpx.HTTPStatusError as e:
        return TelegramTestResult(success=False, message=f"Telegram API error: {e.response.status_code}")
    except Exception as e:
        return TelegramTestResult(success=False, message=f"Error: {str(e)}")
