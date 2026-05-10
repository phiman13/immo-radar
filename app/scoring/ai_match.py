from __future__ import annotations

import json

from anthropic import AsyncAnthropic

from app.config import settings
from app.db import Listing
from app.logging_setup import log

_PROMPT = """Du bewertest Immobilienangebote für einen Käufer in Tutzing am Starnberger See.

Suchprofil:
- Budget: {price_min:,} – {price_max:,} €
- Größe: {qm_min}–{qm_max} m²
- Mind. Zimmer: {rooms_min}
- Gewünschte Objektarten: {types}
- Baujahr ab: {year_built_min}
- Lage: PLZ 82327 + {radius} km Radius (Tutzing, Bernried, Feldafing, Pöcking, Possenhofen, Berg)
- Bevorzugt: Seenähe, Bergblick, ruhige Lage, gute S6-Anbindung

Listing:
- Titel: {title}
- Preis: {price} €
- Größe: {qm} m²
- Zimmer: {rooms}
- Adresse: {address}
- Baujahr: {year_built}
- Hausgeld: {hausgeld} €
- Energie: {energie_class} ({energie_kwh} kWh/m²a)
- Risiko-Flags: {risks}
- Plus-Flags: {positives}
- Beschreibung: {description}

Bewerte das Objekt 0–100 (100 = perfekt) und liefere 2-3 prägnante Sätze warum.
Antworte ausschließlich als JSON: {{"score": <int>, "reasoning": "<deutsch, max 250 Zeichen>"}}
"""


async def score_listing(
    listing: Listing, risk_flags: list[str], positive_flags: list[str]
) -> tuple[int, str] | None:
    if not settings.anthropic_api_key:
        log.debug("ai_match.skip_no_key")
        return None

    log.info("ai_match.start", listing_id=listing.id, model=settings.ai_model)

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    prompt = _PROMPT.format(
        price_min=settings.price_min,
        price_max=settings.price_max,
        qm_min=settings.qm_min,
        qm_max=settings.qm_max,
        rooms_min=settings.rooms_min,
        types=", ".join(settings.property_type_list),
        year_built_min=settings.year_built_min,
        radius=settings.search_radius_km,
        title=listing.title or "—",
        price=f"{listing.price_eur:,}".replace(",", ".") if listing.price_eur else "?",
        qm=listing.qm or "?",
        rooms=listing.rooms or "?",
        address=listing.address or "?",
        year_built=listing.year_built or "?",
        hausgeld=listing.hausgeld_eur or "?",
        energie_class=listing.energie_class or "?",
        energie_kwh=listing.energie_kwh or "?",
        risks=", ".join(risk_flags) or "keine",
        positives=", ".join(positive_flags) or "keine",
        description=(listing.description or "")[:1500],
    )

    try:
        msg = await client.messages.create(
            model=settings.ai_model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip() if msg.content else ""
        text = text.strip("`").lstrip("json").strip()
        data = json.loads(text)
        return int(data["score"]), str(data["reasoning"])[:400]
    except Exception as e:
        log.error(
            "ai_match.failed",
            listing_id=listing.id,
            error=str(e),
            error_type=type(e).__name__,
            model=settings.ai_model,
            has_api_key=bool(settings.anthropic_api_key),
        )
        return None
