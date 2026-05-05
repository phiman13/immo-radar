from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class PropertyType(str, Enum):
    WOHNUNG = "wohnung"
    HAUS = "haus"
    DOPPELHAUSHAELFTE = "doppelhaushaelfte"
    REIHENHAUS = "reihenhaus"
    GRUNDSTUECK = "grundstueck"
    UNKNOWN = "unknown"


class ListingStatus(str, Enum):
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
    description: Optional[str] = None
    price_eur: Optional[int] = None
    qm: Optional[float] = None
    rooms: Optional[float] = None
    year_built: Optional[int] = None
    property_type: PropertyType = PropertyType.UNKNOWN
    address: Optional[str] = None
    plz: Optional[str] = None
    city: Optional[str] = None
    ortsteil: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    hausgeld_eur: Optional[int] = None
    energie_kwh: Optional[float] = None
    energie_class: Optional[str] = None
    images: list[str] = Field(default_factory=list)
    raw_html: Optional[str] = None
    listed_at: Optional[datetime] = None
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
