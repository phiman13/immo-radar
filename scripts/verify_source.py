"""Run a single source adapter and dump what it found.

Usage:
    python -m scripts.verify_source immoscout24
    python -m scripts.verify_source kleinanzeigen
"""
from __future__ import annotations

import asyncio
import sys

from app.logging_setup import configure_logging
from app.sources.registry import REGISTRY


async def main(name: str) -> None:
    configure_logging()
    cls = REGISTRY.get(name)
    if cls is None:
        print(f"unknown source: {name}\nknown: {', '.join(REGISTRY)}")
        sys.exit(2)

    adapter = cls()
    print(f"== {adapter.name} ==")
    count = 0
    async with adapter:
        async for raw in adapter.fetch():
            count += 1
            print(
                f"  [{count:02d}] {raw.title[:80]} | "
                f"{raw.price_eur or '?'} € | {raw.qm or '?'} m² | "
                f"{raw.rooms or '?'} Zi | {raw.address or '?'} | {raw.url}"
            )
    print(f"\ntotal: {count}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
