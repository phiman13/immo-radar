from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import datetime

from bs4 import BeautifulSoup

from app.logging_setup import log
from app.models import PropertyType, RawListing
from app.sources.base import SourceAdapter


class ImmoweltSource(SourceAdapter):
    name = "immowelt"
    base_url = "https://www.immowelt.de"

    SEARCH_URL = (
        "https://www.immowelt.de/classified-search?distributionTypes=Buy&estateTypes=House,Apartment"
        "&locations=AD08DE8587&order=DateDesc"
    )

    async def fetch(self) -> AsyncIterator[RawListing]:
        assert self.client is not None
        try:
            r = await self.client.get(self.SEARCH_URL)
            r.raise_for_status()
        except Exception as e:
            log.warning("immowelt.fetch_failed", error=str(e))
            return

        soup = BeautifulSoup(r.text, "lxml")
        cards = soup.select("a[data-test='card-link'], a[href*='/expose/']")
        seen: set[str] = set()

        for card in cards:
            href = card.get("href") or ""
            m = re.search(r"/expose/([a-zA-Z0-9]+)", href)
            if not m:
                continue
            source_id = m.group(1)
            if source_id in seen:
                continue
            seen.add(source_id)

            url = href if href.startswith("http") else f"{self.base_url}{href}"
            text = card.get_text(" ", strip=True)
            yield RawListing(
                source=self.name,
                source_id=source_id,
                url=url,
                title=text[:200] or "Immowelt-Objekt",
                price_eur=self._parse_price(text),
                qm=self._parse_qm(text),
                rooms=self._parse_rooms(text),
                property_type=self._guess_type(text),
                fetched_at=datetime.utcnow(),
            )

    @staticmethod
    def _parse_price(text: str) -> int | None:
        m = re.search(r"([\d.]+)\s*€", text)
        if not m:
            return None
        try:
            return int(m.group(1).replace(".", ""))
        except ValueError:
            return None

    @staticmethod
    def _parse_qm(text: str) -> float | None:
        m = re.search(r"([\d.,]+)\s*m²", text)
        if not m:
            return None
        try:
            return float(m.group(1).replace(".", "").replace(",", "."))
        except ValueError:
            return None

    @staticmethod
    def _parse_rooms(text: str) -> float | None:
        m = re.search(r"([\d,]+)\s*Zi", text)
        if not m:
            return None
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            return None

    @staticmethod
    def _guess_type(text: str) -> PropertyType:
        t = text.lower()
        if "doppelhaush" in t:
            return PropertyType.DOPPELHAUSHAELFTE
        if "reihenhaus" in t:
            return PropertyType.REIHENHAUS
        if "haus" in t or "villa" in t:
            return PropertyType.HAUS
        if "wohnung" in t:
            return PropertyType.WOHNUNG
        return PropertyType.UNKNOWN
