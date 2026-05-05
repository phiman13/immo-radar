from __future__ import annotations

from sqlalchemy import select

from app.db import Listing, SessionLocal
from app.logging_setup import log
from app.scoring.ai_match import score_listing
from app.scoring.lage import classify_ortsteil, distance_to_sbahn_km
from app.scoring.risk import extract_flags


async def enrich_listing(listing_id: int) -> None:
    """Run risk extraction, lage classification and AI scoring on a single listing."""
    with SessionLocal() as session:
        listing = session.get(Listing, listing_id)
        if listing is None:
            return

        text = " ".join(filter(None, [listing.title, listing.description]))
        risks, positives = extract_flags(text)
        listing.risk_flags = risks

        if listing.lat is not None and listing.lon is not None:
            listing.ortsteil = listing.ortsteil or classify_ortsteil(listing.lat, listing.lon)

        ai = await score_listing(listing, risks, positives)
        if ai is not None:
            listing.ai_score, listing.ai_reasoning = ai

        session.commit()
        log.info(
            "enrich.done",
            id=listing.id,
            risks=risks,
            positives=positives,
            ai_score=listing.ai_score,
        )


async def enrich_pending(limit: int = 20) -> int:
    """Enrich listings without AI score yet."""
    count = 0
    with SessionLocal() as session:
        ids = session.scalars(
            select(Listing.id).where(Listing.ai_score.is_(None)).limit(limit)
        ).all()

    for lid in ids:
        try:
            await enrich_listing(lid)
            count += 1
        except Exception as e:
            log.error("enrich.failed", id=lid, error=str(e))
    return count
