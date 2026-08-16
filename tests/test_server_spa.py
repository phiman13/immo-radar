"""Tests für die SPA-index.html-Auslieferung in app.web.server.

Regression HER-820: index.html referenziert bei jedem Frontend-Build neu
gehashte /assets/*-Dateien. Ohne explizites Cache-Control kann ein Browser
(heuristisches Caching via Last-Modified/ETag) nach einem Deploy ein altes
index.html weiterverwenden, das auf inzwischen gelöschte Asset-Hashes zeigt
(404) -- real während der HER-809-Verifikation beobachtet."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.web.server as server_module


@pytest.fixture()
def spa_client(test_db, monkeypatch, tmp_path):
    """Zeigt BASE_DIR auf ein Temp-Verzeichnis mit einer minimalen
    index.html -- unabhängig davon, ob im aktuellen Checkout gerade ein
    echter Frontend-Build existiert."""
    fake_dist = tmp_path / "static" / "dist"
    fake_dist.mkdir(parents=True)
    (fake_dist / "index.html").write_text("<html><body>SPA</body></html>")
    monkeypatch.setattr(server_module, "BASE_DIR", tmp_path)

    with TestClient(server_module.app, raise_server_exceptions=True) as c:
        yield c
    server_module.app.dependency_overrides.clear()


def test_index_route_sets_no_cache_on_spa_index(spa_client):
    resp = spa_client.get("/")
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-cache"


def test_spa_fallback_route_sets_no_cache_on_spa_index(spa_client):
    resp = spa_client.get("/some/client-side/route")
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-cache"
