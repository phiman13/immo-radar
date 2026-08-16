"""Tests für app.sources.agent_handlers — I/O-Handler der Extraktions-Kaskade
(Phase 2b). httpx wird über AsyncMock mit URL-Routing gemockt (Projekt-
Konvention, siehe tests/test_agent_probe.py) — kein respx."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db import Agent
from app.sources.agent_handlers import (
    REFRESH_WINDOW,
    _source_id,
    _strip_contact_blocks,
    _urls_to_fetch,
    crawl_and_extract,
    feed_adapter_handler,
    sitemap_objekte_handler,
    structured_data_handler,
)


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


def test_source_id_does_not_collide_on_shared_long_url_tail():
    """Finding 6: die alte Implementierung slugifizierte die ganze URL und
    nahm die letzten 64 Zeichen — zwei URLs mit langem gemeinsamem Suffix
    (aber unterschiedlichem Präfix) konnten denselben 64-Zeichen-Slug-Tail
    ergeben. Da RawListing.address für Agent-Listings immer None ist, ist
    source_id die GESAMTE Dedup-Identität (siehe Modul-Docstring) — eine
    Kollision hier kollabiert zwei echte Objekte auf einen Hash.

    Präzedenzbedingung explizit gepinnt (Stil wie
    test_crawl_and_extract_keeps_objects_distinct_despite_shared_footer_address):
    die alten 64-Zeichen-Slug-Tails sind für dieses Paar tatsächlich
    identisch — sonst würde ein künftiger Fixture-Edit die Regression
    stillschweigend aushöhlen."""
    a = "https://x.de/immobilien/kaufen/exklusive-seevilla-mit-privatem-seezugang-und-bootshaus-in-tutzing-am-starnberger-see"
    b = "https://x.de/immobilien/verkauft/exklusive-seevilla-mit-privatem-seezugang-und-bootshaus-in-tutzing-am-starnberger-see"

    def _old_64_char_slug_tail(url: str) -> str:
        import re as _re

        return _re.sub(r"[^a-z0-9]+", "-", url.lower()).strip("-")[-64:]

    assert _old_64_char_slug_tail(a) == _old_64_char_slug_tail(b)

    assert _source_id(1, a) != _source_id(1, b)


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


@pytest.mark.asyncio
async def test_sitemap_objekte_handler_follows_sub_sitemap_to_object_urls():
    index_xml = """
    <urlset>
      <url><loc>https://x.de/immobilie-sitemap.xml</loc></url>
    </urlset>
    """
    sub_xml = """
    <urlset>
      <url><loc>https://x.de/immobilien/villa-am-see-tutzing</loc></url>
      <url><loc>https://x.de/immobilien/wohnung-starnberg</loc></url>
    </urlset>
    """
    detail_html = "<html><body><h1>Villa</h1><p>600.000 € 200 m² 82327 Tutzing</p></body></html>"
    routes = {
        "https://x.de/sitemap.xml": _resp(text=index_xml),
        "https://x.de/immobilie-sitemap.xml": _resp(text=sub_xml),
        "https://x.de/immobilien/villa-am-see-tutzing": _resp(text=detail_html),
        "https://x.de/immobilien/wohnung-starnberg": _resp(text=detail_html),
    }
    client = _routed_client(routes)
    agent = _agent(extraction={"method": "sitemap_objekte", "sitemap_url": "https://x.de/sitemap.xml"})

    results = [r async for r in sitemap_objekte_handler(agent, client)]

    assert len(results) == 2
    assert all(r.price_eur == 600000 for r in results)
    assert results[0].address is None


@pytest.mark.asyncio
async def test_sitemap_objekte_handler_returns_nothing_without_sitemap_url():
    client = _routed_client({})
    agent = _agent(extraction={})

    results = [r async for r in sitemap_objekte_handler(agent, client)]

    assert results == []


@pytest.mark.asyncio
async def test_sitemap_objekte_handler_resolves_relative_loc_entries():
    """Ergänzung zu Finding 3/Konvention 2: ein relativer <loc>-Eintrag
    (manche Sitemap-Generatoren emittieren pfadrelative statt absolute URLs)
    darf nicht als "off-host" verworfen werden (urlparse("").netloc == "" !=
    host) — er muss zuerst gegen die abrufende Sitemap-URL aufgelöst werden,
    wie bei Finding 1 für Feed-Links."""
    index_xml = """
    <urlset>
      <url><loc>/immobilien/villa-am-see-tutzing</loc></url>
    </urlset>
    """
    detail_html = "<html><body><h1>Villa</h1><p>600.000 € 200 m² 82327 Tutzing</p></body></html>"
    routes = {
        "https://x.de/sitemap.xml": _resp(text=index_xml),
        "https://x.de/immobilien/villa-am-see-tutzing": _resp(text=detail_html),
    }
    client = _routed_client(routes)
    agent = _agent(extraction={"method": "sitemap_objekte", "sitemap_url": "https://x.de/sitemap.xml"})

    results = [r async for r in sitemap_objekte_handler(agent, client)]

    assert len(results) == 1
    assert results[0].url == "https://x.de/immobilien/villa-am-see-tutzing"


@pytest.mark.asyncio
async def test_sitemap_objekte_handler_excludes_off_host_loc_entries():
    """Finding 3: robots.txt wird pro Agent nur einmal für seinen eigenen
    Host geprüft (agents_adapter.py, vor dem Handler-Dispatch) — ein
    <loc>-Eintrag, der auf einen fremden Host zeigt, würde sonst Content
    abrufen, dessen robots.txt nie konsultiert wurde."""
    index_xml = """
    <urlset>
      <url><loc>https://x.de/immobilien/villa-am-see-tutzing</loc></url>
      <url><loc>https://evil-other-host.de/immobilien/hijacked-objekt-hier</loc></url>
    </urlset>
    """
    detail_html = "<html><body><h1>Villa</h1><p>600.000 € 200 m² 82327 Tutzing</p></body></html>"
    routes = {
        "https://x.de/sitemap.xml": _resp(text=index_xml),
        "https://x.de/immobilien/villa-am-see-tutzing": _resp(text=detail_html),
        "https://evil-other-host.de/immobilien/hijacked-objekt-hier": _resp(text=detail_html),
    }
    client = _routed_client(routes)
    agent = _agent(extraction={"method": "sitemap_objekte", "sitemap_url": "https://x.de/sitemap.xml"})

    results = [r async for r in sitemap_objekte_handler(agent, client)]

    assert len(results) == 1
    assert results[0].url == "https://x.de/immobilien/villa-am-see-tutzing"


@pytest.mark.asyncio
async def test_structured_data_handler_reads_jsonld_and_fills_gaps_from_detail_page():
    listing_html = """
    <script type="application/ld+json">
    {"@type": "RealEstateListing", "name": "Villa am See",
     "url": "https://x.de/objekte/villa-am-see", "offers": {"price": 1200000}}
    </script>
    """
    detail_html = "<html><body><p>180 m² 6 Zimmer 82327 Tutzing</p></body></html>"
    routes = {
        "https://x.de/immobilien/": _resp(text=listing_html),
        "https://x.de/objekte/villa-am-see": _resp(text=detail_html),
    }
    client = _routed_client(routes)
    agent = _agent(listing_url="https://x.de/immobilien/")

    results = [r async for r in structured_data_handler(agent, client)]

    assert len(results) == 1
    assert results[0].title == "Villa am See"
    assert results[0].price_eur == 1200000
    assert results[0].qm == 180.0
    assert results[0].rooms == 6.0
    assert results[0].address is None


@pytest.mark.asyncio
async def test_structured_data_handler_skips_node_without_url():
    listing_html = """
    <script type="application/ld+json">
    {"@type": "Apartment", "name": "ETW ohne URL"}
    </script>
    """
    client = _routed_client({"https://x.de/immobilien/": _resp(text=listing_html)})
    agent = _agent(listing_url="https://x.de/immobilien/")

    results = [r async for r in structured_data_handler(agent, client)]

    assert results == []


@pytest.mark.asyncio
async def test_structured_data_handler_resolves_relative_jsonld_url_against_listing_page():
    listing_html = """
    <script type="application/ld+json">
    {"@type": "RealEstateListing", "name": "Villa am See",
     "url": "/objekte/villa-am-see", "offers": {"price": 1200000}}
    </script>
    """
    detail_html = "<html><body><p>180 m² 6 Zimmer 82327 Tutzing</p></body></html>"
    routes = {
        "https://x.de/immobilien/": _resp(text=listing_html),
        "https://x.de/objekte/villa-am-see": _resp(text=detail_html),
    }
    client = _routed_client(routes)
    agent = _agent(listing_url="https://x.de/immobilien/")

    results = [r async for r in structured_data_handler(agent, client)]

    assert len(results) == 1
    assert results[0].url == "https://x.de/objekte/villa-am-see"
    assert results[0].price_eur == 1200000
    assert results[0].qm == 180.0
    assert results[0].rooms == 6.0


@pytest.mark.asyncio
async def test_structured_data_handler_excludes_off_host_jsonld_url():
    """Finding 3: eine absolute JSON-LD-"url", die auf einen anderen Host
    zeigt, ist ein no-op für urljoin() (bleibt unverändert) und würde sonst
    Content von einem Host abrufen, dessen robots.txt nie geprüft wurde
    (agents_adapter.py prüft robots.txt nur einmal für agent.listing_url)."""
    listing_html = """
    <script type="application/ld+json">
    {"@type": "RealEstateListing", "name": "Villa am See",
     "url": "https://x.de/objekte/villa-am-see", "offers": {"price": 1200000}}
    </script>
    <script type="application/ld+json">
    {"@type": "RealEstateListing", "name": "Fremdobjekt",
     "url": "https://evil-other-host.de/objekte/hijacked", "offers": {"price": 999000}}
    </script>
    """
    detail_html = "<html><body><p>180 m² 6 Zimmer 82327 Tutzing</p></body></html>"
    routes = {
        "https://x.de/immobilien/": _resp(text=listing_html),
        "https://x.de/objekte/villa-am-see": _resp(text=detail_html),
        "https://evil-other-host.de/objekte/hijacked": _resp(text=detail_html),
    }
    client = _routed_client(routes)
    agent = _agent(listing_url="https://x.de/immobilien/")

    results = [r async for r in structured_data_handler(agent, client)]

    assert len(results) == 1
    assert results[0].url == "https://x.de/objekte/villa-am-see"


@pytest.mark.asyncio
async def test_structured_data_handler_falls_back_to_jsonld_only_when_detail_fetch_fails():
    """Finding 11: schlägt der Detailseiten-Abruf fehl (404/5xx/Timeout),
    liefert der Handler trotzdem einen RawListing mit den JSON-LD-Feldern —
    nur die regex-abgeleiteten Felder (die es ohne Detailseite nie gab)
    bleiben None."""
    listing_html = """
    <script type="application/ld+json">
    {"@type": "RealEstateListing", "name": "Villa am See",
     "url": "https://x.de/objekte/villa-am-see", "offers": {"price": 1200000}}
    </script>
    """
    routes = {
        "https://x.de/immobilien/": _resp(text=listing_html),
        # bewusst KEINE Route für https://x.de/objekte/villa-am-see -> 404
    }
    client = _routed_client(routes)
    agent = _agent(listing_url="https://x.de/immobilien/")

    results = [r async for r in structured_data_handler(agent, client)]

    assert len(results) == 1
    assert results[0].price_eur == 1200000
    assert results[0].qm is None
    assert results[0].rooms is None


@pytest.mark.asyncio
async def test_feed_adapter_handler_extracts_from_feed_items_directly():
    feed_xml = """
    <rss><channel>
      <item>
        <title>Haus in Tutzing, 450.000 €</title>
        <link>https://x.de/objekte/haus-tutzing</link>
        <description>140 m², 5 Zimmer, 82327 Tutzing</description>
      </item>
    </channel></rss>
    """
    client = _routed_client({"https://x.de/feed/": _resp(text=feed_xml)})
    agent = _agent(extraction={"method": "feed_adapter", "feed_url": "https://x.de/feed/"})

    results = [r async for r in feed_adapter_handler(agent, client)]

    assert len(results) == 1
    assert results[0].price_eur == 450000
    assert results[0].qm == 140.0
    assert results[0].url == "https://x.de/objekte/haus-tutzing"
    assert results[0].address is None


@pytest.mark.asyncio
async def test_feed_adapter_handler_resolves_relative_feed_link_against_feed_url():
    """Finding 1: RSS/Atom <link>-Werte sind manchmal relativ (z.B.
    <link href="/objekte/x"/>) -- app.agent_probe.validate_feed's DETAIL_RE
    matcht relative Pfade genauso wie absolute, das ist also erreichbar in
    Produktion. feed_url (die tatsächlich abgerufene URL) ist die korrekte
    Basis für die Auflösung."""
    feed_xml = """
    <feed>
      <entry>
        <title>Haus in Tutzing, 450.000 €</title>
        <link href="/objekte/haus-tutzing"/>
        <summary>140 m², 5 Zimmer, 82327 Tutzing</summary>
      </entry>
    </feed>
    """
    client = _routed_client({"https://x.de/feed/atom.xml": _resp(text=feed_xml)})
    agent = _agent(extraction={"method": "feed_adapter", "feed_url": "https://x.de/feed/atom.xml"})

    results = [r async for r in feed_adapter_handler(agent, client)]

    assert len(results) == 1
    assert results[0].url == "https://x.de/objekte/haus-tutzing"


@pytest.mark.asyncio
async def test_feed_adapter_handler_excludes_off_host_resolved_link():
    """Finding 3 (Nachtrag): robots.txt wird pro Agent nur einmal für seinen
    eigenen Host geprüft (agents_adapter.py, vor dem Handler-Dispatch) — ein
    Feed-<link>, das (nach urljoin gegen feed_url) auf einen fremden Host
    zeigt, würde sonst Content abrufen, dessen robots.txt nie konsultiert
    wurde. feed_adapter_handler war die einzige der drei URL-auflösenden
    Handler ohne diesen Same-Host-Gate (sitemap_objekte_handler und
    structured_data_handler haben ihn bereits)."""
    feed_xml = """
    <rss><channel>
      <item>
        <title>Haus in Tutzing, 450.000 €</title>
        <link>https://x.de/objekte/haus-tutzing</link>
        <description>140 m², 5 Zimmer, 82327 Tutzing</description>
      </item>
      <item>
        <title>Fremdobjekt</title>
        <link>https://evil-other-host.de/objekte/hijacked</link>
        <description>200 m², 82327 Tutzing</description>
      </item>
    </channel></rss>
    """
    client = _routed_client({"https://x.de/feed/": _resp(text=feed_xml)})
    agent = _agent(extraction={"method": "feed_adapter", "feed_url": "https://x.de/feed/"})

    results = [r async for r in feed_adapter_handler(agent, client)]

    assert len(results) == 1
    assert results[0].url == "https://x.de/objekte/haus-tutzing"


@pytest.mark.asyncio
async def test_feed_adapter_handler_returns_nothing_without_feed_url():
    client = _routed_client({})
    agent = _agent(extraction={})

    results = [r async for r in feed_adapter_handler(agent, client)]

    assert results == []


def test_strip_contact_blocks_removes_footer_address_and_kontakt_class():
    """HER-812, real beobachtet 2026-08-14 (ubi-immobilien.de): 'contact'
    kommt zweimal auf einer Detailseite vor -- beide Male als Büroadresse der
    Agentur (c-contact-person__address, c-module-contact__data), NIE als
    Objektadresse. extract_plz_city() nimmt den ERSTEN PLZ+Ort-Treffer im
    Gesamttext -- ohne Entfernung dieser Blöcke gewinnt die Büroadresse
    IMMER gegen eine später im Fließtext stehende echte Objektadresse."""
    html = """
    <html><body>
      <h1>Traumvilla am See</h1>
      <p>Das Objekt liegt in 12345 Musterstadt, gehobene Wohnlage.</p>
      <footer>Impressum: 82327 Tutzing</footer>
      <address>Maklerbüro Beispiel, 82327 Tutzing</address>
      <div class="c-contact-person__address">Hauptstraße 42, 82327 Tutzing</div>
      <div id="kontakt-widget">Rufen Sie uns an: 82327 Tutzing</div>
    </body></html>
    """
    stripped = _strip_contact_blocks(html)

    assert "12345 Musterstadt" in stripped
    assert "Traumvilla" in stripped
    assert "82327 Tutzing" not in stripped


@pytest.mark.asyncio
async def test_crawl_and_extract_prefers_object_address_over_agency_contact_address():
    """Regression HER-812: Objektadresse (12345 Musterstadt) muss gewinnen,
    obwohl die Agentur-Kontaktadresse (82327 Tutzing) zuerst im rohen HTML
    steht -- vor dem Fix hätte extract_plz_city() die Büroadresse
    gefunden."""
    # find_detail_links() erkennt eine "Gruppe" erst ab 3 gleichförmigen
    # Links (app.agent_cascade_detect) -- zwei bedeutungslose Füll-Links
    # nötig, damit der interessante Link überhaupt als Objekt-URL erkannt wird.
    listing_html = """
    <html><body>
      <a href="/immobilien/traumvilla-am-see-mit-grossem-garten">A</a>
      <a href="/immobilien/wohnung-starnberg-zentral-mit-balkon">B</a>
      <a href="/immobilien/haus-poecking-mit-grossem-grundstueck">C</a>
    </body></html>
    """
    filler_html = "<html><body><h1>Sonstiges Objekt</h1></body></html>"
    detail_html = """
    <html><body>
      <div class="c-module-contact__data">Maklerbüro Beispiel GmbH<br>Hauptstraße 42<br>82327 Tutzing</div>
      <h1>Traumvilla am See</h1>
      <p>Kaufpreis: 900.000 € · 200 m² · Lage: 12345 Musterstadt</p>
    </body></html>
    """
    routes = {
        "https://x.de/immobilien/": _resp(text=listing_html),
        "https://x.de/immobilien/traumvilla-am-see-mit-grossem-garten": _resp(text=detail_html),
        "https://x.de/immobilien/wohnung-starnberg-zentral-mit-balkon": _resp(text=filler_html),
        "https://x.de/immobilien/haus-poecking-mit-grossem-grundstueck": _resp(text=filler_html),
    }
    client = _routed_client(routes)
    agent = _agent(listing_url="https://x.de/immobilien/")

    results = [r async for r in crawl_and_extract(agent, client)]

    assert len(results) == 3
    traumvilla = next(r for r in results if r.title == "Traumvilla am See")
    assert traumvilla.plz == "12345"
    assert traumvilla.city == "Musterstadt"


def test_urls_to_fetch_includes_new_urls_not_in_known_urls():
    now = datetime(2026, 8, 16, 12, 0, 0)
    result = _urls_to_fetch(["https://x.de/a", "https://x.de/b"], {}, now)
    assert result == ["https://x.de/a", "https://x.de/b"]


def test_urls_to_fetch_canary_forces_sole_fresh_known_url():
    # Brief-Abweichung (dokumentiert in task-1-report.md): der Brief listet
    # diesen Fall unter "skips_fresh_known_urls" mit erwartetem `== []`, was
    # der eigenen Canary-Regel im selben Brief widerspricht -- bei genau
    # einer bekannten URL insgesamt greift die Canary-Regel identisch zum
    # Mehrfach-Fall (siehe test_urls_to_fetch_canary_forces_oldest_known_url_
    # when_all_fresh unten), sonst würde app.sources.agents_adapter Task 5
    # (Zwei-Läufe-Zähler) einen Single-Listing-Agent nach zwei "alles
    # frisch"-Läufen fälschlich auf needs-manual-watch zurückstufen.
    now = datetime(2026, 8, 16, 12, 0, 0)
    known = {"https://x.de/a": now - timedelta(days=1)}
    result = _urls_to_fetch(["https://x.de/a"], known, now)
    assert result == ["https://x.de/a"]


def test_urls_to_fetch_refetches_stale_known_urls():
    now = datetime(2026, 8, 16, 12, 0, 0)
    known = {"https://x.de/a": now - REFRESH_WINDOW - timedelta(hours=1)}
    result = _urls_to_fetch(["https://x.de/a"], known, now)
    assert result == ["https://x.de/a"]


def test_urls_to_fetch_mixes_new_and_stale_but_omits_fresh():
    now = datetime(2026, 8, 16, 12, 0, 0)
    known = {
        "https://x.de/fresh": now - timedelta(days=1),
        "https://x.de/stale": now - REFRESH_WINDOW - timedelta(hours=1),
    }
    result = _urls_to_fetch(["https://x.de/fresh", "https://x.de/stale", "https://x.de/new"], known, now)
    assert result == ["https://x.de/stale", "https://x.de/new"]


def test_urls_to_fetch_canary_forces_oldest_known_url_when_all_fresh():
    now = datetime(2026, 8, 16, 12, 0, 0)
    known = {
        "https://x.de/a": now - timedelta(days=1),
        "https://x.de/b": now - timedelta(hours=2),
    }
    result = _urls_to_fetch(["https://x.de/a", "https://x.de/b"], known, now)
    assert result == ["https://x.de/a"]


def test_urls_to_fetch_returns_empty_when_no_urls_discovered_at_all():
    now = datetime(2026, 8, 16, 12, 0, 0)
    assert _urls_to_fetch([], {}, now) == []


@pytest.mark.asyncio
async def test_crawl_and_extract_skips_fresh_known_url():
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
        "https://x.de/immobilien/wohnung-starnberg-zentral": _resp(text=detail_html),
        "https://x.de/immobilien/haus-poecking-mit-garten": _resp(text=detail_html),
    }
    client = _routed_client(routes)
    agent = _agent(listing_url="https://x.de/immobilien/")
    now = datetime.utcnow()
    known_urls = {"https://x.de/immobilien/villa-am-see-tutzing": now - timedelta(days=1)}

    results = [r async for r in crawl_and_extract(agent, client, known_urls)]

    urls_fetched = {r.url for r in results}
    assert "https://x.de/immobilien/villa-am-see-tutzing" not in urls_fetched
    assert urls_fetched == {
        "https://x.de/immobilien/wohnung-starnberg-zentral",
        "https://x.de/immobilien/haus-poecking-mit-garten",
    }


@pytest.mark.asyncio
async def test_crawl_and_extract_refetches_stale_known_url():
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
    now = datetime.utcnow()
    known_urls = {
        "https://x.de/immobilien/villa-am-see-tutzing": now - timedelta(days=30),
    }

    results = [r async for r in crawl_and_extract(agent, client, known_urls)]

    assert {r.url for r in results} == {
        "https://x.de/immobilien/villa-am-see-tutzing",
        "https://x.de/immobilien/wohnung-starnberg-zentral",
        "https://x.de/immobilien/haus-poecking-mit-garten",
    }


@pytest.mark.asyncio
async def test_sitemap_objekte_handler_skips_fresh_known_url():
    sitemap_xml = """<?xml version="1.0"?>
    <urlset>
      <url><loc>https://x.de/immobilien/villa-am-see-tutzing</loc></url>
      <url><loc>https://x.de/immobilien/wohnung-starnberg-zentral</loc></url>
    </urlset>"""
    detail_html = (
        "<html><body><h1>Villa am See</h1>"
        "<p>Kaufpreis: 450.000 € 180 m² 6 Zimmer 82327 Tutzing</p></body></html>"
    )
    routes = {
        "https://x.de/sitemap.xml": _resp(text=sitemap_xml),
        "https://x.de/immobilien/wohnung-starnberg-zentral": _resp(text=detail_html),
    }
    client = _routed_client(routes)
    agent = _agent(extraction={"method": "sitemap_objekte", "sitemap_url": "https://x.de/sitemap.xml"})
    now = datetime.utcnow()
    known_urls = {"https://x.de/immobilien/villa-am-see-tutzing": now - timedelta(hours=1)}

    results = [r async for r in sitemap_objekte_handler(agent, client, known_urls)]

    assert {r.url for r in results} == {"https://x.de/immobilien/wohnung-starnberg-zentral"}


@pytest.mark.asyncio
async def test_crawl_and_extract_never_requests_fresh_known_url():
    """Diskriminierender Test (Ergänzung zum Brief): anders als
    test_crawl_and_extract_skips_fresh_known_url fehlt hier NICHT die Route
    für die frische bekannte URL -- sie ist absichtlich vorhanden. Ohne
    Change-Gate würde sie also erfolgreich abgerufen UND in den Ergebnissen
    landen; der Brief-Test oben kann das nicht unterscheiden, weil dort ein
    404 (fehlende Route) das Fehlen aus den Ergebnissen bereits erklärt,
    unabhängig davon, ob das Change-Gate greift. Hier wird stattdessen
    direkt geprüft, dass client.get() NIE mit der frischen URL aufgerufen
    wird."""
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
    now = datetime.utcnow()
    known_urls = {"https://x.de/immobilien/villa-am-see-tutzing": now - timedelta(days=1)}

    [r async for r in crawl_and_extract(agent, client, known_urls)]

    requested_urls = {c.args[0] for c in client.get.call_args_list}
    assert "https://x.de/immobilien/villa-am-see-tutzing" not in requested_urls


@pytest.mark.asyncio
async def test_structured_data_handler_canary_forces_sole_fresh_known_url():
    """Angepasst nach Selbst-Review Task 3: structured_data_handler nutzt jetzt
    denselben _urls_to_fetch()-Helfer wie crawl_and_extract/
    sitemap_objekte_handler -- bei GENAU einer bekannten+frischen URL und
    keiner weiteren fälligen URL erzwingt die Canary-Regel den Abruf trotzdem
    (identisch zu test_urls_to_fetch_canary_forces_sole_fresh_known_url),
    sonst würde ein Single-Listing-Agent nach zwei "alles frisch"-Läufen
    fälschlich auf needs-manual-watch zurückgestuft (Zwei-Läufe-Zähler,
    app.sources.agents_adapter Task 5)."""
    listing_html = """
    <html><body>
    <script type="application/ld+json">
    {"@type": "Product", "name": "Altbauwohnung", "url": "https://x.de/objekt/1",
     "offers": {"price": "399000"}, "floorSize": {"value": "95"}}
    </script>
    </body></html>
    """
    detail_html = (
        "<html><body><h1>Altbauwohnung</h1>"
        "<p>Kaufpreis: 399.000 € 95 m² 3 Zimmer 82327 Tutzing</p></body></html>"
    )
    routes = {
        "https://x.de/immobilien/": _resp(text=listing_html),
        "https://x.de/objekt/1": _resp(text=detail_html),
    }
    client = _routed_client(routes)
    agent = _agent(listing_url="https://x.de/immobilien/", extraction={"method": "structured_data"})
    now = datetime.utcnow()
    known_urls = {"https://x.de/objekt/1": now - timedelta(hours=1)}

    results = [r async for r in structured_data_handler(agent, client, known_urls)]

    assert len(results) == 1
    assert results[0].url == "https://x.de/objekt/1"


@pytest.mark.asyncio
async def test_structured_data_handler_canary_forces_oldest_known_url_when_all_fresh():
    """Ergänzender Test (Concern aus dem Selbst-Review): MEHRERE bekannte+
    frische URLs, KEINE neue/überfällige -- die Canary-Regel darf hier nicht
    alle 0 unterdrücken und auch nicht alle durchlassen, sondern muss genau
    die älteste bekannte URL erzwingen (identisch zu
    test_urls_to_fetch_canary_forces_oldest_known_url_when_all_fresh)."""
    listing_html = """
    <html><body>
    <script type="application/ld+json">
    {"@type": "Product", "name": "Altbauwohnung", "url": "https://x.de/objekt/1",
     "offers": {"price": "399000"}, "floorSize": {"value": "95"}}
    </script>
    <script type="application/ld+json">
    {"@type": "Product", "name": "Neubauwohnung", "url": "https://x.de/objekt/2",
     "offers": {"price": "450000"}, "floorSize": {"value": "110"}}
    </script>
    </body></html>
    """
    detail_html_1 = (
        "<html><body><h1>Altbauwohnung</h1>"
        "<p>Kaufpreis: 399.000 € 95 m² 3 Zimmer 82327 Tutzing</p></body></html>"
    )
    routes = {
        "https://x.de/immobilien/": _resp(text=listing_html),
        "https://x.de/objekt/1": _resp(text=detail_html_1),
    }
    client = _routed_client(routes)
    agent = _agent(listing_url="https://x.de/immobilien/", extraction={"method": "structured_data"})
    now = datetime.utcnow()
    known_urls = {
        "https://x.de/objekt/1": now - timedelta(days=1),
        "https://x.de/objekt/2": now - timedelta(hours=2),
    }

    results = [r async for r in structured_data_handler(agent, client, known_urls)]

    assert len(results) == 1
    assert results[0].url == "https://x.de/objekt/1"


@pytest.mark.asyncio
async def test_feed_adapter_handler_canary_forces_sole_fresh_known_url():
    """Angepasst nach Selbst-Review Task 3: feed_adapter_handler nutzt jetzt
    denselben _urls_to_fetch()-Helfer -- bei GENAU einem bekannten+frischen
    Item und keinem weiteren fälligen Item erzwingt die Canary-Regel den
    Abruf trotzdem (siehe structured_data_handler-Pendant oben für die volle
    Begründung)."""
    feed_xml = """<?xml version="1.0"?>
    <rss><channel>
      <item>
        <title>Reihenhaus Tutzing 450.000 € 140 m²</title>
        <link>https://x.de/feed-item/1</link>
        <description>Schönes Reihenhaus</description>
      </item>
    </channel></rss>"""
    routes = {"https://x.de/feed.xml": _resp(text=feed_xml)}
    client = _routed_client(routes)
    agent = _agent(extraction={"method": "feed_adapter", "feed_url": "https://x.de/feed.xml"})
    now = datetime.utcnow()
    known_urls = {"https://x.de/feed-item/1": now - timedelta(hours=1)}

    results = [r async for r in feed_adapter_handler(agent, client, known_urls)]

    assert len(results) == 1
    assert results[0].url == "https://x.de/feed-item/1"


@pytest.mark.asyncio
async def test_feed_adapter_handler_canary_forces_oldest_known_url_when_all_fresh():
    """Ergänzender Test (Concern aus dem Selbst-Review): MEHRERE bekannte+
    frische Feed-Items, KEIN neues/überfälliges -- die Canary-Regel muss
    genau das älteste bekannte Item erzwingen, nicht 0 und nicht alle."""
    feed_xml = """<?xml version="1.0"?>
    <rss><channel>
      <item>
        <title>Reihenhaus Tutzing 450.000 € 140 m²</title>
        <link>https://x.de/feed-item/1</link>
        <description>Schönes Reihenhaus</description>
      </item>
      <item>
        <title>Neubau Starnberg 600.000 € 160 m²</title>
        <link>https://x.de/feed-item/2</link>
        <description>Neuer Neubau</description>
      </item>
    </channel></rss>"""
    routes = {"https://x.de/feed.xml": _resp(text=feed_xml)}
    client = _routed_client(routes)
    agent = _agent(extraction={"method": "feed_adapter", "feed_url": "https://x.de/feed.xml"})
    now = datetime.utcnow()
    known_urls = {
        "https://x.de/feed-item/1": now - timedelta(days=1),
        "https://x.de/feed-item/2": now - timedelta(hours=2),
    }

    results = [r async for r in feed_adapter_handler(agent, client, known_urls)]

    assert len(results) == 1
    assert results[0].url == "https://x.de/feed-item/1"


@pytest.mark.asyncio
async def test_feed_adapter_handler_still_yields_other_fresh_feed_item_when_one_is_skipped():
    """Diskriminierender Test (Ergänzung zum Brief): der Brief-Test oben hat
    nur ein einziges Feed-Item -- results == [] wäre auch dann wahr, wenn der
    Handler aus einem völlig anderen Grund (z.B. kaputtem XML-Parsing) nichts
    liefert, unabhängig vom Change-Gate. Hier gibt es zwei Items, ein
    bekanntes/frisches und ein neues -- nur das Change-Gate kann erklären,
    dass GENAU das bekannte Item fehlt, während das neue durchkommt."""
    feed_xml = """<?xml version="1.0"?>
    <rss><channel>
      <item>
        <title>Reihenhaus Tutzing 450.000 € 140 m²</title>
        <link>https://x.de/feed-item/1</link>
        <description>Schönes Reihenhaus</description>
      </item>
      <item>
        <title>Neubau Starnberg 600.000 € 160 m²</title>
        <link>https://x.de/feed-item/2</link>
        <description>Neuer Neubau</description>
      </item>
    </channel></rss>"""
    routes = {"https://x.de/feed.xml": _resp(text=feed_xml)}
    client = _routed_client(routes)
    agent = _agent(extraction={"method": "feed_adapter", "feed_url": "https://x.de/feed.xml"})
    now = datetime.utcnow()
    known_urls = {"https://x.de/feed-item/1": now - timedelta(hours=1)}

    results = [r async for r in feed_adapter_handler(agent, client, known_urls)]

    assert {r.url for r in results} == {"https://x.de/feed-item/2"}
