"""Tests für AgentSiteSource — generischer, DB-getriebener Adapter für die
agents-Tabelle. Additiv zur REGISTRY (Vollabdeckung-Spec §5.3)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db as db_module
from app.db import Agent, Base
from app.models import PropertyType, RawListing
from app.sources.agents_adapter import EXTRACTION_METHODS, AgentSiteSource


@pytest.fixture()
def session(monkeypatch, tmp_path):
    test_engine = create_engine(f"sqlite:///{tmp_path}/test.db", echo=False, future=True)
    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)
    return TestSession


@pytest.fixture(autouse=True)
def clean_extraction_methods():
    EXTRACTION_METHODS.clear()
    yield
    EXTRACTION_METHODS.clear()


def _make_agent(session, **overrides) -> int:
    defaults = dict(
        name="Test Makler",
        coverage_status="auto-harvested",
        listing_url="https://example.de/angebote/",
        extraction={"method": "fake"},
    )
    defaults.update(overrides)
    with session() as s:
        agent = Agent(**defaults)
        s.add(agent)
        s.commit()
        return agent.id


@pytest.mark.asyncio
async def test_fetch_yields_from_registered_method(session, monkeypatch):
    agent_id = _make_agent(session)

    async def fake_method(agent, client) -> AsyncIterator[RawListing]:
        yield RawListing(
            source="agents",
            source_id=f"agent-{agent.id}-1",
            url="https://example.de/angebote/1",
            title="Testobjekt",
            property_type=PropertyType.HAUS,
        )

    EXTRACTION_METHODS["fake"] = fake_method
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=True))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert len(results) == 1
    assert results[0].source_id == f"agent-{agent_id}-1"


@pytest.mark.asyncio
async def test_fetch_skips_agents_not_auto_harvested(session, monkeypatch):
    """Strukturelle Garantie der Transparenz-Anforderung: nur
    coverage_status == 'auto-harvested' wird überhaupt angefasst — 'unknown'
    zählt nie als abgedeckt."""
    _make_agent(session, coverage_status="unknown")

    async def fake_method(agent, client) -> AsyncIterator[RawListing]:
        yield RawListing(source="agents", source_id="x", url="https://x", title="x")

    EXTRACTION_METHODS["fake"] = fake_method
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=True))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert results == []


@pytest.mark.asyncio
async def test_fetch_skips_agent_without_method(session, monkeypatch):
    _make_agent(session, extraction={})
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=True))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert results == []


@pytest.mark.asyncio
async def test_fetch_skips_unregistered_method(session, monkeypatch):
    _make_agent(session, extraction={"method": "does-not-exist"})
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=True))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert results == []


@pytest.mark.asyncio
async def test_fetch_marks_robots_disallowed_and_persists_reason(session, monkeypatch):
    agent_id = _make_agent(session)

    async def fake_method(agent, client) -> AsyncIterator[RawListing]:
        yield RawListing(source="agents", source_id="x", url="https://x", title="x")

    EXTRACTION_METHODS["fake"] = fake_method
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=False))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert results == []
    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.coverage_status == "robots-disallowed"
        assert agent.coverage_reason is not None
        assert agent.last_checked is not None


@pytest.mark.asyncio
async def test_fetch_isolates_a_failing_agent_from_the_rest(session, monkeypatch):
    """Spec §7: 'Ein fehlschlagender Makler bricht nie den Gesamtlauf ab.'"""
    _make_agent(session, name="Broken Makler")
    ok_id = _make_agent(session, name="OK Makler", listing_url="https://ok.example.de/angebote/")

    call_count = {"n": 0}

    async def flaky_method(agent, client) -> AsyncIterator[RawListing]:
        call_count["n"] += 1
        if agent.name == "Broken Makler":
            raise RuntimeError("boom")
        yield RawListing(source="agents", source_id=f"agent-{agent.id}", url=agent.listing_url, title="OK")

    EXTRACTION_METHODS["fake"] = flaky_method
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=True))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert call_count["n"] == 2
    assert len(results) == 1
    assert results[0].source_id == f"agent-{ok_id}"


@pytest.mark.asyncio
async def test_fetch_isolates_an_is_allowed_exception_from_the_rest(session, monkeypatch):
    """Die robots-Prüfung selbst ist Teil der Pro-Agent-Isolation (Spec §7):
    ein RobotFileParser-Fehler o.ä. für einen Makler darf den Gesamtlauf
    nicht abbrechen — der review-round-1-Fix für agents_adapter.py."""
    broken_id = _make_agent(session, name="Broken Makler", listing_url="https://broken.example.de/angebote/")
    ok_id = _make_agent(session, name="OK Makler", listing_url="https://ok.example.de/angebote/")

    async def fake_method(agent, client) -> AsyncIterator[RawListing]:
        yield RawListing(source="agents", source_id=f"agent-{agent.id}", url=agent.listing_url, title="OK")

    async def flaky_is_allowed(client, url):
        if url == "https://broken.example.de/angebote/":
            raise ValueError("malformed robots.txt")
        return True

    EXTRACTION_METHODS["fake"] = fake_method
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", flaky_is_allowed)

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert len(results) == 1
    assert results[0].source_id == f"agent-{ok_id}"
    with session() as s:
        broken_agent = s.get(Agent, broken_id)
        # Kein DB-Write erwartet — die Exception fliegt vor dem Commit; nur
        # die Isolation (kein Abbruch des Gesamtlaufs) ist hier relevant.
        assert broken_agent.coverage_status == "auto-harvested"


def test_registry_includes_agents_source_additively():
    from app.sources import REGISTRY, get_all_adapters
    from app.sources.agents_adapter import AgentSiteSource
    from app.sources.kleinanzeigen import KleinanzeigenSource

    assert REGISTRY["agents"] is AgentSiteSource
    assert REGISTRY["kleinanzeigen"] is KleinanzeigenSource  # unverändert

    adapters = get_all_adapters()
    assert any(isinstance(a, AgentSiteSource) for a in adapters)
    assert len(adapters) == len(REGISTRY)
