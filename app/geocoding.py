"""Nominatim-Geocoding mit persistentem Adress-Cache.

Vollabdeckung-Spec §4.3: Adresse/PLZ -> Koordinaten, damit `in_search_area()`
in app/pipeline.py real gegen das Suchprofil prüfen kann statt (mangels
lat/lon) immer True zurückzugeben. Der Cache macht Wiederholungen für
dieselbe Adresse kostenlos und hält die Nominatim-Nutzungsrichtlinie
(max. 1 Anfrage/Sekunde) ein.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from geopy.exc import GeocoderServiceError
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim

import app.db as db_module
from app.db import GeocodeCache
from app.logging_setup import log

USER_AGENT = "immo-radar-geocoder/0.1 (privates Immobilien-Scouting; Kontakt via immo.herrlich.dev)"

_geolocator = Nominatim(user_agent=USER_AGENT, timeout=10)
_rate_limited_geocode = RateLimiter(
    _geolocator.geocode, min_delay_seconds=1.0, max_retries=0, swallow_exceptions=False
)


def _address_hash(address: str) -> str:
    normalized = " ".join(address.lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()[:32]


def geocode(address: str) -> tuple[float | None, float | None, float | None]:
    """Löst eine Adresse zu (lat, lon, importance) auf. Gecacht per Adress-Hash.

    Liefert (None, None, None) bei leerer Adresse, ohne Treffer, oder bei
    einem transienten Fehler. Ein transienter Fehler (Timeout, Service
    down) wird NICHT gecacht — der nächste Lauf versucht es erneut. Ein
    bestätigtes "keine solche Adresse" WIRD gecacht, weil eine Wiederholung
    sonst nur eine Anfrage verschwendet, ohne je ein anderes Ergebnis zu
    liefern.
    """
    if not address or not address.strip():
        return None, None, None

    key = _address_hash(address)
    with db_module.SessionLocal() as session:
        cached = session.get(GeocodeCache, key)
        if cached is not None:
            return cached.lat, cached.lon, cached.importance

    try:
        result = _rate_limited_geocode(address, exactly_one=True, addressdetails=False)
    except GeocoderServiceError as e:
        log.warning("geocoding.transient_failure", address=address, error=str(e))
        return None, None, None

    lat = result.latitude if result else None
    lon = result.longitude if result else None
    importance = (result.raw or {}).get("importance") if result else None

    with db_module.SessionLocal() as session:
        session.merge(
            GeocodeCache(
                address_hash=key,
                address=address[:500],
                lat=lat,
                lon=lon,
                importance=importance,
                created_at=datetime.utcnow(),
            )
        )
        session.commit()

    return lat, lon, importance
