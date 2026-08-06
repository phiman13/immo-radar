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

from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim

import app.db as db_module
from app.db import GeocodeCache
from app.logging_setup import log

USER_AGENT = "immo-radar-geocoder/0.1 (privates Immobilien-Scouting; Kontakt via immo.herrlich.dev)"

_geolocator = Nominatim(user_agent=USER_AGENT, timeout=10)
# RateLimiter blockiert synchron (time.sleep) — in der async-Pipeline heißt das:
# bis zu ~1s Event-Loop-Blockade pro Cache-Miss-Adresse. Bewusst akzeptiert, weil
# dieses Tool nur wenige Crawls pro Tag mit wenigen neuen Adressen fährt; ein
# Thread-Offload wäre hier reine Komplexität ohne spürbaren Gewinn.
_rate_limited_geocode = RateLimiter(
    _geolocator.geocode, min_delay_seconds=1.0, max_retries=0, swallow_exceptions=False
)


def _address_hash(address: str) -> str:
    normalized = " ".join(address.lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()[:32]


def _read_cache(session, key: str) -> tuple[float | None, float | None, float | None] | None:
    cached = session.get(GeocodeCache, key)
    if cached is None:
        return None
    return cached.lat, cached.lon, cached.importance


def geocode(address: str, session=None) -> tuple[float | None, float | None, float | None]:
    """Löst eine Adresse zu (lat, lon, importance) auf. Gecacht per Adress-Hash.

    Liefert (None, None, None) bei leerer Adresse, ohne Treffer, oder bei
    einem transienten Fehler. Ein transienter Fehler (Timeout, Service
    down) wird NICHT gecacht — der nächste Lauf versucht es erneut. Ein
    bestätigtes "keine solche Adresse" WIRD gecacht, weil eine Wiederholung
    sonst nur eine Anfrage verschwendet, ohne je ein anderes Ergebnis zu
    liefern.

    `session`: optionale SQLAlchemy-Session des Aufrufers. SQLite erlaubt nur
    EINEN Schreiber gleichzeitig — wer bereits eine schreibende Transaktion
    offen hält (z. B. `pipeline.run_source()`), muss sie hier durchreichen,
    sonst kollidiert der Cache-Write mit dem Schreib-Lock des Aufrufers
    ("database is locked") und reißt dessen ganzen Lauf mit in den Rollback.
    Mit übergebener Session wird NICHT committet — das übernimmt der Aufrufer
    mit seinem eigenen Commit (wie bei `pipeline._upsert`). Ohne Session
    öffnet und committet geocode() wie gehabt eine eigene.
    """
    if not address or not address.strip():
        return None, None, None

    key = _address_hash(address)
    if session is not None:
        hit = _read_cache(session, key)
    else:
        with db_module.SessionLocal() as own_session:
            hit = _read_cache(own_session, key)
    if hit is not None:
        return hit

    try:
        result = _rate_limited_geocode(address, exactly_one=True, addressdetails=False)
    except Exception as e:
        # Bewusst breit: geopy verpackt nicht jeden Transportfehler in
        # GeocoderServiceError (ssl.SSLError, socket.timeout, unerwartete
        # Response-Form). Jede Exception, die hier entkäme, würde über
        # pipeline._matches_profile den kompletten Quellenlauf rollbacken —
        # deshalb bleibt das hier ein transienter Fehler: kein Cache-Eintrag.
        log.warning("geocoding.transient_failure", address=address, error=str(e))
        return None, None, None

    lat = result.latitude if result else None
    lon = result.longitude if result else None
    importance = (result.raw or {}).get("importance") if result else None

    entry = GeocodeCache(
        address_hash=key,
        address=address[:500],
        lat=lat,
        lon=lon,
        importance=importance,
        created_at=datetime.utcnow(),
    )
    if session is not None:
        session.merge(entry)
        # SessionLocal läuft mit autoflush=False: ohne dieses Flush bliebe der
        # gemergte Eintrag pending und für ein späteres _read_cache() derselben
        # Transaktion unsichtbar. Zwei Objekte mit derselben Adresse in EINEM
        # Lauf erzeugten dann zwei pending INSERTs auf denselben Primary Key →
        # UNIQUE-Constraint-Fehler und Rollback des ganzen Quellenlaufs.
        # Flush, kein Commit — den Commit besitzt weiterhin der Aufrufer.
        session.flush()
    else:
        with db_module.SessionLocal() as own_session:
            own_session.merge(entry)
            own_session.commit()

    return lat, lon, importance
