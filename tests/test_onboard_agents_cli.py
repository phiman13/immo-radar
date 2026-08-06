"""Test für scripts.onboard_agents — Agent-Auswahl für den CLI-Trigger."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db as db_module
from app.db import Agent, Base
from scripts.onboard_agents import _agent_ids_to_onboard, main


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


@pytest.mark.asyncio
async def test_main_isolates_exceptions_per_agent(session, monkeypatch, capsys):
    """Verify that if one agent raises an exception, the next one still gets
    onboarded (failure isolation per Spec §7)."""
    # Setup two agents
    with session() as s:
        a1 = Agent(name="A1", verified_domain="a1.de", coverage_status="unknown")
        a2 = Agent(name="A2", verified_domain="a2.de", coverage_status="unknown")
        s.add_all([a1, a2])
        s.commit()
        a1_id = a1.id
        a2_id = a2.id

    # Mock onboard_agent: first call raises, second succeeds
    fake_agent = Agent(
        id=a2_id,
        name="A2",
        verified_domain="a2.de",
        coverage_status="auto-harvested",
        extraction={"method": "test"},
    )

    call_count = 0

    async def mock_onboard(agent_id, client, session=None):
        nonlocal call_count
        call_count += 1
        if agent_id == a1_id:
            raise ValueError(f"agent {a1_id} has no verified_domain")
        return fake_agent

    monkeypatch.setattr("scripts.onboard_agents.onboard_agent", mock_onboard)

    # Run main() with both agents
    await main(None)
    captured = capsys.readouterr()

    # Verify both agents were processed (attempted)
    assert call_count == 2, f"Expected 2 calls, got {call_count}"
    # First agent should show error line
    assert "ERROR" in captured.out
    assert f"[{a1_id:>4}]" in captured.out
    # Second agent should show success line with auto-harvested status
    assert f"[{a2_id:>4}]" in captured.out
    assert "auto-harvested" in captured.out
