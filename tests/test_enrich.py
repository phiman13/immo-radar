"""Tests for enrich_pending() skip logic."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db as db_module
import app.enrich as enrich_module
from app.db import Base, Listing


@pytest.fixture()
def in_memory_session(monkeypatch, tmp_path):
    """Patch db_module engine + SessionLocal to use an isolated in-memory DB."""
    test_engine = create_engine(f"sqlite:///{tmp_path}/test.db", echo=False, future=True)
    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)

    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)
    monkeypatch.setattr(enrich_module, "SessionLocal", TestSession)

    return TestSession


def _make_listing(session_factory, *, enrich_attempts: int = 0, ai_score=None) -> int:
    with session_factory() as s:
        listing = Listing(
            dedup_hash=f"hash-{enrich_attempts}-{ai_score}-{id(session_factory)}",
            source="test",
            source_id=f"src-{enrich_attempts}-{ai_score}",
            url="http://example.com",
            title="Testinserat",
            property_type="wohnung",
            enrich_attempts=enrich_attempts,
            ai_score=ai_score,
        )
        s.add(listing)
        s.commit()
        s.refresh(listing)
        return listing.id


def test_enrich_pending_skips_exhausted(in_memory_session, monkeypatch):
    """Listings with enrich_attempts >= 3 must NOT be passed to enrich_listing."""
    called_ids: list[int] = []

    async def fake_enrich(listing_id: int) -> None:
        called_ids.append(listing_id)

    monkeypatch.setattr(enrich_module, "enrich_listing", fake_enrich)

    exhausted_id = _make_listing(in_memory_session, enrich_attempts=3)
    fresh_id = _make_listing(in_memory_session, enrich_attempts=0)

    asyncio.run(enrich_module.enrich_pending())

    assert exhausted_id not in called_ids, "exhausted listing must be skipped"
    assert fresh_id in called_ids, "fresh listing must be processed"


def test_enrich_pending_also_skips_at_two_plus_one(in_memory_session, monkeypatch):
    """Boundary: attempts == 3 is the cutoff, attempts == 2 is still eligible."""
    called_ids: list[int] = []

    async def fake_enrich(listing_id: int) -> None:
        called_ids.append(listing_id)

    monkeypatch.setattr(enrich_module, "enrich_listing", fake_enrich)

    at_two_id = _make_listing(in_memory_session, enrich_attempts=2)
    at_three_id = _make_listing(in_memory_session, enrich_attempts=3)

    asyncio.run(enrich_module.enrich_pending())

    assert at_two_id in called_ids, "attempts=2 must still be processed"
    assert at_three_id not in called_ids, "attempts=3 must be skipped"


def test_enrich_pending_skips_already_scored(in_memory_session, monkeypatch):
    """Listings with ai_score already set are not re-enriched (existing behaviour)."""
    called_ids: list[int] = []

    async def fake_enrich(listing_id: int) -> None:
        called_ids.append(listing_id)

    monkeypatch.setattr(enrich_module, "enrich_listing", fake_enrich)

    scored_id = _make_listing(in_memory_session, ai_score=75)
    pending_id = _make_listing(in_memory_session, ai_score=None)

    asyncio.run(enrich_module.enrich_pending())

    assert scored_id not in called_ids
    assert pending_id in called_ids
