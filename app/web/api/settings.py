from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import app.settings_service as svc_module

router = APIRouter()


class SettingsOut(BaseModel):
    settings: dict[str, Any]


class SettingsPatch(BaseModel):
    key: str
    value: Any


@router.get("/", response_model=SettingsOut)
def get_settings():
    """Return all known settings with their current values."""
    return SettingsOut(settings=svc_module.get_all_settings())


@router.patch("/", response_model=SettingsOut)
def patch_settings(body: SettingsPatch):
    """Update a single setting by key.

    Raises HTTPException 422 if the key is not a known setting.
    """
    valid_keys = set(svc_module._DEFAULTS.keys())
    if body.key not in valid_keys:
        raise HTTPException(status_code=422, detail=f"Unknown setting key: {body.key}")
    svc_module.set_setting(body.key, body.value)
    return SettingsOut(settings=svc_module.get_all_settings())
