from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import select

from app.config import settings
from app.db import FetchRun, Listing, ListingHistory, SessionLocal
from app.geocoding import geocode
from app.logging_setup import log
from app.models import RawListing
from app.scoring.lage import in_search_area
from app.settings_service import get_setting
from app.sources import get_all_adapters

# Tutzing + 10km — explicit allowlist of cities/PLZs that count as "in scope".
# Core (5km): Tutzing, Feldafing, Pöcking, Bernried, Berg, Seeshaupt
# Extended (10km): Starnberg, Iffeldorf, Andechs (Herrsching), Weilheim-area edges
LOCATION_ALLOWLIST_RE = re.compile(
    r"\b("
    # core PLZs
    r"82327|82340|82343|82347|82335|82393|"
    # 10km extended PLZs
    r"82319|82389|82407|82362|82211|82418|82394|82211|"
    # core cities + Ortsteile
    r"Tutzing|Feldafing|Pöcking|Poecking|Bernried|Possenhofen|"
    r"Garatshausen|Diemendorf|Kampberg|Oberzeismering|Unterzeismering|Deixlfurt|Traubing|"
    r"Berg\s*\(|Berg/|Aufkirchen|Kempfenhausen|Allmannshausen|Assenhausen|Mörlbach|"
    r"Seeshaupt|St\.\s*Heinrich|Magnetsried|"
    # 10km extended cities
    r"Starnberg|Iffeldorf|Andechs|Herrsching|Pähl|Wielenbach"
    r")\b",
    re.IGNORECASE,
)

# Hard reject: commercial / service / non-housing junk that gets mixed in
JUNK_RE = re.compile(
    r"\b(coworking|büroetage|büroflache|bürofl(ä|ae)che|gewerbeflache|gewerbefl(ä|ae)che|"
    r"umzug(s|sservice|sfirma)?|m(ö|oe)beltransport|montage|dienstleistung|"
    r"pizzeria|restaurant|gastronomie|kiosk|laden|ladenlokal|"
    r"praxis|arztpraxis|kanzlei|tankstelle|werkstatt)\b",
    re.IGNORECASE,
)


def _location_ok(raw: RawListing) -> bool:
    haystack = " ".join(filter(None, [raw.address, raw.title, raw.city, raw.plz]))
    if not haystack.strip():
        # No location info at all → reject (safer than letting Aachen-style junk through)
        return False
    return bool(LOCATION_ALLOWLIST_RE.search(haystack))


def _is_junk(raw: RawListing) -> bool:
    haystack = " ".join(filter(None, [raw.title, raw.description]))
    return bool(JUNK_RE.search(haystack))


def _resolve_location(raw: RawListing, session) -> None:
    """Füllt raw.lat/lon per Geocoding, falls die Quelle sie nicht mitliefert,
    und dokumentiert in region_match_reason, worauf die spätere
    in_search_area()-Entscheidung beruht (Spec §4.3 Punkt 4).

    `session` ist die offene Schreib-Session des Aufrufers und wird an
    geocode() durchgereicht, damit der Cache-Write in derselben Transaktion
    landet statt als zweiter SQLite-Schreiber dagegen zu laufen."""
    if raw.lat is not None and raw.lon is not None:
        raw.region_match_reason = "coordinates-from-source"
        return

    address = " ".join(filter(None, [raw.address, raw.plz, raw.city])).strip()
    if not address:
        raw.region_match_reason = "no-address-info"
        return

    lat, lon, importance = geocode(address, session=session)
    if lat is not None and lon is not None:
        raw.lat, raw.lon = lat, lon
        raw.geocode_confidence = importance
        raw.region_match_reason = "geocoded"
    else:
        raw.region_match_reason = "geocode-failed-regex-fallback"


def _matches_profile(raw: RawListing, session) -> bool:
    if _is_junk(raw):
        return False
    if not _location_ok(raw):
        return False
    _resolve_location(raw, session)
    if raw.lat is not None and raw.lon is not None:
        if not in_search_area(raw.lat, raw.lon, get_setting("search_locations")):
            return False
    if raw.price_eur is not None:
        if raw.price_eur < settings.price_min or raw.price_eur > settings.price_max:
            return False
    if raw.qm is not None:
        if raw.qm < settings.qm_min or raw.qm > settings.qm_max:
            return False
    if raw.rooms is not None and raw.rooms < settings.rooms_min:
        return False
    if raw.year_built is not None and raw.year_built < settings.year_built_min:
        return False
    if raw.property_type.value not in settings.property_type_list and raw.property_type.value != "unknown":
        return False
    return True


def _upsert(session, raw: RawListing) -> tuple[Listing, bool]:
    """Insert if new, otherwise update + record changes. Returns (listing, is_new)."""
    h = raw.dedup_hash()
    existing: Listing | None = session.scalar(select(Listing).where(Listing.dedup_hash == h))
    now = datetime.utcnow()

    if existing is None:
        listing = Listing(
            dedup_hash=h,
            source=raw.source,
            source_id=raw.source_id,
            url=raw.url,
            title=raw.title,
            description=raw.description,
            price_eur=raw.price_eur,
            qm=raw.qm,
            rooms=raw.rooms,
            year_built=raw.year_built,
            property_type=raw.property_type.value,
            address=raw.address,
            plz=raw.plz,
            city=raw.city,
            ortsteil=raw.ortsteil,
            lat=raw.lat,
            lon=raw.lon,
            geocode_confidence=raw.geocode_confidence,
            region_match_reason=raw.region_match_reason,
            hausgeld_eur=raw.hausgeld_eur,
            energie_kwh=raw.energie_kwh,
            energie_class=raw.energie_class,
            images=raw.images,
            listed_at=raw.listed_at,
            first_seen_at=now,
            last_seen_at=now,
            is_active=True,
            status="new",
        )
        session.add(listing)
        session.flush()
        return listing, True

    # Track changes for important fields
    tracked = {
        "price_eur": raw.price_eur,
        "title": raw.title,
        "qm": raw.qm,
        "rooms": raw.rooms,
    }
    for field, new_val in tracked.items():
        old_val = getattr(existing, field)
        if new_val is not None and old_val != new_val:
            session.add(
                ListingHistory(
                    listing_id=existing.id,
                    field=field,
                    old_value=str(old_val),
                    new_value=str(new_val),
                )
            )
            setattr(existing, field, new_val)

    existing.last_seen_at = now
    existing.is_active = True
    # Nur überschreiben, wenn diesmal wirklich Koordinaten da sind: ein
    # transienter Geocoding-Fehler (Timeout) liefert lat/lon = None und würde
    # sonst bereits persistierte, gute Koordinaten stillschweigend nullen.
    if raw.lat is not None and raw.lon is not None:
        existing.lat = raw.lat
        existing.lon = raw.lon
        existing.geocode_confidence = raw.geocode_confidence
    # region_match_reason dokumentiert den JEWEILS letzten Versuch (auch den
    # gescheiterten) und wird deshalb bewusst unbedingt aktualisiert.
    existing.region_match_reason = raw.region_match_reason
    if raw.images and not existing.images:
        existing.images = raw.images
    return existing, False


async def run_source(adapter) -> tuple[int, int, list[Listing]]:
    """Run one source adapter. Returns (found, new, new_listings)."""
    found = 0
    new = 0
    new_listings: list[Listing] = []
    run = FetchRun(source=adapter.name)

    with SessionLocal() as session:
        session.add(run)
        session.flush()
        try:
            async with adapter:
                async for raw in adapter.fetch():
                    found += 1
                    if not _matches_profile(raw, session):
                        continue
                    listing, is_new = _upsert(session, raw)
                    if is_new:
                        new += 1
                        new_listings.append(listing)
            session.commit()
        except Exception as e:
            log.error("pipeline.source_failed", source=adapter.name, error=str(e))
            run.error = str(e)[:1000]
            session.rollback()

        run.finished_at = datetime.utcnow()
        run.listings_found = found
        run.listings_new = new
        with SessionLocal() as s2:
            s2.merge(run)
            s2.commit()

    log.info("pipeline.source_done", source=adapter.name, found=found, new=new)
    return found, new, new_listings


async def run_all() -> list[Listing]:
    """Run every adapter, return aggregated list of new listings."""
    all_new: list[Listing] = []
    for adapter in get_all_adapters():
        try:
            _, _, new_listings = await run_source(adapter)
            all_new.extend(new_listings)
        except Exception as e:
            log.error("pipeline.adapter_crashed", adapter=adapter.name, error=str(e))
    return all_new
