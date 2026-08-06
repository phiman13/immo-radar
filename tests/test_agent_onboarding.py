"""Tests für app.agent_onboarding — bildet die klassifizierte Kaskadenstufe
auf das extraction-Schema ab und schreibt sie auf die Agent-Zeile."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db as db_module
from app.agent_onboarding import onboard_agent
from app.db import Agent, Base


@pytest.fixture()
def session(monkeypatch, tmp_path):
    test_engine = create_engine(f"sqlite:///{tmp_path}/test.db", echo=False, future=True)
    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)
    return TestSession


def _make_agent(session, **overrides) -> int:
    defaults = dict(name="Test Makler", verified_domain="x.de")
    defaults.update(overrides)
    with session() as s:
        agent = Agent(**defaults)
        s.add(agent)
        s.commit()
        return agent.id


@pytest.mark.asyncio
async def test_onboard_agent_sets_auto_harvested_for_vendor_stage(session, monkeypatch):
    agent_id = _make_agent(session)
    fake_row = {
        "reachable": True,
        "robots_allows_root": True,
        "vendors": ["onoffice"],
        "listing_url": "https://x.de/immobilien/",
        "structured": {"jsonld_types": []},
        "sitemap_object_urls": 0,
        "detail_links": 0,
        "signals": {"prices": 0},
    }
    monkeypatch.setattr("app.agent_onboarding.probe_agent", AsyncMock(return_value=fake_row))

    client = AsyncMock()
    with session() as s:
        await onboard_agent(agent_id, client, session=s)
        s.commit()

    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.coverage_status == "auto-harvested"
        assert agent.extraction == {"method": "vendor:onoffice", "vendor": "onoffice"}
        assert agent.listing_url == "https://x.de/immobilien/"
        assert agent.last_checked is not None


@pytest.mark.asyncio
async def test_onboard_agent_sets_needs_manual_watch_for_js_shell(session, monkeypatch):
    agent_id = _make_agent(session)
    fake_row = {
        "reachable": True,
        "robots_allows_root": True,
        "vendors": [],
        "structured": {"jsonld_types": []},
        "sitemap_object_urls": 0,
        "detail_links": 0,
        "signals": {"prices": 0},
    }
    monkeypatch.setattr("app.agent_onboarding.probe_agent", AsyncMock(return_value=fake_row))

    client = AsyncMock()
    with session() as s:
        await onboard_agent(agent_id, client, session=s)
        s.commit()

    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.coverage_status == "needs-manual-watch"
        assert "JS-Shell" in agent.coverage_reason


@pytest.mark.asyncio
async def test_onboard_agent_sets_robots_disallowed(session, monkeypatch):
    agent_id = _make_agent(session)
    fake_row = {"reachable": True, "robots_allows_root": False}
    monkeypatch.setattr("app.agent_onboarding.probe_agent", AsyncMock(return_value=fake_row))

    client = AsyncMock()
    with session() as s:
        await onboard_agent(agent_id, client, session=s)
        s.commit()

    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.coverage_status == "robots-disallowed"
        assert agent.robots_status == "disallowed"


@pytest.mark.asyncio
async def test_onboard_agent_sets_bot_blocked_with_needs_browser_hint(session, monkeypatch):
    agent_id = _make_agent(session)
    fake_row = {"reachable": False, "blocked": True}
    monkeypatch.setattr("app.agent_onboarding.probe_agent", AsyncMock(return_value=fake_row))

    client = AsyncMock()
    with session() as s:
        await onboard_agent(agent_id, client, session=s)
        s.commit()

    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.coverage_status == "bot-blocked"
        assert agent.extraction == {"needs_browser": True}


@pytest.mark.asyncio
async def test_onboard_agent_raises_for_missing_verified_domain(session):
    agent_id = _make_agent(session, verified_domain=None)
    client = AsyncMock()

    with pytest.raises(ValueError, match="verified_domain"):
        with session() as s:
            await onboard_agent(agent_id, client, session=s)


@pytest.mark.asyncio
async def test_onboard_agent_without_explicit_session_commits_itself(session, monkeypatch):
    agent_id = _make_agent(session)
    fake_row = {
        "reachable": True,
        "robots_allows_root": True,
        "vendors": ["onoffice"],
        "listing_url": "https://x.de/immobilien/",
        "structured": {"jsonld_types": []},
        "sitemap_object_urls": 0,
        "detail_links": 0,
        "signals": {"prices": 0},
    }
    monkeypatch.setattr("app.agent_onboarding.probe_agent", AsyncMock(return_value=fake_row))

    client = AsyncMock()
    await onboard_agent(agent_id, client)  # keine Session übergeben

    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.coverage_status == "auto-harvested"
