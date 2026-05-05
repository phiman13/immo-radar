"""Fetch your Telegram chat_id from the bot's getUpdates feed.

Prerequisite: open Telegram, find your bot, send it any message.
Then run: python -m scripts.get_chat_id
"""
from __future__ import annotations

import sys

import httpx

from app.config import settings


def main() -> None:
    if not settings.telegram_bot_token:
        print("ERROR: TELEGRAM_BOT_TOKEN not set in .env")
        sys.exit(1)

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/getUpdates"
    r = httpx.get(url, timeout=15)
    if r.status_code != 200:
        print(f"ERROR HTTP {r.status_code}: {r.text}")
        sys.exit(2)

    data = r.json()
    if not data.get("ok"):
        print(f"ERROR: {data}")
        sys.exit(3)

    updates = data.get("result", [])
    if not updates:
        print(
            "Keine Updates. Schreibe dem Bot mindestens eine Nachricht "
            "in Telegram und führe das Skript erneut aus."
        )
        sys.exit(0)

    seen_chats: dict[int, str] = {}
    for upd in updates:
        msg = upd.get("message") or upd.get("edited_message") or {}
        chat = msg.get("chat", {})
        if "id" in chat:
            who = (
                chat.get("username")
                or f"{chat.get('first_name','')} {chat.get('last_name','')}".strip()
                or chat.get("title")
                or "?"
            )
            seen_chats[chat["id"]] = who

    print("Gefundene Chats:")
    for cid, who in seen_chats.items():
        print(f"  TELEGRAM_CHAT_ID={cid}    ({who})")
    print("\n→ Trag den passenden Wert in .env als TELEGRAM_CHAT_ID ein.")


if __name__ == "__main__":
    main()
