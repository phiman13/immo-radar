"""Send a test message to your Telegram chat. Run after setting CHAT_ID in .env."""
from __future__ import annotations

import asyncio

from app.config import settings
from app.notify.telegram import send_telegram


async def main() -> None:
    if not settings.telegram_chat_id:
        print("ERROR: TELEGRAM_CHAT_ID not set in .env")
        return
    ok = await send_telegram(
        "<b>🏠 Immo-Radar Tutzing</b>\nTest-Nachricht — alles funktioniert.",
    )
    print("OK" if ok else "FAIL — siehe Log oben")


if __name__ == "__main__":
    asyncio.run(main())
