"""Tests für app.pipeline — insbesondere die Geocoding-Integration, die den
Regionsfilter repariert (Vollabdeckung-Spec §4.3)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db as db_module
from app.db import Base
from app.models import PropertyType, RawListing
from app.pipeline import _matches_profile, _upsert
from app.settings_service import set_setting

TUTZING_LOCATIONS = [{"lat": 47.9095, "lon": 11.2783, "radius_km": 5, "label": "Tutzing"}]


@pytest.fixture()
def session(monkeypatch, tmp_path):
    test_engine = create_engine(f"sqlite:///{tmp_path}/test.db", echo=False, future=True)
    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)
    return TestSession


def _raw(**overrides) -> RawListing:
    defaults = dict(
        source="test",
        source_id="1",
        url="https://example.de/1",
        title="Haus in Tutzing",
        address="Bahnhofstr. 1, 82327 Tutzing",
        price_eur=800_000,
        qm=140,
        property_type=PropertyType.HAUS,
    )
    defaults.update(overrides)
    return RawListing(**defaults)


def test_matches_profile_accepts_geocoded_object_in_area(session):
    set_setting("search_locations", TUTZING_LOCATIONS)
    raw = _raw()
    with patch("app.pipeline.geocode", return_value=(47.9095, 11.2783, 0.6)):
        assert _matches_profile(raw) is True
    assert raw.region_match_reason == "geocoded"
    assert raw.geocode_confidence == 0.6
    assert raw.lat == 47.9095


def test_matches_profile_rejects_geocoded_object_outside_area(session):
    """Regression für den historischen Bug: früher gab in_search_area() ohne
    lat/lon immer True zurück, egal wo das Objekt tatsächlich lag. Der
    Regex-Vorfilter matcht hier zwar ("Starnberg" im Titel erwähnt), die
    echten geocodierten Koordinaten (München) müssen den Regionsfilter
    trotzdem greifen lassen."""
    set_setting("search_locations", TUTZING_LOCATIONS)
    raw = _raw(
        address="Marienplatz 1, 80331 München",
        title="Wohnung München (erwähnt Starnberg im Text)",
    )
    with patch("app.pipeline.geocode", return_value=(48.1374, 11.5755, 0.7)):
        assert _matches_profile(raw) is False


def test_matches_profile_uses_source_coordinates_without_geocoding(session):
    set_setting("search_locations", TUTZING_LOCATIONS)
    raw = _raw(lat=47.91, lon=11.28)
    with patch("app.pipeline.geocode") as mock_geocode:
        assert _matches_profile(raw) is True
        mock_geocode.assert_not_called()
    assert raw.region_match_reason == "coordinates-from-source"


def test_matches_profile_falls_back_to_regex_on_geocode_failure(session):
    set_setting("search_locations", TUTZING_LOCATIONS)
    raw = _raw()
    with patch("app.pipeline.geocode", return_value=(None, None, None)):
        assert _matches_profile(raw) is True
    assert raw.region_match_reason == "geocode-failed-regex-fallback"


def test_matches_profile_rejects_without_geocoding_when_no_location_text(session):
    """Der Regex-Vorfilter spart die Geocoding-Anfrage, wenn gar kein
    Ortstext vorhanden ist — unverändertes Verhalten von _location_ok."""
    raw = _raw(address=None, city=None, plz=None, title="Haus")
    with patch("app.pipeline.geocode") as mock_geocode:
        assert _matches_profile(raw) is False
        mock_geocode.assert_not_called()


def test_upsert_persists_geocoding_metadata(session):
    raw = _raw()
    raw.lat, raw.lon = 47.9095, 11.2783
    raw.geocode_confidence = 0.6
    raw.region_match_reason = "geocoded"

    with session() as s:
        listing, is_new = _upsert(s, raw)
        s.commit()
        assert is_new is True
        assert listing.geocode_confidence == 0.6
        assert listing.region_match_reason == "geocoded"

    raw.region_match_reason = "geocode-failed-regex-fallback"
    raw.geocode_confidence = None

    with session() as s:
        listing, is_new = _upsert(s, raw)
        s.commit()
        assert is_new is False
        assert listing.region_match_reason == "geocode-failed-regex-fallback"
        assert listing.geocode_confidence is None
