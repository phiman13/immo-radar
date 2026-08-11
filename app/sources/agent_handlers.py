"""I/O-Handler der Extraktions-Kaskade (Vollabdeckung-Spec §4.1, Phase 2b) —
Gegenstück zu app.agent_cascade_detect (reine Erkennung) und
app.agent_field_extract (reine Feldextraktion): hier laufen beide zusammen,
gegen echtes Netzwerk. Jeder Handler erfüllt die ExtractionMethod-Signatur aus
app.sources.agents_adapter (Callable[[Agent, httpx.AsyncClient],
AsyncIterator[RawListing]]) und wird dort in EXTRACTION_METHODS registriert.

Crawl-Budget (Spec §8): pro Agent maximal MAX_DETAIL_PAGES_PER_AGENT
Detailseiten, mit DETAIL_FETCH_DELAY_SECONDS Pause dazwischen — bewusst
kürzer als die 1s-Probe-Pause aus app.agent_probe (dort ein Abruf pro Host je
Onboarding-Lauf, hier bis zu 40 Abrufe pro Host je Harvest-Lauf). robots.txt
wird hier NICHT pro Detailseite erneut geprüft — app.sources.agents_adapter
prüft bereits einmal pro Agent vor jedem Handler-Aufruf (identische
Vereinfachung wie app.agent_probe, das nur robots_allows_root auf
Root-Ebene prüft).

Alle Handler befüllen RawListing.plz/.city, NIE RawListing.address — siehe
app.agent_field_extract-Modul-Docstring für die Dedup-Begründung."""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator

import httpx
from bs4 import BeautifulSoup

from app.agent_cascade_detect import DETAIL_RE, SITEMAP_OBJECT_RE, find_detail_links
from app.agent_field_extract import extract_fields
from app.db import Agent
from app.logging_setup import log
from app.models import RawListing

MAX_DETAIL_PAGES_PER_AGENT = 40
DETAIL_FETCH_DELAY_SECONDS = 0.5


def _source_id(agent_id: int, url: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", url.lower()).strip("-")[-64:]
    return f"agent-{agent_id}-{slug}"


async def _fetch_detail_listing(agent: Agent, client: httpx.AsyncClient, url: str) -> RawListing | None:
    try:
        r = await client.get(url)
        r.raise_for_status()
    except Exception as e:
        log.warning("agent_handlers.detail_fetch_failed", agent_id=agent.id, url=url, error=str(e))
        return None

    text = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)
    fields = extract_fields(r.text, text)
    return RawListing(
        source="agents",
        source_id=_source_id(agent.id, url),
        url=url,
        title=fields["title"],
        description=text[:2000],
        price_eur=fields["price_eur"],
        qm=fields["qm"],
        rooms=fields["rooms"],
        plz=fields["plz"],
        city=fields["city"],
        property_type=fields["property_type"],
    )


async def crawl_and_extract(agent: Agent, client: httpx.AsyncClient) -> AsyncIterator[RawListing]:
    """Handler für alle `vendor:<x>`-Method-Keys UND `detail_links` (Scope-
    Entscheidung Phase 2b): Phase 0 lieferte nur Vendor-Fingerprints, keine
    Vendor-spezifischen Selektoren — `vendor:<x>` bleibt deshalb nur ein
    Herkunfts-Tag im extraction-Dict, kein eigener Code-Pfad. Findet
    Objekt-URLs strukturell (find_detail_links) auf agent.listing_url, holt
    jede Detailseite, extrahiert Felder generisch."""
    if not agent.listing_url:
        log.warning("agent_handlers.crawl_no_listing_url", agent_id=agent.id)
        return

    try:
        r = await client.get(agent.listing_url)
        r.raise_for_status()
    except Exception as e:
        log.warning("agent_handlers.listing_fetch_failed", agent_id=agent.id, error=str(e))
        return

    _, urls = find_detail_links(r.text, agent.listing_url, limit=None)
    urls = urls[:MAX_DETAIL_PAGES_PER_AGENT]

    for url in urls:
        listing = await _fetch_detail_listing(agent, client, url)
        if listing is not None:
            yield listing
        await asyncio.sleep(DETAIL_FETCH_DELAY_SECONDS)


async def _discover_sitemap_object_urls(client: httpx.AsyncClient, sitemap_url: str) -> list[str]:
    try:
        r = await client.get(sitemap_url)
        r.raise_for_status()
    except Exception as e:
        log.warning("agent_handlers.sitemap_fetch_failed", url=sitemap_url, error=str(e))
        return []

    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", r.text)
    subs = [u for u in locs if u.endswith(".xml") and SITEMAP_OBJECT_RE.search(u)]
    obj_urls: set[str] = {u for u in locs if DETAIL_RE.search(u)}
    for sub in subs[:3]:
        try:
            sr = await client.get(sub)
            sr.raise_for_status()
        except Exception as e:
            log.warning("agent_handlers.sub_sitemap_fetch_failed", url=sub, error=str(e))
            continue
        obj_urls.update(u for u in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sr.text) if DETAIL_RE.search(u))
    return sorted(obj_urls)


async def sitemap_objekte_handler(agent: Agent, client: httpx.AsyncClient) -> AsyncIterator[RawListing]:
    """Handler für `sitemap_objekte`: die in extraction['sitemap_url']
    festgehaltene Sitemap wird erneut abgerufen (der Onboarding-Probe hat sie
    nur klassifiziert, nicht für den Harvest behalten), Objekt-URLs per
    DETAIL_RE/SITEMAP_OBJECT_RE identifiziert (identisch zur Probe-Logik in
    app.agent_probe.probe_agent), dann wie crawl_and_extract je Detailseite
    extrahiert."""
    sitemap_url = (agent.extraction or {}).get("sitemap_url")
    if not sitemap_url:
        log.warning("agent_handlers.sitemap_no_url", agent_id=agent.id)
        return

    urls = (await _discover_sitemap_object_urls(client, sitemap_url))[:MAX_DETAIL_PAGES_PER_AGENT]
    for url in urls:
        listing = await _fetch_detail_listing(agent, client, url)
        if listing is not None:
            yield listing
        await asyncio.sleep(DETAIL_FETCH_DELAY_SECONDS)
