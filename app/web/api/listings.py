from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, computed_field
from sqlalchemy import asc
from sqlalchemy import desc as sqla_desc

import app.db as db_module
from app.db import Listing

router = APIRouter()


class ListingOut(BaseModel):
    id: int
    source_id: str
    source: str
    title: str
    price_eur: int | None
    qm: float | None
    rooms: float | None
    year_built: int | None
    property_type: str | None
    address: str | None
    city: str | None
    ortsteil: str | None
    plz: str | None
    lat: float | None
    lon: float | None
    hausgeld_eur: int | None
    energie_kwh: float | None
    energie_class: str | None
    images: list = []
    url: str
    lage_score: int | None
    ai_score: int | None
    ai_reasoning: str | None
    risk_flags: list = []
    status: str
    notes: str | None
    first_seen_at: datetime
    last_seen_at: datetime
    is_active: bool
    enrich_attempts: int

    @computed_field
    @property
    def price_per_sqm(self) -> float | None:
        if self.price_eur and self.qm and self.qm > 0:
            return round(self.price_eur / self.qm, 0)
        return None

    model_config = {"from_attributes": True}


class ListingPatch(BaseModel):
    status: str | None = None  # e.g. "favorit", "abgelehnt", "kontaktiert"
    notes: str | None = None


SortOption = Literal["date_desc", "price_asc", "price_desc", "score_desc", "ppm_asc", "ppm_desc"]


@router.get("/", response_model=list[ListingOut])
def get_listings(
    status: str | None = None,
    portal: str | None = None,
    min_score: float | None = None,
    price_min: int | None = None,
    price_max: int | None = None,
    qm_min: float | None = None,
    qm_max: float | None = None,
    rooms_min: float | None = None,
    sort: SortOption = "date_desc",
):
    with db_module.SessionLocal() as session:
        q = session.query(Listing)
        if status:
            q = q.filter(Listing.status == status)
        if portal:
            q = q.filter(Listing.source == portal)
        if min_score is not None:
            q = q.filter(Listing.lage_score >= min_score)
        if price_min is not None:
            q = q.filter(Listing.price_eur >= price_min)
        if price_max is not None:
            q = q.filter(Listing.price_eur <= price_max)
        if qm_min is not None:
            q = q.filter(Listing.qm >= qm_min)
        if qm_max is not None:
            q = q.filter(Listing.qm <= qm_max)
        if rooms_min is not None:
            q = q.filter(Listing.rooms >= rooms_min)

        # DB-level sort (except ppm which is computed)
        if sort == "date_desc":
            q = q.order_by(sqla_desc(Listing.last_seen_at))
        elif sort == "price_asc":
            q = q.order_by(asc(Listing.price_eur))
        elif sort == "price_desc":
            q = q.order_by(sqla_desc(Listing.price_eur))
        elif sort == "score_desc":
            q = q.order_by(sqla_desc(Listing.ai_score))
        # ppm_asc / ppm_desc: no DB sort, handle in Python below

        results = [ListingOut.model_validate(listing) for listing in q.all()]

        if sort == "ppm_asc":
            results.sort(key=lambda x: x.price_per_sqm or float("inf"))
        elif sort == "ppm_desc":
            results.sort(key=lambda x: x.price_per_sqm or 0, reverse=True)

        return results


@router.get("/{listing_id}", response_model=ListingOut)
def get_listing(listing_id: int):
    with db_module.SessionLocal() as session:
        listing = session.get(Listing, listing_id)
        if not listing:
            raise HTTPException(status_code=404, detail="Listing not found")
        return ListingOut.model_validate(listing)


@router.patch("/{listing_id}", response_model=ListingOut)
def patch_listing(listing_id: int, body: ListingPatch):
    with db_module.SessionLocal() as session:
        listing = session.get(Listing, listing_id)
        if not listing:
            raise HTTPException(status_code=404, detail="Listing not found")
        if body.status is not None:
            listing.status = body.status
        if body.notes is not None:
            listing.notes = body.notes
        session.commit()
        session.refresh(listing)
        return ListingOut.model_validate(listing)
