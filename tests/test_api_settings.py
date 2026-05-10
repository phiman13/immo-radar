"""Tests for /api/settings/ endpoints."""

from __future__ import annotations


def test_get_settings(client, test_db):
    """GET /api/settings/ returns all known settings."""
    resp = client.get("/api/settings/")
    assert resp.status_code == 200
    data = resp.json()
    assert "settings" in data
    assert isinstance(data["settings"], dict)
    assert "poll_interval_minutes" in data["settings"]
    assert "search_radius_km" in data["settings"]
    assert "price_min" in data["settings"]


def test_patch_settings_valid(client, test_db):
    """PATCH /api/settings/ with a valid key updates the setting."""
    resp = client.patch("/api/settings/", json={"key": "poll_interval_minutes", "value": 99})
    assert resp.status_code == 200
    data = resp.json()
    assert data["settings"]["poll_interval_minutes"] == 99

    # Verify the change persists
    resp2 = client.get("/api/settings/")
    assert resp2.json()["settings"]["poll_interval_minutes"] == 99


def test_patch_settings_float(client, test_db):
    """PATCH /api/settings/ with a float value."""
    resp = client.patch("/api/settings/", json={"key": "search_radius_km", "value": 7.5})
    assert resp.status_code == 200
    data = resp.json()
    assert data["settings"]["search_radius_km"] == 7.5


def test_patch_settings_invalid_key(client, test_db):
    """PATCH /api/settings/ with an unknown key returns 422."""
    resp = client.patch("/api/settings/", json={"key": "nonexistent_key", "value": "x"})
    assert resp.status_code == 422
    assert "Unknown setting key" in resp.json()["detail"]
