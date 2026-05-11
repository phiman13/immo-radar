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
        ]:
            try:
                conn.execute(text(ddl))
                conn.commit()
            except Exception:
                pass  # Column already exists
