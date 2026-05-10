"""Tests for GET /api/sources/ and PATCH /api/sources/{id}."""

from __future__ import annotations


def test_get_sources_seeds_defaults(client, test_db):
    """First call should seed default sources."""
    resp = client.get("/api/sources/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 3  # at least immoscout24, immowelt, kleinanzeigen
    names = [s["name"] for s in data]
    assert "immoscout24" in names


def test_get_sources_idempotent(client, test_db):
    """Second call should not duplicate sources."""
    client.get("/api/sources/")
    resp = client.get("/api/sources/")
    data = resp.json()
    names = [s["name"] for s in data]
    assert names.count("immoscout24") == 1


def test_patch_source_toggle(client, test_db):
    """Should be able to disable a source."""
    sources = client.get("/api/sources/").json()
    source_id = sources[0]["id"]

    resp = client.patch(f"/api/sources/{source_id}", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


def test_patch_source_404(client, test_db):
    resp = client.patch("/api/sources/9999", json={"enabled": True})
    assert resp.status_code == 404
