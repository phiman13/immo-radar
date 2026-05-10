from __future__ import annotations

from typing import Any

import app.db as db_module
from app.config import settings as env_settings

# Mapping: setting key → (attr on env_settings, type)
_DEFAULTS: dict[str, tuple[str, type]] = {
    "poll_interval_minutes": ("poll_interval_minutes", int),
    "detail_fetch_interval_minutes": ("detail_fetch_interval_minutes", int),
    "search_radius_km": ("search_radius_km", float),
    "price_min": ("price_min", int),
    "price_max": ("price_max", int),
    "qm_min": ("qm_min", int),
    "qm_max": ("qm_max", int),
    "rooms_min": ("rooms_min", float),
    "year_built_min": ("year_built_min", int),
    "property_types": ("property_types", str),
    "score_threshold": ("score_threshold", float),
}


def get_setting(key: str) -> Any:
    """Return setting value from DB, falling back to env/default."""
    with db_module.SessionLocal() as session:
        row = session.get(db_module.AppSetting, key)
        if row is not None:
            _, cast = _DEFAULTS.get(key, (None, str))
            return cast(row.value)
    # Fall back to env
    attr, cast = _DEFAULTS.get(key, (key, str))
    val = getattr(env_settings, attr, None)
    return val


def set_setting(key: str, value: Any) -> None:
    """Persist a setting to DB."""
    with db_module.SessionLocal() as session:
        row = session.get(db_module.AppSetting, key)
        if row is None:
            row = db_module.AppSetting(key=key, value=str(value))
            session.add(row)
        else:
            row.value = str(value)
        session.commit()


def get_all_settings() -> dict[str, Any]:
    """Return all known settings with their current values."""
    return {key: get_setting(key) for key in _DEFAULTS}
