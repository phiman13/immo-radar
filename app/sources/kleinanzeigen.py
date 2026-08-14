from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import datetime

from bs4 import BeautifulSoup

from app.logging_setup import log
from app.models import PropertyType, RawListing
from app.sources.base import SourceAdapter
from app.sources.browser import fetch_html


class KleinanzeigenSource(SourceAdapter):
    """kleinanzeigen.de — Cloudflare-protected, browser-fetched."""

    name = "kleinanzeigen"
    base_url = "https://www.kleinanzeigen.de"
    requires_browser = True

    # PLZ 82327 prefix — kleinanzeigen sometimes ignores location filters and
    # returns nationwide results, so the pipeline-level in_search_area()
    # geocoded radius check is the real safety net. We hit two categories:
    # Wohnung kaufen + Haus kaufen.
    SEARCH_URLS = [
        "https://www.kleinanzeigen.de/s-haus-kaufen/82327/c208",
        "https://www.kleinanzeigen.de/s-wohnung-kaufen/82327/c196",
    ]
    SEARCH_URL = SEARCH_URLS[0]  # backwards-compat for verify_source.py

    async def fetch(self) -> AsyncIterator[RawListing]:
        seen_ids: set[str] = set()
        for search_url in self.SEARCH_URLS:
            try:
                html = await fetch_html(search_url, wait_selector="article.aditem")
            except Exception as e:
                log.warning("kleinanzeigen.fetch_failed", url=search_url, error=str(e))
                continue

            soup = BeautifulSoup(html, "lxml")
            for article in soup.select("article.aditem"):
                source_id = article.get("data-adid") or ""
                if not source_id or source_id in seen_ids:
                    continue
                seen_ids.add(source_id)

                link_el = article.select_one("a.ellipsis")
                href = link_el.get("href") if link_el else None
                if not href:
                    continue
                listing_url = href if href.startswith("http") else f"{self.base_url}{href}"

                title_el = article.select_one("a.ellipsis, .text-module-begin a")
                title = title_el.get_text(strip=True) if title_el else "Kleinanzeige"

                price_text = self._text(article, ".aditem-main--middle--price-shipping--price")
                price = self._parse_price(price_text)

                details_text = self._text(article, ".aditem-main--bottom, .aditem-details")

                location_el = article.select_one(".aditem-main--top--left")
                raw_loc = location_el.get_text(" ", strip=True) if location_el else ""
                location = re.sub(r"\s+", " ", raw_loc).strip()

                yield RawListing(
                    source=self.name,
                    source_id=source_id,
                    url=listing_url,
                    title=title,
                    price_eur=price,
                    qm=self._parse_qm(details_text + " " + title),
                    rooms=self._parse_rooms(details_text + " " + title),
                    address=location or None,
                    property_type=self._guess_type(title),
                    fetched_at=datetime.utcnow(),
                )

    @staticmethod
    def _text(node, selector: str) -> str:
        el = node.select_one(selector)
        return el.get_text(" ", strip=True) if el else ""

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
        m = re.search(r"([\d,]+)\s*(?:Zi|Zimmer)", text)
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
        if "wohnung" in t or "etw" in t:
            return PropertyType.WOHNUNG
        if "grundst" in t:
            return PropertyType.GRUNDSTUECK
        return PropertyType.UNKNOWN
