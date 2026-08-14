"""Tests für app.pipeline — insbesondere die Geocoding-Integration, die den
Regionsfilter repariert (Vollabdeckung-Spec §4.3)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db as db_module
import app.pipeline as pipeline_module
from app.db import Base, FetchRun, GeocodeCache, Listing
from app.models import PropertyType, RawListing
from app.pipeline import _matches_profile, _upsert
from app.settings_service import set_setting

TUTZING_LOCATIONS = [{"lat": 47.9095, "lon": 11.2783, "radius_km": 5, "label": "Tutzing"}]


@pytest.fixture()
def session(monkeypatch, tmp_path):
    test_engine = create_engine(f"sqlite:///{tmp_path}/test.db", echo=False, future=True)
    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)
    return TestSession


def _raw(**overrides) -> RawListing:
    defaults = dict(
        source="test",
        source_id="1",
        url="https://example.de/1",
        title="Haus in Tutzing",
        address="Bahnhofstr. 1, 82327 Tutzing",
        price_eur=800_000,
        qm=140,
        property_type=PropertyType.HAUS,
    )
    defaults.update(overrides)
    return RawListing(**defaults)


def test_matches_profile_accepts_geocoded_object_in_area(session):
    set_setting("search_locations", TUTZING_LOCATIONS)
    raw = _raw()
    with session() as s, patch("app.pipeline.geocode", return_value=(47.9095, 11.2783, 0.6)):
        assert _matches_profile(raw, s) is True
    assert raw.region_match_reason == "geocoded"
    assert raw.geocode_confidence == 0.6
    assert raw.lat == 47.9095


def test_matches_profile_rejects_geocoded_object_outside_area(session):
    """Regression für den historischen Bug: früher gab in_search_area() ohne
    lat/lon immer True zurück, egal wo das Objekt tatsächlich lag. "Starnberg"
    im Titel darf hier nicht durchrutschen — die echten geocodierten
    Koordinaten (München) müssen den Regionsfilter greifen lassen."""
    set_setting("search_locations", TUTZING_LOCATIONS)
    raw = _raw(
        address="Marienplatz 1, 80331 München",
        title="Wohnung München (erwähnt Starnberg im Text)",
    )
    with session() as s, patch("app.pipeline.geocode", return_value=(48.1374, 11.5755, 0.7)):
        assert _matches_profile(raw, s) is False


def test_matches_profile_uses_source_coordinates_without_geocoding(session):
    set_setting("search_locations", TUTZING_LOCATIONS)
    raw = _raw(lat=47.91, lon=11.28)
    with session() as s, patch("app.pipeline.geocode") as mock_geocode:
        assert _matches_profile(raw, s) is True
        mock_geocode.assert_not_called()
    assert raw.region_match_reason == "coordinates-from-source"


def test_matches_profile_accepts_without_region_check_on_geocode_failure(session):
    """HER-807: seit dem Wegfall des hartkodierten Regionsfilters gibt es bei
    einem Geocoding-Fehlschlag KEINE Regionsprüfung mehr -- das Objekt wird
    nur noch über die übrigen Filter (Preis/Fläche/Zimmer/Objektart/Junk)
    beurteilt. Bewusste Design-Entscheidung, siehe Kommentar in
    _resolve_location()."""
    set_setting("search_locations", TUTZING_LOCATIONS)
    raw = _raw()
    with session() as s, patch("app.pipeline.geocode", return_value=(None, None, None)):
        assert _matches_profile(raw, s) is True
    assert raw.region_match_reason == "geocode-failed"


def test_matches_profile_rejects_without_geocoding_when_no_location_text(session):
    """_location_ok() spart den Geocoding-Call, wenn wirklich gar kein Orts-/
    Adresshinweis vorhanden ist (HER-807: seit dem Wegfall des hartkodierten
    Städte-/PLZ-Regex-Vorfilters ist das die einzige verbleibende
    Vorprüfung — Text mit unbekanntem Ortsnamen wird jetzt bewusst NICHT
    mehr hier verworfen, sondern korrekt an in_search_area() weitergereicht,
    siehe test_matches_profile_geocodes_even_unrecognized_location_text)."""
    raw = _raw(address=None, city=None, plz=None, title="")
    with session() as s, patch("app.pipeline.geocode") as mock_geocode:
        assert _matches_profile(raw, s) is False
        mock_geocode.assert_not_called()


def test_matches_profile_geocodes_even_unrecognized_location_text(session):
    """Regression HER-807: ein früherer hartkodierter Städte-/PLZ-Regex
    verwarf Objekte mit Ortstext außerhalb einer festen Tutzing-Liste schon
    VOR dem Geocoding — unabhängig davon, was der Nutzer als Suchgebiet
    konfiguriert hatte. "Musterstadt" ist in keiner hartkodierten Liste,
    muss aber trotzdem bis zum echten, DB-gesteuerten Radius-Check
    durchgereicht werden."""
    set_setting("search_locations", TUTZING_LOCATIONS)
    raw = _raw(address=None, city="Musterstadt", plz="99999", title="Haus in Musterstadt")
    with session() as s, patch("app.pipeline.geocode", return_value=(47.9095, 11.2783, 0.6)) as mock_geocode:
        assert _matches_profile(raw, s) is True
        mock_geocode.assert_called_once()


def test_matches_profile_uses_db_persisted_price_range_not_static_config(session):
    """Regression: _matches_profile las Preis/Fläche/Zimmer/Baujahr/Objektart
    bisher aus dem STATISCHEN app.config.settings-Objekt (.env-Werte beim
    Prozessstart), nicht aus den DB-persistenten Dashboard-Settings, die
    settings_service.set_setting() schreibt -- eine Preisrahmen-Änderung im
    Dashboard hatte dadurch NULL Effekt auf die tatsächliche Filterung (real
    beobachtet in Produktion: price_max im Dashboard auf 1.8 Mio. gesetzt,
    Pipeline filterte weiterhin gegen den alten .env-Wert 1.1 Mio.,
    siehe docs/STATUS.md 2026-08-14). Ein Preis, der die DB-Grenze
    unterschreitet, aber über einem absichtlich ANDEREN, engeren
    .env-Default läge, darf nur durchkommen, wenn tatsächlich der
    DB-Wert gilt."""
    set_setting("price_min", 500_000)
    set_setting("price_max", 3_000_000)
    set_setting("qm_min", 90)
    set_setting("qm_max", 500)
    set_setting("rooms_min", 2.0)
    set_setting("year_built_min", 1900)
    set_setting("property_types", "haus,villa")

    raw = _raw(price_eur=2_500_000, qm=300, rooms=4, property_type=PropertyType.HAUS)
    with session() as s, patch("app.pipeline.geocode", return_value=(47.9095, 11.2783, 0.6)):
        assert _matches_profile(raw, s) is True


def test_matches_profile_rejects_price_above_db_persisted_max(session):
    set_setting("price_min", 500_000)
    set_setting("price_max", 900_000)

    raw = _raw(price_eur=2_500_000)
    with session() as s, patch("app.pipeline.geocode", return_value=(47.9095, 11.2783, 0.6)):
        assert _matches_profile(raw, s) is False


def test_upsert_persists_geocoding_metadata(session):
    raw = _raw()
    raw.lat, raw.lon = 47.9095, 11.2783
    raw.geocode_confidence = 0.6
    raw.region_match_reason = "geocoded"

    with session() as s:
        listing, is_new = _upsert(s, raw)
        s.commit()
        assert is_new is True
        assert listing.geocode_confidence == 0.6
        assert listing.region_match_reason == "geocoded"

    raw.region_match_reason = "geocode-failed"
    raw.geocode_confidence = None

    with session() as s:
        listing, is_new = _upsert(s, raw)
        s.commit()
        assert is_new is False
        assert listing.region_match_reason == "geocode-failed"
        assert listing.geocode_confidence is None


def test_upsert_keeps_good_coordinates_when_regeocoding_fails(session):
    """Ein transienter Geocoding-Fehler beim Wiedersehen eines Objekts liefert
    lat/lon/confidence = None. Diese None-Werte dürfen die bereits
    persistierten, guten Koordinaten NICHT überschreiben — sonst verliert das
    Objekt still seine Kartenposition, bis der nächste Lauf zufällig
    durchkommt. region_match_reason dokumentiert dagegen den letzten Versuch
    und wird sehr wohl aktualisiert."""
    raw = _raw()
    raw.lat, raw.lon = 47.9095, 11.2783
    raw.geocode_confidence = 0.6
    raw.region_match_reason = "geocoded"

    with session() as s:
        _, is_new = _upsert(s, raw)
        s.commit()
        assert is_new is True

    failed = _raw()  # gleiche Adresse/qm/Preis → gleicher dedup_hash
    failed.lat = None
    failed.lon = None
    failed.geocode_confidence = None
    failed.region_match_reason = "geocode-failed"

    with session() as s:
        listing, is_new = _upsert(s, failed)
        s.commit()
        assert is_new is False
        assert listing.lat == 47.9095
        assert listing.lon == 11.2783
        assert listing.geocode_confidence == 0.6
        assert listing.region_match_reason == "geocode-failed"

    with session() as s:
        persisted = s.query(Listing).one()
        assert persisted.lat == 47.9095
        assert persisted.lon == 11.2783
        assert persisted.geocode_confidence == 0.6


class _FakeAdapter:
    """Minimaler SourceAdapter-Ersatz: async-Context-Manager, der die
    übergebenen RawListings ausliefert — ohne Netzwerk, ohne httpx."""

    def __init__(self, name: str, raws: list[RawListing]) -> None:
        self.name = name
        self._raws = raws

    async def __aenter__(self) -> _FakeAdapter:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def fetch(self):
        for raw in self._raws:
            yield raw


@pytest.mark.asyncio
async def test_run_source_survives_geocode_cache_miss_inside_open_transaction(session, monkeypatch):
    """Regression gegen den SQLite-Write-Lock-Deadlock.

    run_source() hält über den gesamten fetch()-Lauf eine schreibende
    Transaktion offen (session.add(run) + flush). Ein Geocoding-Cache-MISS
    schrieb seinen Cache-Eintrag früher über eine ZWEITE Session — SQLite
    erlaubt aber nur einen Schreiber: 'database is locked', gefangen vom
    breiten except in run_source, session.rollback() — und damit waren ALLE
    bereits geupserteten Listings dieses Laufs weg.

    Der Test fährt run_source() gegen echtes (ungemocktes) geocode() und eine
    echte SQLite-Datei; gemockt ist nur der Netz-Call. Die DB ist frisch, die
    Adressen sind neu → garantierter Cache-MISS, also genau der Pfad, der den
    zweiten Schreiber ausgelöst hat (belegt durch die Assertion auf zwei
    frisch geschriebene GeocodeCache-Zeilen)."""
    monkeypatch.setattr(pipeline_module, "SessionLocal", session)
    set_setting("search_locations", TUTZING_LOCATIONS)

    calls: list[str] = []

    def fake_nominatim(address, **kwargs):
        calls.append(address)
        return SimpleNamespace(latitude=47.9095, longitude=11.2783, raw={"importance": 0.6})

    monkeypatch.setattr("app.geocoding._rate_limited_geocode", fake_nominatim)

    raws = [
        _raw(source_id="1", url="https://example.de/1", address="Bahnhofstr. 1, 82327 Tutzing"),
        _raw(source_id="2", url="https://example.de/2", address="Hauptstr. 2, 82327 Tutzing"),
    ]

    found, new, new_listings = await pipeline_module.run_source(_FakeAdapter("fake", raws))

    assert found == 2
    assert new == 2
    assert len(new_listings) == 2
    assert len(calls) == 2  # beides echte Cache-Misses → echter Nominatim-Call

    with session() as s:
        run = s.query(FetchRun).one()
        assert run.error is None
        assert run.listings_found == 2
        assert run.listings_new == 2

        listings = s.query(Listing).order_by(Listing.source_id).all()
        assert len(listings) == 2
        assert [ln.lat for ln in listings] == [47.9095, 47.9095]
        assert {ln.region_match_reason for ln in listings} == {"geocoded"}

        # Der Cache-Write landete in derselben Transaktion und ist mit-committet
        assert s.query(GeocodeCache).count() == 2


@pytest.mark.asyncio
async def test_run_source_survives_duplicate_address_before_first_upsert(session, monkeypatch):
    """Regression gegen den UNIQUE-Constraint-Crash bei doppelter Adresse.

    `SessionLocal` läuft mit autoflush=False: ein `session.merge()` im
    Geocoding-Cache bleibt PENDING und ist damit für ein späteres
    `session.get(GeocodeCache, key)` derselben Transaktion unsichtbar (ohne
    Identity-Key kein Identity-Map-Treffer, ohne Autoflush kein DB-Treffer).

    Teilen sich zwei Objekte EINES Laufs dieselbe Geocoding-Adresse und wurde
    dazwischen nichts geflusht (weil ein NACH dem Geocoding laufender Filter —
    hier der Preisfilter — sie verwirft, `_upsert` also nie greift), dann
    entstehen zwei pending INSERTs auf denselben Primary Key. Spätestens beim
    ersten echten Flush wirft SQLite
    `UNIQUE constraint failed: geocode_cache.address_hash`; das breite except
    in run_source() rollbackt daraufhin den KOMPLETTEN Quellenlauf — inklusive
    aller bis dahin gültigen Objekte.

    Der Fix ist ein `session.flush()` direkt nach dem `session.merge()` im
    Session-Pfad von geocode(): der Cache-Eintrag wird sofort sichtbar, der
    zweite Treffer ist ein echter Cache-HIT (belegt durch `len(calls) == 1`)."""
    monkeypatch.setattr(pipeline_module, "SessionLocal", session)
    set_setting("price_max", 1_000_000)
    set_setting("search_locations", TUTZING_LOCATIONS)

    calls: list[str] = []

    def fake_nominatim(address, **kwargs):
        calls.append(address)
        return SimpleNamespace(latitude=47.9095, longitude=11.2783, raw={"importance": 0.6})

    monkeypatch.setattr("app.geocoding._rate_limited_geocode", fake_nominatim)

    # Identischer Adress-String für alle drei ("82327 Tutzing"), aber nur das
    # letzte Objekt passiert den Preisfilter — davor flusht also nichts.
    shared = dict(address=None, plz="82327", city="Tutzing")
    raws = [
        _raw(source_id="1", url="https://example.de/1", price_eur=5_000_000, **shared),
        _raw(source_id="2", url="https://example.de/2", price_eur=5_000_000, **shared),
        _raw(source_id="3", url="https://example.de/3", price_eur=800_000, **shared),
    ]

    found, new, new_listings = await pipeline_module.run_source(_FakeAdapter("fake", raws))

    assert found == 3
    assert new == 1
    assert len(new_listings) == 1
    assert calls == ["82327 Tutzing"]  # ein Miss, danach Cache-HITs

    with session() as s:
        run = s.query(FetchRun).one()
        assert run.error is None

        listings = s.query(Listing).all()
        assert len(listings) == 1
        assert listings[0].source_id == "3"
        assert listings[0].lat == 47.9095
        assert listings[0].region_match_reason == "geocoded"

        assert s.query(GeocodeCache).count() == 1
