from __future__ import annotations

import app.db as db_module
from app.db import Listing


def seed_listing(session, **kwargs):
    """Helper to create a test listing with required fields."""
    _id = kwargs.pop("_id", 1)
    defaults = dict(
        dedup_hash=f"hash-{_id}",
        source_id=f"src-{_id}",
        source="test",
        url=f"https://example.com/listing/{_id}",
        title=f"Listing {_id}",
        price_eur=250000,
        status="new",
    )
    defaults.update(kwargs)
    listing = Listing(**defaults)
    session.add(listing)
    session.commit()
    session.refresh(listing)
    return listing


def test_system_status(client):
    """Test that /api/system/status returns valid JSON with required fields."""
    resp = client.get("/api/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "scheduler_running" in data
    assert "jobs" in data
    assert "listing_counts" in data
    assert "total" in data["listing_counts"]
    assert isinstance(data["listing_counts"]["total"], int)


def test_system_status_initial_counts(client):
    """Test that initial listing count is 0."""
    resp = client.get("/api/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["listing_counts"]["total"] == 0


def test_system_status_counts_listings(client):
    """Test that listing counts reflect actual DB state."""
    with db_module.SessionLocal() as session:
        seed_listing(session, _id=1, status="new")
        seed_listing(session, _id=2, status="viewed")

    resp = client.get("/api/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["listing_counts"]["total"] == 2
    assert data["listing_counts"]["new"] == 1
    assert data["listing_counts"]["viewed"] == 1


def test_system_status_graceful_no_scheduler(client):
    """Test that endpoint works gracefully when scheduler is not available."""
    resp = client.get("/api/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["scheduler_running"] is False
    assert data["jobs"] == []
