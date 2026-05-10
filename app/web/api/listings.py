from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, computed_field

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
    address: str | None
    url: str
    lage_score: int | None
    ai_score: int | None
    ai_reasoning: str | None
    status: str
    notes: str | None
    first_seen_at: datetime
    last_seen_at: datetime
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


@router.get("/", response_model=list[ListingOut])
def get_listings(
    status: str | None = None,
    portal: str | None = None,
    min_score: float | None = None,
):
    with db_module.SessionLocal() as session:
        q = session.query(Listing)
        if status:
            q = q.filter(Listing.status == status)
        if portal:
            q = q.filter(Listing.source == portal)
        if min_score is not None:
            q = q.filter(Listing.lage_score >= min_score)
        results = q.order_by(Listing.last_seen_at.desc()).all()
        return [ListingOut.model_validate(listing) for listing in results]


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
