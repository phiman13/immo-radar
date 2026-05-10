from __future__ import annotations

from datetime import datetime

import httpx

from app.config import settings
from app.db import Listing, SessionLocal
from app.logging_setup import log
from app.settings_service import get_setting


async def send_telegram(text: str, image_url: str | None = None, buttons: list[dict] | None = None) -> bool:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        log.debug("telegram.skip_no_credentials")
        return False

    base = f"https://api.telegram.org/bot{settings.telegram_bot_token}"
    payload: dict = {
        "chat_id": settings.telegram_chat_id,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": [buttons]}

    async with httpx.AsyncClient(timeout=15.0) as client:
        if image_url:
            payload["photo"] = image_url
            payload["caption"] = text[:1024]
            r = await client.post(f"{base}/sendPhoto", json=payload)
        else:
            payload["text"] = text[:4096]
            r = await client.post(f"{base}/sendMessage", json=payload)

    if r.status_code != 200:
        log.warning("telegram.send_failed", status=r.status_code, body=r.text[:200])
        return False
    return True


def _format_listing(listing: Listing) -> str:
    parts = [f"<b>🏠 {listing.title}</b>"]
    sub = []
    if listing.price_eur:
        sub.append(f"💰 {listing.price_eur:,.0f} €".replace(",", "."))
    if listing.qm:
        sub.append(f"📐 {listing.qm:.0f} m²")
    if listing.rooms:
        sub.append(f"🛏 {listing.rooms:g} Zi")
    if listing.price_eur and listing.qm:
        sub.append(f"= {listing.price_eur / listing.qm:,.0f} €/m²".replace(",", "."))
    if sub:
        parts.append(" · ".join(sub))

    meta = []
    if listing.address:
        meta.append(f"📍 {listing.address}")
    if listing.year_built:
        meta.append(f"Bj. {listing.year_built}")
    if listing.energie_class:
        meta.append(f"Energie {listing.energie_class}")
    if meta:
        parts.append(" · ".join(meta))

    if listing.ai_score is not None:
        emoji = "🟢" if listing.ai_score >= 75 else ("🟡" if listing.ai_score >= 50 else "🔴")
        parts.append(f"{emoji} <b>Match {listing.ai_score}/100</b>")
        if listing.ai_reasoning:
            parts.append(f"<i>{listing.ai_reasoning[:300]}</i>")

    if listing.risk_flags:
        parts.append("⚠️ " + ", ".join(listing.risk_flags))

    parts.append(f"\n<a href='{listing.url}'>→ Exposé öffnen ({listing.source})</a>")
    return "\n".join(parts)


async def notify_new_listing(listing: Listing) -> None:
    threshold = get_setting("score_threshold")
    if threshold is not None and listing.lage_score is not None:
        if listing.lage_score < threshold:
            log.info(
                "notify.skipped_below_threshold",
                id=listing.id,
                score=listing.lage_score,
                threshold=threshold,
            )
            return

    text = _format_listing(listing)
    image = listing.images[0] if listing.images else None
    buttons = [{"text": "🔗 Exposé", "url": listing.url}]

    ok = await send_telegram(text, image_url=image, buttons=buttons)
    if ok:
        with SessionLocal() as session:
            session.query(Listing).filter(Listing.id == listing.id).update({"notified_at": datetime.utcnow()})
            session.commit()
