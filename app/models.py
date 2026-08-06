from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class PropertyType(StrEnum):
    WOHNUNG = "wohnung"
    HAUS = "haus"
    DOPPELHAUSHAELFTE = "doppelhaushaelfte"
    REIHENHAUS = "reihenhaus"
    GRUNDSTUECK = "grundstueck"
    UNKNOWN = "unknown"


class ListingStatus(StrEnum):
    NEW = "new"
    SEEN = "seen"
    CONTACTED = "contacted"
    VIEWING = "viewing"
    BID = "bid"
    REJECTED = "rejected"
    SOLD = "sold"


class RawListing(BaseModel):
    """Normalized output from a source adapter — pre-storage."""

    source: str
    source_id: str
    url: str
    title: str
    description: str | None = None
    price_eur: int | None = None
    qm: float | None = None
    rooms: float | None = None
    year_built: int | None = None
    property_type: PropertyType = PropertyType.UNKNOWN
    address: str | None = None
    plz: str | None = None
    city: str | None = None
    ortsteil: str | None = None
    lat: float | None = None
    lon: float | None = None
    geocode_confidence: float | None = None
    region_match_reason: str | None = None
    hausgeld_eur: int | None = None
    energie_kwh: float | None = None
    energie_class: str | None = None
    images: list[str] = Field(default_factory=list)
    raw_html: str | None = None
    listed_at: datetime | None = None
    fetched_at: datetime = Field(default_factory=datetime.utcnow)

    def dedup_hash(self) -> str:
        """Stable hash to detect cross-platform duplicates."""
        import hashlib

        parts = [
            (self.address or "").lower().strip(),
            f"{int(self.qm or 0)}",
            f"{(self.price_eur or 0) // 1000}",
        ]
        if not parts[0]:
            parts.append(self.source_id)
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]
