from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import datetime

from bs4 import BeautifulSoup

from app.logging_setup import log
from app.models import PropertyType, RawListing
from app.sources.base import SourceAdapter


class Tutzing24Source(SourceAdapter):
    """tutzing24.de — local Tutzing classifieds aggregator.

    Page often empty (small town), but anything posted is by-design Tutzing-relevant.
    We crawl the immobilien-angebote page, treat each non-nav link as a candidate.
    """

    name = "tutzing24"
    base_url = "https://www.tutzing24.de"
    SEARCH_URL = "https://www.tutzing24.de/kleinanzeigen/kleinanzeigen-immobilien-angebote.htm"

    async def fetch(self) -> AsyncIterator[RawListing]:
        assert self.client is not None
        try:
            r = await self.client.get(self.SEARCH_URL)
            r.raise_for_status()
        except Exception as e:
            log.warning("tutzing24.fetch_failed", error=str(e))
            return

        soup = BeautifulSoup(r.text, "lxml")
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            h = a["href"]
            text = a.get_text(" ", strip=True)
            # Heuristic: listing links are individual ad pages, not menu/cat pages
            if not h or len(text) < 12:
                continue
            # skip menu/categories
            if any(skip in h for skip in (
                "kleinanzeigen-stellengesuche", "kleinanzeigen-stellenangebote",
                "kleinanzeigen-verkaeufe", "kleinanzeigen-gesuche", "kleinanzeigen-verschiedenes",
                "kleinanzeige-aufgeben", "kleinanzeigen-immobilien-gesuche",
                "kleinanzeigen-immobilien-angebote.htm", "/tourismus", "/wirtschaft",
                "/gemeinde", "/kontakt", "/impressum", "/datenschutz", "mailto:", "tel:",
            )):
                continue
            # Listing details typically at /kleinanzeigen/<slug>-<id>.htm
            if "kleinanzeigen" not in h:
                continue
            full = h if h.startswith("http") else f"{self.base_url}{h if h.startswith('/') else '/' + h}"
            if full in seen:
                continue
            seen.add(full)

            source_id = re.sub(r"[^a-z0-9]+", "-", h.lower()).strip("-")[-64:]

            # Surrounding card text for price/qm/location
            card = a
            for _ in range(4):
                if card.parent is None:
                    break
                card = card.parent
            ctext = re.sub(r"\s+", " ", card.get_text(" ", strip=True))[:1500]

            # Hard filter: must have price/qm/Zimmer signal in the card text — otherwise it's nav/header
            if not re.search(r"\d[\d.,]*\s*(?:€|EUR|m²|Zimmer|Zi\b)", ctext):
                continue
            # Skip generic nav titles
            if text.lower().strip() in ("kleinanzeigen", "immobilien", "angebote", "anzeigen", "alle anzeigen"):
                continue

            yield RawListing(
                source=self.name,
                source_id=source_id,
                url=full,
                title=text[:200],
                description=ctext,
                price_eur=self._parse_price(ctext),
                qm=self._parse_qm(ctext),
                rooms=self._parse_rooms(ctext),
                # tutzing24.de listings are by definition Tutzing-area
                address=self._parse_location(ctext) or "Tutzing",
                property_type=self._guess_type(text + " " + ctext[:200]),
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
        for ort in ("Tutzing", "Feldafing", "Pöcking", "Bernried", "Possenhofen"):
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
        if "grundst" in s:
            return PropertyType.GRUNDSTUECK
        return PropertyType.UNKNOWN
