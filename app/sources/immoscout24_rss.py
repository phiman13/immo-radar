from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import datetime

import feedparser
from bs4 import BeautifulSoup

from app.config import settings
from app.logging_setup import log
from app.models import PropertyType, RawListing
from app.sources.base import SourceAdapter


class ImmoScout24RSSSource(SourceAdapter):
    """ImmoScout24 via saved-search RSS feed — no Playwright, no captcha.

    Set IMMOSCOUT24_SAVE_SEARCH_ID in .env to the numeric ID from your IS24
    saved search URL (the saveSearchId= parameter).
    """

    name = "immoscout24"
    base_url = "https://www.immobilienscout24.de"

    async def fetch(self) -> AsyncIterator[RawListing]:
        save_id = settings.immoscout24_save_search_id
        if not save_id:
            log.warning("immoscout24_rss.skip_no_id")
            return

        rss_url = f"https://www.immobilienscout24.de/rss/suche.rss?saveSearchId={save_id}"
        assert self.client is not None

        try:
            r = await self.client.get(
                rss_url,
                headers={"Accept": "application/rss+xml, application/xml, text/xml, */*"},
            )
            r.raise_for_status()
        except Exception as e:
            log.warning("immoscout24_rss.fetch_failed", error=str(e), url=rss_url)
            return

        feed = feedparser.parse(r.text)
        if not feed.entries:
            log.warning("immoscout24_rss.no_entries", url=rss_url, status=r.status_code, body_len=len(r.text))
            return

        log.info("immoscout24_rss.fetched", entries=len(feed.entries))

        for entry in feed.entries:
            link = entry.get("link", "")
            m = re.search(r"/expose/(\d+)", link)
            if not m:
                continue
            source_id = m.group(1)

            title = entry.get("title", "Inserat")
            desc_html = entry.get("summary", "") or entry.get("description", "")
            desc_text = BeautifulSoup(desc_html, "lxml").get_text(" ", strip=True) if desc_html else ""
            full_text = f"{title} {desc_text}"

            yield RawListing(
                source=self.name,
                source_id=source_id,
                url=link,
                title=title,
                description=desc_text[:2000],
                price_eur=self._parse_price(full_text),
                qm=self._parse_qm(full_text),
                rooms=self._parse_rooms(full_text),
                address=self._parse_address(desc_text),
                property_type=self._guess_type(title),
                fetched_at=datetime.utcnow(),
            )

    @staticmethod
    def _parse_price(text: str) -> int | None:
        m = re.search(r"([\d\.]{4,})\s*(?:€|EUR)", text)
        if not m:
            return None
        try:
            return int(m.group(1).replace(".", ""))
        except ValueError:
            return None

    @staticmethod
    def _parse_qm(text: str) -> float | None:
        m = re.search(r"([\d,]+)\s*m²", text)
        if not m:
            return None
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            return None

    @staticmethod
    def _parse_rooms(text: str) -> float | None:
        m = re.search(r"([\d,]+)\s*(?:Zi(?:mmer)?\.?)", text)
        if not m:
            return None
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            return None

    @staticmethod
    def _parse_address(text: str) -> str | None:
        m = re.search(r"(\d{5}\s+[A-ZÄÖÜ][a-zA-ZäöüÄÖÜß\-\s]{2,30})", text)
        return m.group(1).strip() if m else None

    @staticmethod
    def _guess_type(title: str) -> PropertyType:
        t = title.lower()
        if "doppelhaush" in t:
            return PropertyType.DOPPELHAUSHAELFTE
        if "reihenhaus" in t:
            return PropertyType.REIHENHAUS
        if "haus" in t or "villa" in t or "bungalow" in t:
            return PropertyType.HAUS
        if "wohnung" in t or "appartement" in t or "etage" in t:
            return PropertyType.WOHNUNG
        if "grundst" in t:
            return PropertyType.GRUNDSTUECK
        return PropertyType.UNKNOWN
