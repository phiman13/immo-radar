"""Tests für die neuen Modelle Agent und GeocodeCache (Phase 1: Fundament)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db as db_module
from app.db import COVERAGE_STATUSES, Agent, Base, GeocodeCache, Listing


@pytest.fixture()
def session(monkeypatch, tmp_path):
    """Isolierte In-Memory-DB pro Test — Referenzmuster: tests/test_db_models.py."""
    test_engine = create_engine(f"sqlite:///{tmp_path}/test.db", echo=False, future=True)
    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)
    return TestSession


def test_coverage_statuses_constant():
    assert COVERAGE_STATUSES == (
        "unknown",
        "auto-harvested",
        "needs-manual-watch",
        "unreachable",
        "bot-blocked",
        "login-required",
        "robots-disallowed",
    )


def test_agent_defaults_to_unknown_coverage(session):
    """Kernanforderung aus dem Spec: `unknown` ist Default und zählt nie als
    abgedeckt, ohne dass eine Zeile das explizit setzen muss."""
    with session() as s:
        agent = Agent(name="Testmakler Tutzing")
        s.add(agent)
        s.commit()

        fetched = s.query(Agent).filter_by(name="Testmakler Tutzing").first()
        assert fetched is not None
        assert fetched.coverage_status == "unknown"
        assert fetched.discovery_sources == []
        assert fetched.domain_candidates == []
        assert fetched.extraction == {}
        assert fetched.imprint_match is False
        assert fetched.last_listing_count == 0
        assert fetched.verified_domain is None
        assert fetched.last_checked is None


def test_agent_full_roundtrip(session):
    with session() as s:
        agent = Agent(
            name="Beispiel Immobilien",
            city="Starnberg",
            discovery_sources=["makler-empfehlung.de", "websuche"],
            verified_domain="beispiel-immobilien.de",
            domain_candidates=["beispiel-immobilien.de", "beispiel-immo.de"],
            imprint_match=True,
            listing_url="https://beispiel-immobilien.de/angebote/",
            extraction={"method": "vendor:onoffice", "vendor": "onoffice"},
            coverage_status="auto-harvested",
            coverage_reason=None,
            robots_status="allowed",
            last_listing_count=12,
        )
        s.add(agent)
        s.commit()
        agent_id = agent.id

    with session() as s:
        fetched = s.get(Agent, agent_id)
        assert fetched.city == "Starnberg"
        assert fetched.discovery_sources == ["makler-empfehlung.de", "websuche"]
        assert fetched.extraction["vendor"] == "onoffice"
        assert fetched.coverage_status == "auto-harvested"
        assert fetched.last_listing_count == 12
        s.delete(fetched)
        s.commit()


def test_geocode_cache_crud(session):
    with session() as s:
        row = GeocodeCache(
            address_hash="abc123",
            address="Bahnhofstr. 1, 82327 Tutzing",
            lat=47.9095,
            lon=11.2783,
            importance=0.55,
        )
        s.add(row)
        s.commit()

        fetched = s.get(GeocodeCache, "abc123")
        assert fetched.lat == 47.9095
        assert fetched.address == "Bahnhofstr. 1, 82327 Tutzing"
        s.delete(fetched)
        s.commit()


def test_listing_geocoding_columns_default_none(session):
    with session() as s:
        listing = Listing(
            dedup_hash="x" * 16,
            source="test",
            source_id="1",
            url="https://example.de/1",
            title="Testobjekt",
        )
        s.add(listing)
        s.commit()

        fetched = s.query(Listing).filter_by(dedup_hash="x" * 16).first()
        assert fetched.geocode_confidence is None
        assert fetched.region_match_reason is None
        s.delete(fetched)
        s.commit()
