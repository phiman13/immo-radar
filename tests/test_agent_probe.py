"""Tests für app.agent_probe — Ein-Domain-Netzwerk-Orchestrierung der
Extraktions-Kaskade. httpx wird über AsyncMock mit URL-Routing gemockt
(Projekt-Konvention, siehe tests/test_robots.py) — kein respx."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent_probe import classify_stage, probe_agent, validate_domain


def _resp(status_code=200, text="", url=None):
    r = MagicMock()
    r.status_code = status_code
    r.text = text
    r.url = url or "https://x.de/"
    r.headers = {}
    return r


def _routed_client(routes: dict[str, MagicMock], default=None):
    """routes: URL (exakt) -> Response-Mock. Alles andere -> default (404)."""
    client = AsyncMock()

    async def _get(url, *a, **kw):
        if url in routes:
            return routes[url]
        return default or _resp(status_code=404)

    client.get = AsyncMock(side_effect=_get)
    return client


@pytest.mark.asyncio
async def test_probe_agent_unreachable_domain_short_circuits():
    client = AsyncMock()
    client.get = AsyncMock(side_effect=Exception("connection refused"))

    row = await probe_agent("tot.example.de", client)

    assert row["reachable"] is False
    assert row["error"] == "unreachable"


@pytest.mark.asyncio
async def test_probe_agent_403_marks_blocked():
    client = _routed_client({"https://blocked.example.de/": _resp(status_code=403)})

    row = await probe_agent("blocked.example.de", client)

    assert row["reachable"] is False
    assert row["blocked"] is True


@pytest.mark.asyncio
async def test_probe_agent_stops_after_robots_disallow():
    """Spec §8: Disallow -> kein weiterer Abruf. Der Sitemap-Pfad darf nie
    angefragt werden, wenn robots.txt die Startseite verbietet."""
    routes = {
        "https://x.de/": _resp(text="<html></html>"),
        "https://x.de/robots.txt": _resp(text="User-agent: *\nDisallow: /"),
    }
    client = _routed_client(routes)

    row = await probe_agent("x.de", client)

    assert row["robots_allows_root"] is False
    assert "sitemap" not in row
    called_urls = {c.args[0] for c in client.get.await_args_list}
    assert "https://x.de/sitemap.xml" not in called_urls


@pytest.mark.asyncio
async def test_probe_agent_detects_vendor_and_detail_links():
    home_html = """
    <html><body>
      <script src="/wp-content/plugins/onoffice-for-wp-websites/app.js"></script>
      <a href="/immobilien/">Immobilien</a>
    </body></html>
    """
    listing_html = """
    <html><body>
      <a href="/immobilien/villa-am-see-tutzing">A</a>
      <a href="/immobilien/wohnung-starnberg-zentral">B</a>
      <a href="/immobilien/haus-poecking-mit-garten">C</a>
    </body></html>
    """
    routes = {
        "https://x.de/": _resp(text=home_html),
        "https://x.de/robots.txt": _resp(status_code=404),
        "https://x.de/sitemap.xml": _resp(status_code=404),
        "https://x.de/wp-sitemap.xml": _resp(status_code=404),
        "https://x.de/immobilien/": _resp(text=listing_html, url="https://x.de/immobilien/"),
    }
    client = _routed_client(routes)

    row = await probe_agent("x.de", client)

    assert row["reachable"] is True
    assert "onoffice" in row["vendors"]
    assert row["detail_links"] == 3
    assert classify_stage(row) == "2-vendor"


@pytest.mark.asyncio
async def test_probe_agent_captures_sitemap_url_for_sitemap_objekte_stage():
    """Fix 1 (Final-Review): der Sitemap-URL selbst (zum späteren Re-Fetch in
    Phase 2b) muss im Ergebnis landen -- getrennt von sitemap_object_sample,
    das lediglich ein paar Beispiel-Objekt-URLs für Diagnosezwecke trägt."""
    sitemap_xml = """<?xml version="1.0"?>
    <urlset>
      <url><loc>https://x.de/immobilien/villa-am-see-tutzing</loc></url>
      <url><loc>https://x.de/immobilien/wohnung-starnberg-zentral</loc></url>
      <url><loc>https://x.de/immobilien/haus-poecking-mit-garten</loc></url>
    </urlset>"""
    routes = {
        "https://x.de/": _resp(text="<html></html>"),
        "https://x.de/robots.txt": _resp(status_code=404),
        "https://x.de/sitemap.xml": _resp(text=sitemap_xml),
    }
    client = _routed_client(routes)

    row = await probe_agent("x.de", client)

    assert row["sitemap"] is True
    assert row["sitemap_url"] == "https://x.de/sitemap.xml"
    assert row["sitemap_object_urls"] == 3
    assert classify_stage(row) == "4-sitemap-objekte"


def test_classify_stage_unreachable():
    assert classify_stage({"reachable": False}) == "unreachable"


def test_classify_stage_blocked():
    assert classify_stage({"reachable": False, "blocked": True}) == "blocked (braucht Browser)"


def test_classify_stage_robots_disallowed_before_any_cascade_check():
    row = {"reachable": True, "robots_allows_root": False, "vendors": ["onoffice"]}
    assert classify_stage(row) == "robots-disallowed"


def test_classify_stage_prefers_vendor_over_detail_links():
    row = {
        "reachable": True,
        "robots_allows_root": True,
        "vendors": ["onoffice"],
        "detail_links": 10,
    }
    assert classify_stage(row) == "2-vendor"


def test_classify_stage_falls_back_to_js_shell():
    row = {
        "reachable": True,
        "robots_allows_root": True,
        "vendors": [],
        "structured": {"jsonld_types": []},
        "sitemap_object_urls": 0,
        "detail_links": 0,
        "signals": {"prices": 0},
    }
    assert classify_stage(row) == "7-js-shell/unklar"


# --- HER-725: SSRF-Guard auf verified_domain -------------------------------
#
# Aktuell wird Agent.verified_domain nur manuell gesetzt (vertrauenswürdig),
# aber Phase 3 (Discovery) wird dieses Feld künftig aus Websuche-Ergebnissen
# befüllen -- ab dann ist der Wert nicht mehr vertrauenswürdig. probe_agent()
# baut daraus direkt eine Netzwerk-Ziel-URL (f"https://{domain}/"); ohne
# Guard könnte ein Wert wie "169.254.169.254" (Cloud-Metadata) oder
# "localhost:8001" (das eigene Dashboard) den Worker-Container gegen sich
# selbst oder das VPS-interne Netz probieren lassen.


@pytest.mark.parametrize(
    "domain",
    [
        "loeger-immobilien.de",
        "www.ubi-immobilien.de",
        "immobilien.vr-starnberg-zugspitze.de",
        "sub.domain.example.co.uk",
    ],
)
def test_validate_domain_accepts_real_looking_hostnames(domain):
    validate_domain(domain)  # darf nicht raisen


@pytest.mark.parametrize(
    "domain",
    [
        "127.0.0.1",
        "169.254.169.254",  # Cloud-Metadata-Endpoint
        "10.0.0.5",
        "192.168.1.1",
        "::1",
        "localhost",
        "foo.localhost",
        "bar.internal",
        "baz.local",
        "app.test",
        "example.example",
        "site.onion",
        "localhost:8001",
        "a.de@internal",
        "http://a.de",
        "a..de",
        "-a.de",
        "a.de-",
        "",
        "   ",
    ],
)
def test_validate_domain_rejects_ssrf_adjacent_and_malformed_values(domain):
    with pytest.raises(ValueError):
        validate_domain(domain)


@pytest.mark.asyncio
async def test_probe_agent_raises_instead_of_probing_an_ip_literal():
    client = AsyncMock()
    client.get = AsyncMock(side_effect=AssertionError("darf nie aufgerufen werden"))

    with pytest.raises(ValueError):
        await probe_agent("169.254.169.254", client)

    client.get.assert_not_called()
