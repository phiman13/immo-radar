from __future__ import annotations

import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.enrich import enrich_pending
from app.logging_setup import log
from app.notify.telegram import notify_new_listing
from app.pipeline import run_all


async def poll_and_notify() -> None:
    log.info("scheduler.poll_start")
    new_listings = await run_all()
    if not new_listings:
        log.info("scheduler.poll_no_new")
        return

    log.info("scheduler.poll_new", count=len(new_listings))

    # Enrich first so notifications include AI score + risk flags
    for listing in new_listings:
        try:
            from app.enrich import enrich_listing

            await enrich_listing(listing.id)
        except Exception as e:
            log.error("scheduler.enrich_failed", id=listing.id, error=str(e))

    # Reload from DB after enrichment
    from app.db import Listing, SessionLocal

    with SessionLocal() as session:
        ids = [listing.id for listing in new_listings]
        fresh = session.query(Listing).filter(Listing.id.in_(ids)).all()
        for listing in fresh:
            try:
                await notify_new_listing(listing)
            except Exception as e:
                log.error("scheduler.notify_failed", id=listing.id, error=str(e))


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Berlin")
    scheduler.add_job(
        poll_and_notify,
        trigger=IntervalTrigger(minutes=settings.poll_interval_minutes),
        id="poll_and_notify",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        enrich_pending,
        trigger=IntervalTrigger(minutes=settings.detail_fetch_interval_minutes),
        id="enrich_pending",
        max_instances=1,
        coalesce=True,
    )
    return scheduler


async def run_forever() -> None:
    sched = build_scheduler()
    sched.start()
    log.info("scheduler.started", interval_min=settings.poll_interval_minutes)
    # Run once immediately
    await poll_and_notify()
    while True:
        await asyncio.sleep(3600)
