from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import datetime

from bs4 import BeautifulSoup

from app.logging_setup import log
from app.models import PropertyType, RawListing
from app.sources.base import SourceAdapter


class StarnbergImmoSource(SourceAdapter):
    """Claudia Bader / starnberg-immobilien.de (= starnbergersee-immobilien.de).

    Verified: site uses sub-pages `/Haeuser-zum-Kauf.htm` and `/Immobilien-zum-Kauf.htm`.
    Each listing is on its own .htm page. Site is light-traffic, no JS.
    """

    name = "starnberg_bader"
    base_url = "https://www.starnberg-immobilien.de"
    SEARCH_URLS = [
        "https://www.starnberg-immobilien.de/Immobilien-zum-Kauf.htm",
        "https://www.starnberg-immobilien.de/Haeuser-zum-Kauf.htm",
    ]

    async def fetch(self) -> AsyncIterator[RawListing]:
        assert self.client is not None
        seen: set[str] = set()
        for url in self.SEARCH_URLS:
            try:
                r = await self.client.get(url)
                r.raise_for_status()
            except Exception as e:
                log.warning("starnberg_bader.fetch_failed", url=url, error=str(e))
                continue

            soup = BeautifulSoup(r.text, "lxml")
            # Listing detail pages typically end in .htm and aren't navigation
            for a in soup.find_all("a", href=True):
                h = a["href"]
                if not h.endswith(".htm"):
                    continue
                # Skip top-level navigation pages
                if any(kw in h for kw in ("/Impressum", "/Datenschutz", "/Kontakt", "/AGB", "Service")):
                    continue
                if "zum-Kauf" in h or "zur-Miete" in h or "Verkauf" in h:
                    continue
                # Plausible listing URLs are deeper than top-level
                if h.count("/") < 2 and not h.startswith("/"):
                    continue

                full = h if h.startswith("http") else f"{self.base_url}{h if h.startswith('/') else '/' + h}"
                if full in seen:
                    continue
                seen.add(full)

                title = a.get_text(" ", strip=True)
                if len(title) < 8:  # too short to be a meaningful title
                    continue

                # Extract from surrounding card if available
                card = a
                for _ in range(4):
                    if card.parent is None:
                        break
                    card = card.parent

                text = re.sub(r"\s+", " ", card.get_text(" ", strip=True))[:2000]

                # Hard filter: only accept links whose card text actually looks like a listing
                if not re.search(r"\d[\d.,]*\s*(?:€|EUR|m²|Zimmer|Zi\b)", text):
                    continue
                # Skip About/Contact/Imprint pages
                if any(skip in title.lower() for skip in ("über uns", "kontakt", "impressum", "datenschutz", "team", "leistungen", "service")):
                    continue

                # Generate stable id from URL
                source_id = re.sub(r"[^a-zA-Z0-9]+", "-", full.split("/")[-1].replace(".htm", ""))[:64]

                yield RawListing(
                    source=self.name,
                    source_id=source_id,
                    url=full,
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
                    "Starnberg", "Seeshaupt", "Weilheim", "Iffeldorf", "Andechs", "Herrsching"):
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
