"""Tests for settings_service: DB persistence + env fallback."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db as db_module
from app.db import Base


@pytest.fixture()
def session(monkeypatch, tmp_path):
    """Isolated SQLite DB per test — patches db_module globals."""
    test_engine = create_engine(f"sqlite:///{tmp_path}/test.db", echo=False, future=True)
    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)
    return TestSession


def test_get_setting_fallback(session):
    """When DB is empty, should return env/default value."""
    from app.settings_service import get_setting

    val = get_setting("poll_interval_minutes")
    assert val is not None
    assert isinstance(val, int)


def test_set_and_get_setting(session):
    """Written value should be returned on next read."""
    from app.settings_service import get_setting, set_setting

    set_setting("poll_interval_minutes", 99)
    val = get_setting("poll_interval_minutes")
    assert val == 99


def test_set_overwrite_existing(session):
    """Overwriting an existing key should update the value."""
    from app.settings_service import get_setting, set_setting

    set_setting("poll_interval_minutes", 30)
    set_setting("poll_interval_minutes", 45)
    assert get_setting("poll_interval_minutes") == 45


def test_get_all_settings_returns_dict(session):
    """get_all_settings returns a dict with all known keys."""
    from app.settings_service import get_all_settings

    result = get_all_settings()
    assert isinstance(result, dict)
    assert "poll_interval_minutes" in result
    assert "search_radius_km" in result
    assert "property_types" in result


def test_get_setting_type_casting(session):
    """Values stored as strings are cast to the correct type on read."""
    from app.settings_service import get_setting, set_setting

    set_setting("search_radius_km", 7.5)
    val = get_setting("search_radius_km")
    assert isinstance(val, float)
    assert val == 7.5
