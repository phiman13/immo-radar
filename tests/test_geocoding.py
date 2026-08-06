"""Tests für app.geocoding — Nominatim mit persistentem Adress-Cache."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from geopy.exc import GeocoderServiceError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db as db_module
from app.db import Base, GeocodeCache
from app.geocoding import geocode


@pytest.fixture()
def session(monkeypatch, tmp_path):
    test_engine = create_engine(f"sqlite:///{tmp_path}/test.db", echo=False, future=True)
    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)
    return TestSession


def test_geocode_empty_address_skips_nominatim(session, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.geocoding._rate_limited_geocode",
        lambda *a, **kw: calls.append(1),
    )
    assert geocode("") == (None, None, None)
    assert geocode("   ") == (None, None, None)
    assert calls == []


def test_geocode_cache_miss_then_hit(session, monkeypatch):
    calls = []

    def fake_geocode(address, **kwargs):
        calls.append(address)
        return SimpleNamespace(latitude=47.91, longitude=11.28, raw={"importance": 0.55})

    monkeypatch.setattr("app.geocoding._rate_limited_geocode", fake_geocode)

    result1 = geocode("Bahnhofstr. 1, 82327 Tutzing")
    assert result1 == (47.91, 11.28, 0.55)
    assert len(calls) == 1

    result2 = geocode("Bahnhofstr. 1, 82327 Tutzing")
    assert result2 == (47.91, 11.28, 0.55)
    assert len(calls) == 1  # Cache-Treffer — kein zweiter Nominatim-Call

    with session() as s:
        row = s.query(GeocodeCache).first()
        assert row is not None
        assert row.address == "Bahnhofstr. 1, 82327 Tutzing"
        assert row.lat == 47.91


def test_geocode_normalizes_whitespace_for_cache_key(session, monkeypatch):
    """'Bahnhofstr.  1,   82327  Tutzing' und 'bahnhofstr. 1, 82327 tutzing'
    müssen denselben Cache-Eintrag treffen."""
    calls = []

    def fake_geocode(address, **kwargs):
        calls.append(address)
        return SimpleNamespace(latitude=47.91, longitude=11.28, raw={})

    monkeypatch.setattr("app.geocoding._rate_limited_geocode", fake_geocode)

    geocode("Bahnhofstr.  1,   82327  Tutzing")
    geocode("bahnhofstr. 1, 82327 tutzing")
    assert len(calls) == 1


def test_geocode_no_result_is_cached_as_permanent_miss(session, monkeypatch):
    calls = []

    def fake_geocode(address, **kwargs):
        calls.append(address)
        return None

    monkeypatch.setattr("app.geocoding._rate_limited_geocode", fake_geocode)

    assert geocode("Nirgendwostr. 999, 00000 Nirgendwo") == (None, None, None)
    assert geocode("Nirgendwostr. 999, 00000 Nirgendwo") == (None, None, None)
    assert len(calls) == 1  # zweiter Aufruf trifft den (negativen) Cache


def test_geocode_transient_error_is_not_cached(session, monkeypatch):
    calls = []

    def failing_geocode(address, **kwargs):
        calls.append(address)
        raise GeocoderServiceError("timeout")

    monkeypatch.setattr("app.geocoding._rate_limited_geocode", failing_geocode)

    assert geocode("Teststr. 1, 82327 Tutzing") == (None, None, None)
    assert geocode("Teststr. 1, 82327 Tutzing") == (None, None, None)
    assert len(calls) == 2  # kein Cache-Eintrag bei transientem Fehler → jeder Aufruf versucht erneut
