from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    dedup_hash: Mapped[str] = mapped_column(String(32), unique=True, index=True)

    source: Mapped[str] = mapped_column(String(64), index=True)
    source_id: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(1000))

    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text, default=None)

    price_eur: Mapped[int | None] = mapped_column(Integer, default=None, index=True)
    qm: Mapped[float | None] = mapped_column(Float, default=None)
    rooms: Mapped[float | None] = mapped_column(Float, default=None)
    year_built: Mapped[int | None] = mapped_column(Integer, default=None)
    property_type: Mapped[str] = mapped_column(String(32), default="unknown")

    address: Mapped[str | None] = mapped_column(String(500), default=None)
    plz: Mapped[str | None] = mapped_column(String(10), default=None, index=True)
    city: Mapped[str | None] = mapped_column(String(100), default=None)
    ortsteil: Mapped[str | None] = mapped_column(String(100), default=None)
    lat: Mapped[float | None] = mapped_column(Float, default=None)
    lon: Mapped[float | None] = mapped_column(Float, default=None)
    geocode_confidence: Mapped[float | None] = mapped_column(Float, default=None)
    region_match_reason: Mapped[str | None] = mapped_column(String(64), default=None)

    hausgeld_eur: Mapped[int | None] = mapped_column(Integer, default=None)
    energie_kwh: Mapped[float | None] = mapped_column(Float, default=None)
    energie_class: Mapped[str | None] = mapped_column(String(8), default=None)

    images: Mapped[list] = mapped_column(JSON, default=list)

    status: Mapped[str] = mapped_column(String(32), default="new", index=True)
    notes: Mapped[str | None] = mapped_column(Text, default=None)

    ai_score: Mapped[int | None] = mapped_column(Integer, default=None, index=True)
    ai_reasoning: Mapped[str | None] = mapped_column(Text, default=None)
    enrich_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    risk_flags: Mapped[list] = mapped_column(JSON, default=list)
    lage_score: Mapped[int | None] = mapped_column(Integer, default=None)
    bodenrichtwert: Mapped[int | None] = mapped_column(Integer, default=None)

    notified_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    listed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    history: Mapped[list[ListingHistory]] = relationship(
        back_populates="listing", cascade="all, delete-orphan"
    )


class ListingHistory(Base):
    __tablename__ = "listing_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    field: Mapped[str] = mapped_column(String(64))
    old_value: Mapped[str | None] = mapped_column(Text, default=None)
    new_value: Mapped[str | None] = mapped_column(Text, default=None)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    listing: Mapped[Listing] = relationship(back_populates="history")


class FetchRun(Base):
    __tablename__ = "fetch_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    listings_found: Mapped[int] = mapped_column(Integer, default=0)
    listings_new: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, default=None)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    last_run: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    listing_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    source_type: Mapped[str] = mapped_column(String, default="builtin", server_default="builtin")


class ApiUsage(Base):
    __tablename__ = "api_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    model: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    purpose: Mapped[str] = mapped_column(String(32))  # "enrichment" | "analyze" | "discover"


COVERAGE_STATUSES = (
    "unknown",
    "auto-harvested",
    "needs-manual-watch",
    "unreachable",
    "bot-blocked",
    "login-required",
    "robots-disallowed",
)


class Agent(Base):
    """Makler-Entität + Coverage-Register (Vollabdeckung-Spec §5.1).

    `unknown` ist bewusst der Default und zählt nie als abgedeckt — ein Status
    gilt erst mit frischem Beleg (`last_checked` innerhalb des
    Staleness-Fensters, siehe Phase 2/4)."""

    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str | None] = mapped_column(String(100), default=None)

    discovery_sources: Mapped[list] = mapped_column(JSON, default=list)
    verified_domain: Mapped[str | None] = mapped_column(String(255), default=None)
    domain_candidates: Mapped[list] = mapped_column(JSON, default=list)
    imprint_match: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    listing_url: Mapped[str | None] = mapped_column(String(1000), default=None)

    extraction: Mapped[dict] = mapped_column(JSON, default=dict)
    recipe_verified_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    coverage_status: Mapped[str] = mapped_column(
        String(32), default="unknown", server_default="unknown", index=True
    )
    coverage_reason: Mapped[str | None] = mapped_column(Text, default=None)
    robots_status: Mapped[str | None] = mapped_column(String(32), default=None)

    last_checked: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    last_nonempty_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    last_listing_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    next_review_due: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class GeocodeCache(Base):
    """Adress-Hash → Koordinaten. Macht wiederholte Geocoding-Anfragen für
    dieselbe Adresse kostenlos (Vollabdeckung-Spec §4.3)."""

    __tablename__ = "geocode_cache"

    address_hash: Mapped[str] = mapped_column(String(32), primary_key=True)
    address: Mapped[str] = mapped_column(String(500))
    lat: Mapped[float | None] = mapped_column(Float, default=None)
    lon: Mapped[float | None] = mapped_column(Float, default=None)
    importance: Mapped[float | None] = mapped_column(Float, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


def _ensure_db_dir() -> None:
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)


_ensure_db_dir()
engine = create_engine(f"sqlite:///{settings.db_path}", echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)
    with engine.connect() as conn:
        for ddl in [
            "ALTER TABLE sources ADD COLUMN url TEXT",
            "ALTER TABLE sources ADD COLUMN source_type TEXT DEFAULT 'builtin'",
            "ALTER TABLE listings ADD COLUMN geocode_confidence REAL",
            "ALTER TABLE listings ADD COLUMN region_match_reason TEXT",
            (
                "CREATE TABLE IF NOT EXISTS api_usage "
                "(id INTEGER PRIMARY KEY, ts DATETIME, model TEXT, "
                "input_tokens INTEGER, output_tokens INTEGER, purpose TEXT)"
            ),
            "CREATE INDEX IF NOT EXISTS ix_api_usage_ts ON api_usage (ts)",
        ]:
            try:
                conn.execute(text(ddl))
                conn.commit()
            except Exception as e:
                if "duplicate column name" not in str(e).lower() and "already exists" not in str(e).lower():
                    raise
