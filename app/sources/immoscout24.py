from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import datetime

from bs4 import BeautifulSoup

from app.config import settings
from app.logging_setup import log
from app.models import PropertyType, RawListing
from app.sources.base import SourceAdapter
from app.sources.browser import fetch_html


class ImmoScout24Source(SourceAdapter):
    """ImmoScout24 — bot-protected, requires Playwright.

    URL pattern: searches by Geo-Polygon. We use the radius-around-Tutzing search.
    """

    name = "immoscout24"
    base_url = "https://www.immobilienscout24.de"
    requires_browser = True

    SEARCH_URL = (
        "https://www.immobilienscout24.de/Suche/de/bayern/starnberg-kreis/tutzing/"
        "wohnung-haus-kaufen?enteredFrom=result_list"
    )

    async def fetch(self) -> AsyncIterator[RawListing]:
        try:
            html = await fetch_html(self.SEARCH_URL)
        except Exception as e:
            log.warning("immoscout24.fetch_failed", error=str(e))
            return

        soup = BeautifulSoup(html, "lxml")
        cards = soup.select("article[data-id], li.result-list__listing")

        for card in cards:
            source_id = card.get("data-id") or card.get("data-obid") or ""
            if not source_id:
                link = card.select_one("a[href*='/expose/']")
                if link and link.get("href"):
                    m = re.search(r"/expose/(\d+)", link["href"])
                    if m:
                        source_id = m.group(1)
            if not source_id:
                continue

            url = f"{self.base_url}/expose/{source_id}"
            title_el = card.select_one("h2, h3, .result-list-entry__brand-title")
            title = title_el.get_text(strip=True) if title_el else "Wohnung"

            price_text = self._text(card, "[data-is24-qa='attributes'] dd, .result-list-entry__primary-criterion dd")
            price = self._parse_price(price_text)

            qm = self._parse_qm(self._all_text(card))
            rooms = self._parse_rooms(self._all_text(card))

            address_el = card.select_one(".result-list-entry__address, .result-list-entry__map-link")
            address = address_el.get_text(strip=True) if address_el else None

            yield RawListing(
                source=self.name,
                source_id=str(source_id),
                url=url,
                title=title,
                price_eur=price,
                qm=qm,
                rooms=rooms,
                address=address,
                property_type=self._guess_type(title),
                fetched_at=datetime.utcnow(),
            )

    @staticmethod
    def _text(node, selector: str) -> str:
        el = node.select_one(selector)
        return el.get_text(" ", strip=True) if el else ""

    @staticmethod
    def _all_text(node) -> str:
        return node.get_text(" ", strip=True)

    @staticmethod
    def _parse_price(text: str) -> int | None:
        m = re.search(r"([\d.]+)\s*(?:€|EUR)", text)
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
        m = re.search(r"([\d,]+)\s*(?:Zi\.?|Zimmer)", text)
        if not m:
            return None
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            return None

    @staticmethod
    def _guess_type(title: str) -> PropertyType:
        t = title.lower()
        if "doppelhaush" in t:
            return PropertyType.DOPPELHAUSHAELFTE
        if "reihenhaus" in t:
            return PropertyType.REIHENHAUS
        if "haus" in t or "villa" in t:
            return PropertyType.HAUS
        if "wohnung" in t or "etagenwhg" in t:
            return PropertyType.WOHNUNG
        if "grundst" in t:
            return PropertyType.GRUNDSTUECK
        return PropertyType.UNKNOWN
