"""Tests für app.sources.agent_handlers — I/O-Handler der Extraktions-Kaskade
(Phase 2b). httpx wird über AsyncMock mit URL-Routing gemockt (Projekt-
Konvention, siehe tests/test_agent_probe.py) — kein respx."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db import Agent
from app.sources.agent_handlers import crawl_and_extract


def _resp(status_code=200, text=""):
    r = MagicMock()
    r.status_code = status_code
    r.text = text
    r.raise_for_status = MagicMock()
    if status_code >= 400:
        r.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return r


def _routed_client(routes: dict[str, MagicMock], default=None):
    client = AsyncMock()

    async def _get(url, *a, **kw):
        if url in routes:
            return routes[url]
        return default or _resp(status_code=404)

    client.get = AsyncMock(side_effect=_get)
    return client


def _agent(**overrides) -> Agent:
    defaults = dict(id=1, name="Test Makler", listing_url=None, extraction={})
    defaults.update(overrides)
    return Agent(**defaults)


@pytest.mark.asyncio
async def test_crawl_and_extract_finds_and_extracts_detail_pages():
    listing_html = """
    <html><body>
      <a href="/immobilien/villa-am-see-tutzing">A</a>
      <a href="/immobilien/wohnung-starnberg-zentral">B</a>
      <a href="/immobilien/haus-poecking-mit-garten">C</a>
    </body></html>
    """
    detail_html = (
        "<html><body><h1>Villa am See</h1>"
        "<p>Kaufpreis: 450.000 € 180 m² 6 Zimmer 82327 Tutzing</p></body></html>"
    )
    routes = {
        "https://x.de/immobilien/": _resp(text=listing_html),
        "https://x.de/immobilien/villa-am-see-tutzing": _resp(text=detail_html),
        "https://x.de/immobilien/wohnung-starnberg-zentral": _resp(text=detail_html),
        "https://x.de/immobilien/haus-poecking-mit-garten": _resp(text=detail_html),
    }
    client = _routed_client(routes)
    agent = _agent(listing_url="https://x.de/immobilien/")

    results = [r async for r in crawl_and_extract(agent, client)]

    assert len(results) == 3
    assert results[0].price_eur == 450000
    assert results[0].qm == 180.0
    assert results[0].plz == "82327"
    assert results[0].city == "Tutzing"
    assert results[0].address is None
    assert results[0].source == "agents"
    assert results[0].source_id.startswith("agent-1-")


@pytest.mark.asyncio
async def test_crawl_and_extract_returns_nothing_without_listing_url():
    client = _routed_client({})
    agent = _agent(listing_url=None)

    results = [r async for r in crawl_and_extract(agent, client)]

    assert results == []


@pytest.mark.asyncio
async def test_crawl_and_extract_skips_a_single_failing_detail_page():
    listing_html = """
    <html><body>
      <a href="/immobilien/villa-am-see-tutzing">A</a>
      <a href="/immobilien/wohnung-starnberg-zentral">B</a>
      <a href="/immobilien/haus-poecking-mit-garten">C</a>
    </body></html>
    """
    detail_html = "<html><body><h1>Villa am See</h1><p>450.000 € 180 m² 82327 Tutzing</p></body></html>"
    routes = {
        "https://x.de/immobilien/": _resp(text=listing_html),
        "https://x.de/immobilien/villa-am-see-tutzing": _resp(status_code=500),
        "https://x.de/immobilien/wohnung-starnberg-zentral": _resp(text=detail_html),
        "https://x.de/immobilien/haus-poecking-mit-garten": _resp(text=detail_html),
    }
    client = _routed_client(routes)
    agent = _agent(listing_url="https://x.de/immobilien/")

    results = [r async for r in crawl_and_extract(agent, client)]

    assert len(results) == 2


@pytest.mark.asyncio
async def test_crawl_and_extract_keeps_objects_distinct_despite_shared_footer_address():
    """Regression für den Dedup-Kollaps (Advisor-Fund): teilen sich alle
    Detailseiten dieselbe Impressum-Adresse im Footer und haben KEINE
    Preis-/Flächenangabe (z.B. "Preis auf Anfrage"), darf RawListing.address
    NICHT davon befüllt werden — sonst kollabieren alle Objekte auf denselben
    dedup_hash() (app/models.py: leere address -> Fallback source_id, gesetzte
    address -> address+qm+price als Hash-Basis, und qm/price sind hier auch
    beide None -> ohne den Fix wäre der Hash für alle drei identisch).

    Slugs bewusst lang/mehrgliedrig ("objekt-ohne-sachdaten-eins" statt
    "objekt-a") — find_detail_links() (Task 1) verlangt für
    is_object_like() ein letztes Pfadsegment mit >=12 Zeichen ODER >=2
    Bindestrichen, sonst wird die Detailseiten-Gruppe gar nicht erst
    erkannt (kein Regressionstest-Verhalten, sondern ein Detektions-Gate
    aus app.agent_cascade_detect, das hier nicht verändert wird)."""
    listing_html = """
    <html><body>
      <a href="/immobilien/objekt-ohne-sachdaten-eins">A</a>
      <a href="/immobilien/objekt-ohne-sachdaten-zwei">B</a>
      <a href="/immobilien/objekt-ohne-sachdaten-drei">C</a>
    </body></html>
    """
    detail_html = (
        "<html><body><h1>Objekt ohne Sachdaten</h1><footer>82327 Tutzing, Impressum</footer></body></html>"
    )
    routes = {
        "https://x.de/immobilien/": _resp(text=listing_html),
        "https://x.de/immobilien/objekt-ohne-sachdaten-eins": _resp(text=detail_html),
        "https://x.de/immobilien/objekt-ohne-sachdaten-zwei": _resp(text=detail_html),
        "https://x.de/immobilien/objekt-ohne-sachdaten-drei": _resp(text=detail_html),
    }
    client = _routed_client(routes)
    agent = _agent(listing_url="https://x.de/immobilien/")

    results = [r async for r in crawl_and_extract(agent, client)]

    assert len(results) == 3
    assert all(r.address is None for r in results)
    # Precondition für die Hash-Demonstration unten: der Kollaps entsteht nur,
    # wenn address UND qm UND price_eur alle leer/None sind (app/models.py
    # dedup_hash()) — ohne diese Pin-Assertion könnte ein künftiger
    # Fixture-Edit die Regression stillschweigend aushöhlen.
    assert all(r.price_eur is None and r.qm is None for r in results)
    hashes = {r.dedup_hash() for r in results}
    assert len(hashes) == 3
