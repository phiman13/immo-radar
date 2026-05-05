from __future__ import annotations

import asyncio

from app.db import init_db
from app.logging_setup import configure_logging, log
from app.scheduler import run_forever


async def main() -> None:
    configure_logging()
    init_db()
    log.info("immo_radar.start")
    await run_forever()


if __name__ == "__main__":
    asyncio.run(main())
