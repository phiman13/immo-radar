from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import datetime

from bs4 import BeautifulSoup

from app.logging_setup import log
from app.models import PropertyType, RawListing
from app.sources.base import SourceAdapter


class RiedelSource(SourceAdapter):
    """Riedel Immobilien — verified live: /angebote/kauf/ uses
    `.listEntryObject-immoObject` for each listing card."""

    name = "riedel"
    base_url = "https://www.riedel-immobilien.de"
    SEARCH_URL = "https://www.riedel-immobilien.de/angebote/kauf/"

    async def fetch(self) -> AsyncIterator[RawListing]:
        assert self.client is not None
        try:
            r = await self.client.get(self.SEARCH_URL)
            r.raise_for_status()
        except Exception as e:
            log.warning("riedel.fetch_failed", error=str(e))
            return

        soup = BeautifulSoup(r.text, "lxml")
        for card in soup.select(".listEntry.listEntryObject-immoObject_var, .listEntryObject-immoObject"):
            link_el = card.select_one("a[href]")
            if not link_el:
                continue
            href = link_el.get("href", "")
            url = href if href.startswith("http") else f"{self.base_url}{href if href.startswith('/') else '/' + href}"

            # Source ID from URL slug
            slug_match = re.search(r"/objekt/([^/?#]+)", url) or re.search(r"/expose/([^/?#]+)", url)
            source_id = slug_match.group(1) if slug_match else re.sub(r"[^a-z0-9]+", "-", url.lower()).strip("-")[-64:]

            title_el = card.select_one(".listDefaultTitle, h2, h3, .immo-title")
            title = title_el.get_text(" ", strip=True) if title_el else "Riedel-Objekt"

            text = re.sub(r"\s+", " ", card.get_text(" ", strip=True))

            yield RawListing(
                source=self.name,
                source_id=source_id,
                url=url,
                title=title[:200],
                description=text[:2000],
                price_eur=self._parse_price(text),
                qm=self._parse_qm(text),
                rooms=self._parse_rooms(text),
                address=self._parse_location(text),
                property_type=self._guess_type(title + " " + text[:200]),
                fetched_at=datetime.utcnow(),
            )

    @staticmethod
    def _parse_price(text: str) -> int | None:
        m = re.search(r"([\d\.]{4,})\s*€", text)
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
    def _parse_location(text: str) -> str | None:
        # Try to extract a place name pattern
        m = re.search(
            r"\b(\d{5})\s+([A-ZÄÖÜ][a-zäöüß\-]+(?:\s+[A-ZÄÖÜ][a-zäöüß\-]+)?)",
            text,
        )
        if m:
            return f"{m.group(1)} {m.group(2)}"
        for ort in ("Tutzing", "Feldafing", "Pöcking", "Bernried", "Possenhofen", "Berg", "Seeshaupt"):
            if ort in text:
                return ort
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
        if "wohnung" in t or "etw" in t:
            return PropertyType.WOHNUNG
        if "grundst" in t:
            return PropertyType.GRUNDSTUECK
        return PropertyType.UNKNOWN
