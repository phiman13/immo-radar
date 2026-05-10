from __future__ import annotations

import app.db as db_module
from app.db import Listing

_counter = 0


def seed_listing(session, **kwargs):
    global _counter
    _counter += 1
    source_id = kwargs.pop("ext_id", f"ext-{_counter}")
    defaults = dict(
        dedup_hash=f"hash-{source_id}-{_counter}",
        source_id=source_id,
        source=kwargs.pop("portal", "test"),
        title="Wohnung Tutzing",
        url=f"https://example.com/listing/{_counter}",
        price_eur=kwargs.pop("price", 250000),
        qm=kwargs.pop("area", 80.0),
        rooms=3.0,
        lage_score=kwargs.pop("lage_score", 70),
    )
    defaults.update(kwargs)
    listing = Listing(**defaults)
    session.add(listing)
    session.commit()
    session.refresh(listing)
    return listing


def test_get_listings_empty(client, test_db):
    resp = client.get("/api/listings/")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_listings_returns_listing(client, test_db):
    with db_module.SessionLocal() as session:
        seed_listing(session)
    resp = client.get("/api/listings/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "Wohnung Tutzing"
    assert data[0]["price_per_sqm"] == 3125.0


def test_get_listing_404(client, test_db):
    resp = client.get("/api/listings/9999")
    assert resp.status_code == 404


def test_patch_listing_status(client, test_db):
    with db_module.SessionLocal() as session:
        listing = seed_listing(session)
        lid = listing.id
    resp = client.patch(f"/api/listings/{lid}", json={"status": "favorit"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "favorit"


def test_get_listings_filter_by_score(client, test_db):
    with db_module.SessionLocal() as session:
        seed_listing(session, lage_score=80)
        seed_listing(session, lage_score=30)
    resp = client.get("/api/listings/?min_score=50")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
