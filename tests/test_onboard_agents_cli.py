"""Test für scripts.onboard_agents — Agent-Auswahl für den CLI-Trigger."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db as db_module
from app.db import Agent, Base
from scripts.onboard_agents import _agent_ids_to_onboard


@pytest.fixture()
def session(monkeypatch, tmp_path):
    test_engine = create_engine(f"sqlite:///{tmp_path}/test.db", echo=False, future=True)
    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)
    return TestSession


@pytest.mark.asyncio
async def test_agent_ids_to_onboard_selects_unknown_with_verified_domain(session):
    with session() as s:
        a = Agent(name="A", verified_domain="a.de", coverage_status="unknown")
        b = Agent(name="B", verified_domain=None, coverage_status="unknown")
        c = Agent(name="C", verified_domain="c.de", coverage_status="auto-harvested")
        s.add_all([a, b, c])
        s.commit()
        a_id = a.id

    ids = await _agent_ids_to_onboard(None)

    assert ids == [a_id]


@pytest.mark.asyncio
async def test_agent_ids_to_onboard_with_explicit_id_ignores_status(session):
    with session() as s:
        c = Agent(name="C", verified_domain="c.de", coverage_status="auto-harvested")
        s.add(c)
        s.commit()
        c_id = c.id

    ids = await _agent_ids_to_onboard(c_id)

    assert ids == [c_id]
