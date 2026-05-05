from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import datetime

from bs4 import BeautifulSoup

from app.logging_setup import log
from app.models import PropertyType, RawListing
from app.sources.base import SourceAdapter


class SparkasseImmoSource(SourceAdapter):
    """Sparkasse Immobilien — regional Sparkasse Oberland search around Tutzing."""

    name = "sparkasse_immo"
    base_url = "https://immobilien.sparkasse.de"
    SEARCH_URL = (
        "https://immobilien.sparkasse.de/expose/list?location=82327%20Tutzing&radius=5"
        "&category=buy&type=apartment,house"
    )

    async def fetch(self) -> AsyncIterator[RawListing]:
        assert self.client is not None
        try:
            r = await self.client.get(self.SEARCH_URL)
            r.raise_for_status()
        except Exception as e:
            log.warning("sparkasse_immo.fetch_failed", error=str(e))
            return

        soup = BeautifulSoup(r.text, "lxml")
        for card in soup.select("article, .expose-card, .result-item"):
            link_el = card.select_one("a[href*='/expose/']")
            if not link_el:
                continue
            href = link_el.get("href", "")
            m = re.search(r"/expose/([\w-]+)", href)
            if not m:
                continue
            source_id = m.group(1)
            url = href if href.startswith("http") else f"{self.base_url}{href}"

            title_el = card.select_one("h2, h3, .title")
            title = title_el.get_text(strip=True) if title_el else "Sparkasse-Immobilie"

            text = card.get_text(" ", strip=True)
            yield RawListing(
                source=self.name,
                source_id=source_id,
                url=url,
                title=title,
                price_eur=self._parse_price(text),
                qm=self._parse_qm(text),
                rooms=self._parse_rooms(text),
                property_type=self._guess_type(title + " " + text),
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
