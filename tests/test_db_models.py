"""Tests for AppSetting and Source models."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db as db_module
from app.db import AppSetting, Base, Source


@pytest.fixture()
def session(monkeypatch, tmp_path):
    """Isolated in-memory DB per test."""
    test_engine = create_engine(f"sqlite:///{tmp_path}/test.db", echo=False, future=True)
    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)
    return TestSession


def test_app_setting_crud(session):
    with session() as s:
        setting = AppSetting(key="test_key", value="test_value")
        s.add(setting)
        s.commit()
        fetched = s.get(AppSetting, "test_key")
        assert fetched.value == "test_value"
        s.delete(fetched)
        s.commit()


def test_source_crud(session):
    with session() as s:
        source = Source(name="test_portal", display_name="Test Portal")
        s.add(source)
        s.commit()
        fetched = s.query(Source).filter_by(name="test_portal").first()
        assert fetched is not None
        assert fetched.enabled is True
        s.delete(fetched)
        s.commit()
