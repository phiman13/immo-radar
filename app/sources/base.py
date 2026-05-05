from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

import httpx

from app.models import RawListing


class SourceAdapter(ABC):
    """Base class for every immo source.

    Implement `fetch()` to yield RawListing objects. Adapters should be
    polite (respect rate limits, set a real User-Agent, back off on errors).
    """

    name: str = "base"
    base_url: str = ""
    requires_browser: bool = False

    def __init__(self) -> None:
        self.client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "SourceAdapter":
        self.client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/130.0 Safari/537.36"
                ),
                "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
            },
        )
        return self

    async def __aexit__(self, *_: object) -> None:
        if self.client:
            await self.client.aclose()

    @abstractmethod
    async def fetch(self) -> AsyncIterator[RawListing]:
        """Yield RawListings matching the configured search profile."""
        if False:
            yield  # type: ignore[unreachable]
