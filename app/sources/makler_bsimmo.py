from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import datetime

from bs4 import BeautifulSoup

from app.logging_setup import log
from app.models import PropertyType, RawListing
from app.sources.base import SourceAdapter


class BsImmoSource(SourceAdapter):
    """BS Immobilien (Bergmann) — listings on bs-immo.de link to ImmoScout24 exposes.

    Strategy: scrape bs-immo.de page, extract ImmoScout24 expose URLs, and surrounding
    text for title/price/qm. We don't fetch ImmoScout itself (bot-blocked) — the
    bs-immo.de page already contains enough metadata.
    """

    name = "bs_immo"
    base_url = "https://www.bs-immo.de"
    SEARCH_URL = "https://www.bs-immo.de"

    async def fetch(self) -> AsyncIterator[RawListing]:
        assert self.client is not None
        try:
            r = await self.client.get(self.SEARCH_URL)
            r.raise_for_status()
        except Exception as e:
            log.warning("bs_immo.fetch_failed", error=str(e))
            return

        soup = BeautifulSoup(r.text, "lxml")
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            h = a["href"]
            m = re.match(r"https?://(?:www\.)?immobilienscout24\.de/expose/(\d+)", h)
            if not m:
                continue
            source_id = m.group(1)
            if source_id in seen:
                continue
            seen.add(source_id)

            # Find surrounding card text
            card = a
            for _ in range(5):
                if card.parent is None:
                    break
                card = card.parent

            text = re.sub(r"\s+", " ", card.get_text(" ", strip=True))[:2000]
            # Try to find a real title in the surrounding card (h2/h3 or first long text node)
            title = ""
            for tag in ("h2", "h3", "h4"):
                t_el = card.find(tag)
                if t_el:
                    candidate = t_el.get_text(" ", strip=True)
                    if len(candidate) > 8:
                        title = candidate
                        break
            if not title:
                # Fallback: longest plausible text snippet in the card
                snippets = [s.strip() for s in re.split(r"[\n.|]", text) if 15 < len(s.strip()) < 120]
                title = snippets[0] if snippets else "BS-Immo Objekt"

            yield RawListing(
                source=self.name,
                source_id=source_id,
                url=h.split("?")[0].split("#")[0],
                title=title[:200],
                description=text,
                price_eur=self._parse_price(text),
                qm=self._parse_qm(text),
                rooms=self._parse_rooms(text),
                address=self._parse_location(text),
                property_type=self._guess_type(title + " " + text[:200]),
                fetched_at=datetime.utcnow(),
            )

    @staticmethod
    def _parse_price(t: str) -> int | None:
        m = re.search(r"([\d\.]{4,})\s*(?:€|EUR)", t)
        if not m:
            return None
        try:
            return int(m.group(1).replace(".", ""))
        except ValueError:
            return None

    @staticmethod
    def _parse_qm(t: str) -> float | None:
        m = re.search(r"([\d.,]+)\s*m²", t)
        if not m:
            return None
        try:
            return float(m.group(1).replace(".", "").replace(",", "."))
        except ValueError:
            return None

    @staticmethod
    def _parse_rooms(t: str) -> float | None:
        m = re.search(r"([\d,]+)\s*Zi", t)
        if not m:
            return None
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            return None

    @staticmethod
    def _parse_location(t: str) -> str | None:
        m = re.search(r"\b(\d{5})\s+([A-ZÄÖÜ][a-zäöüß\-]+)", t)
        if m:
            return f"{m.group(1)} {m.group(2)}"
        for ort in ("Tutzing", "Feldafing", "Pöcking", "Bernried", "Possenhofen", "Berg",
                    "Starnberg", "Seeshaupt", "Weilheim", "Iffeldorf", "Andechs", "Herrsching",
                    "Diessen", "Pähl", "Wielenbach"):
            if ort in t:
                return ort
        return None

    @staticmethod
    def _guess_type(t: str) -> PropertyType:
        s = t.lower()
        if "doppelhaush" in s:
            return PropertyType.DOPPELHAUSHAELFTE
        if "reihenhaus" in s:
            return PropertyType.REIHENHAUS
        if "haus" in s or "villa" in s:
            return PropertyType.HAUS
        if "wohnung" in s:
            return PropertyType.WOHNUNG
        return PropertyType.UNKNOWN
