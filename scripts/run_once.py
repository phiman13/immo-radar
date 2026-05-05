"""One-shot crawler run for testing. Usage: python -m scripts.run_once"""
from __future__ import annotations

import asyncio

from app.db import init_db
from app.enrich import enrich_pending
from app.logging_setup import configure_logging, log
from app.notify.telegram import notify_new_listing
from app.pipeline import run_all


async def main() -> None:
    configure_logging()
    init_db()
    new = await run_all()
    log.info("run_once.found_new", count=len(new))
    await enrich_pending(limit=50)
    for listing in new:
        await notify_new_listing(listing)


if __name__ == "__main__":
    asyncio.run(main())
