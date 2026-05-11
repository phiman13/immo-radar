from __future__ import annotations

import json as _json
from typing import Any

import app.db as db_module
from app.config import settings as env_settings

# Mapping: setting key → (attr on env_settings, type)
_DEFAULTS: dict[str, tuple[str, type]] = {
    "poll_interval_minutes": ("poll_interval_minutes", int),
    "detail_fetch_interval_minutes": ("detail_fetch_interval_minutes", int),
    "poll_enabled": ("poll_enabled", bool),
    "enrich_enabled": ("enrich_enabled", bool),
    "search_center_lat": ("search_center_lat", float),
    "search_center_lon": ("search_center_lon", float),
    "search_radius_km": ("search_radius_km", float),
    "price_min": ("price_min", int),
    "price_max": ("price_max", int),
    "qm_min": ("qm_min", int),
    "qm_max": ("qm_max", int),
    "rooms_min": ("rooms_min", float),
    "year_built_min": ("year_built_min", int),
    "property_types": ("property_types", str),
    "score_threshold": ("score_threshold", float),
    "search_locations": ("search_locations", str),  # stored as JSON
    "preferences": ("preferences", str),  # stored as JSON list of strings
}

_JSON_KEYS = {"search_locations", "preferences"}
_BOOL_KEYS = {"poll_enabled", "enrich_enabled"}


def get_setting(key: str) -> Any:
    """Return setting value from DB, falling back to env/default."""
    with db_module.SessionLocal() as session:
        row = session.get(db_module.AppSetting, key)
        if row is not None:
            if key in _JSON_KEYS:
                return _json.loads(row.value)
            if key in _BOOL_KEYS:
                return row.value.lower() in ("1", "true")
            _, cast = _DEFAULTS.get(key, (None, str))
            return cast(row.value)
    # Fallback for preferences: empty list
    if key == "preferences":
        return []
    # Fallback for search_locations: derive from individual lat/lon/radius settings
    if key == "search_locations":
        return [
            {
                "lat": get_setting("search_center_lat"),
                "lon": get_setting("search_center_lon"),
                "radius_km": get_setting("search_radius_km"),
                "label": "Hauptstandort",
            }
        ]
    # Boolean keys default to True if not in DB yet
    if key in _BOOL_KEYS:
        return True
    # Fall back to env
    attr, cast = _DEFAULTS.get(key, (key, str))
    val = getattr(env_settings, attr, None)
    return val


def set_setting(key: str, value: Any) -> None:
    """Persist a setting to DB."""
    if key in _JSON_KEYS:
        str_value = _json.dumps(value, ensure_ascii=False)
    elif key in _BOOL_KEYS:
        str_value = "true" if value else "false"
    else:
        str_value = str(value)
    with db_module.SessionLocal() as session:
        row = session.get(db_module.AppSetting, key)
        if row is None:
            row = db_module.AppSetting(key=key, value=str_value)
            session.add(row)
        else:
            row.value = str_value
        session.commit()


def get_all_settings() -> dict[str, Any]:
    """Return all known settings with their current values."""
    return {key: get_setting(key) for key in _DEFAULTS}
