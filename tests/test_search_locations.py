import os

os.environ.setdefault("DB_PATH", "/tmp/immo_test_loc.db")

import pytest


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db)
    import importlib

    import app.config
    import app.db
    import app.settings_service

    importlib.reload(app.config)
    importlib.reload(app.db)
    importlib.reload(app.settings_service)
    from app.db import init_db

    init_db()
    yield


def test_search_locations_fallback():
    """When not set in DB, should return list from single-location settings."""
    from app.settings_service import get_setting

    locs = get_setting("search_locations")
    assert isinstance(locs, list)
    assert len(locs) >= 1
    first = locs[0]
    assert "lat" in first and "lon" in first and "radius_km" in first


def test_search_locations_roundtrip():
    """set_setting stores as JSON, get_setting returns parsed list."""
    from app.settings_service import get_setting, set_setting

    locs = [
        {"lat": 47.9095, "lon": 11.2783, "radius_km": 5, "label": "Tutzing"},
        {"lat": 47.8651, "lon": 11.3415, "radius_km": 3, "label": "Starnberg"},
    ]
    set_setting("search_locations", locs)
    result = get_setting("search_locations")
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[1]["label"] == "Starnberg"


def test_in_search_area_multi():
    """in_search_area with locations list: True if within ANY circle."""
    from app.scoring.lage import in_search_area

    locations = [
        {"lat": 47.9095, "lon": 11.2783, "radius_km": 5},
        {"lat": 48.1351, "lon": 11.5820, "radius_km": 3},  # München
    ]
    # Tutzing center — in first circle
    assert in_search_area(47.9095, 11.2783, locations) is True
    # Munich center — in second circle
    assert in_search_area(48.1351, 11.5820, locations) is True
    # Hamburg — in neither
    assert in_search_area(53.55, 10.00, locations) is False
    # None coords — always True (don't filter unknown)
    assert in_search_area(None, None, locations) is True
