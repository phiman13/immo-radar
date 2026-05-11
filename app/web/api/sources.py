from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import app.db as db_module

router = APIRouter()

DEFAULT_SOURCES = [
    {"name": "immoscout24", "display_name": "ImmoScout24"},
    {"name": "immowelt", "display_name": "Immowelt"},
    {"name": "kleinanzeigen", "display_name": "Kleinanzeigen"},
    {"name": "makler_bsimmo", "display_name": "BS Immo"},
    {"name": "makler_riedel", "display_name": "Riedel Immobilien"},
    {"name": "makler_starnberg_immo", "display_name": "Starnberg Immo"},
    {"name": "sparkasse_immo", "display_name": "Sparkasse Immobilien"},
    {"name": "tutzing24", "display_name": "Tutzing24"},
]


def _seed_sources(session) -> None:
    """Seed default sources if table is empty."""
    count = session.query(db_module.Source).count()
    if count == 0:
        for src in DEFAULT_SOURCES:
            session.add(db_module.Source(**src))
        session.commit()


class SourceOut(BaseModel):
    id: int
    name: str
    display_name: str
    enabled: bool
    last_run: datetime | None
    listing_count: int
    url: str | None
    source_type: str = "builtin"

    model_config = {"from_attributes": True}


class SourcePatch(BaseModel):
    enabled: bool | None = None
    display_name: str | None = None


@router.get("/", response_model=list[SourceOut])
def get_sources():
    with db_module.SessionLocal() as session:
        _seed_sources(session)
        sources = session.query(db_module.Source).order_by(db_module.Source.name).all()
        return [SourceOut.model_validate(s) for s in sources]


@router.patch("/{source_id}", response_model=SourceOut)
def patch_source(source_id: int, body: SourcePatch):
    with db_module.SessionLocal() as session:
        source = session.get(db_module.Source, source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")
        if body.enabled is not None:
            source.enabled = body.enabled
        if body.display_name is not None:
            source.display_name = body.display_name
        session.commit()
        session.refresh(source)
        return SourceOut.model_validate(source)
