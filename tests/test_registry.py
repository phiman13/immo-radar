"""Tests für app.sources.registry.get_all_adapters().

Regression HER-805: der "Aktiv"-Schalter im Dashboard schrieb `Source.enabled`
in die DB, aber get_all_adapters() instanziierte bedingungslos alle REGISTRY-
Adapter — eine deaktivierte Quelle wurde trotzdem bei jedem Poll gecrawlt."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db as db_module
from app.db import Base, Source
from app.sources.registry import REGISTRY, get_all_adapters


@pytest.fixture()
def session(monkeypatch, tmp_path):
    test_engine = create_engine(f"sqlite:///{tmp_path}/test.db", echo=False, future=True)
    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)
    return TestSession


def test_get_all_adapters_returns_everything_when_no_source_rows_exist(session):
    adapters = get_all_adapters()
    assert len(adapters) == len(REGISTRY)


def test_get_all_adapters_skips_a_disabled_source(session):
    with session() as s:
        s.add(Source(name="kleinanzeigen", display_name="Kleinanzeigen", enabled=False))
        s.commit()

    adapters = get_all_adapters()

    assert len(adapters) == len(REGISTRY) - 1
    assert not any(a.name == "kleinanzeigen" for a in adapters)


def test_get_all_adapters_keeps_enabled_sources(session):
    with session() as s:
        s.add(Source(name="kleinanzeigen", display_name="Kleinanzeigen", enabled=True))
        s.add(Source(name="riedel", display_name="Riedel", enabled=False))
        s.commit()

    adapters = get_all_adapters()

    names = {a.name for a in adapters}
    assert "kleinanzeigen" in names
    assert "riedel" not in names
    assert len(adapters) == len(REGISTRY) - 1


def test_get_all_adapters_treats_agents_as_enabled_without_a_source_row(session):
    """`agents` hat nie eine `sources`-Zeile (eigene Coverage-Tabelle) — darf
    dadurch nicht fälschlich als deaktiviert gelten."""
    adapters = get_all_adapters()
    assert any(a.name == "agents" for a in adapters)
