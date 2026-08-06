"""Tests für app.agent_probe — Ein-Domain-Netzwerk-Orchestrierung der
Extraktions-Kaskade. httpx wird über AsyncMock mit URL-Routing gemockt
(Projekt-Konvention, siehe tests/test_robots.py) — kein respx."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent_probe import classify_stage, probe_agent


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
