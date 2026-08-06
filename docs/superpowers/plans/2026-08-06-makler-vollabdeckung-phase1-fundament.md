# Makler-Vollabdeckung — Phase 1 (Fundament) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Legt das Datenmodell- und Plumbing-Fundament für die Erfassung von Objekten auf Makler-eigenen Websites: `agents`-Tabelle (Coverage-Register), ein generischer DB-getriebener Adapter (additiv zur bestehenden `REGISTRY`), Geocoding beim Ingest mit persistentem Cache (repariert den Regionsfilter, der heute wegen fehlender Koordinaten wirkungslos ist), und ein ehrlicher, höflicher Zugriff (echter User-Agent, `robots.txt`-Respekt).

**Architecture:** Neue Tabellen `agents` + `geocode_cache` treten neben die bestehenden `sources`/`listings` — kein Big-Bang-Umbau. `AgentSiteSource` ist ein neuer `SourceAdapter`, der `agents`-Zeilen mit `coverage_status = "auto-harvested"` an registrierte Extraktionsmethoden (`EXTRACTION_METHODS`, in Phase 1 noch leer) verteilt; Phase 2 füllt diese Registry mit den acht Vendor-Adaptern + struktureller Detail-Link-Erkennung. Geocoding läuft synchron (Nominatim via `geopy`, gecacht) und wird in `app/pipeline.py`s Regionsfilter verdrahtet — die alte Ortsnamen-Regex bleibt als kostensparender Vorfilter und Fallback bei Geocoding-Fehlschlag erhalten, ist aber nicht mehr der Hauptfilter.

**Tech Stack:** Python 3.11+, SQLAlchemy 2.0 (declarative, synchron), httpx (async), `geopy` (bereits in `pyproject.toml`, bisher ungenutzt), pytest + pytest-asyncio, ruff.

**Nicht Teil dieses Plans (Phase 2):** Vendor-Adapter (onOffice, immonex, OpenImmo2WP, WP-ImmoMakler, Propstack, cursor-cms, TYPO3-OpenImmo, IS24-Widget), vokabularfreie strukturelle Detail-Link-Erkennung (`is_object_like`/`find_detail_links` aus `scripts/probe_agent_sites.py`), Change-Gate-Fingerprint, Selbsttest/Bruch-Erkennung, `field_completeness`, HTML-Fixtures. Diese folgen in einem eigenen, späteren Plan, sobald dieses Schema steht.

## Global Constraints

- Python 3.11+ Zielversion (ruff `target-version = "py311"`, `line-length = 110`, `select = ["E","F","I","B","UP"]`).
- `ruff check .` hat **schon vor diesem Plan** 26 Altlast-Fehler in `app/models.py` (19, überwiegend `UP045` „Optional[X] → X | None"), `app/sources/base.py` (1, `UP037`), `app/sources/immoscout24.py`, `app/sources/makler_riedel.py`, `app/sources/makler_starnberg_immo.py`, `app/sources/tutzing24.py`, `app/web/auth.py` — nicht Teil dieses Plans, nicht beheben (unrelated refactoring). Alle neuen Dateien in diesem Plan müssen 0 ruff-Fehler haben. In `app/models.py` und `app/sources/base.py` neue Zeilen im bestehenden `Optional[...]`-Stil der jeweiligen Datei halten (matcht die Nachbarzeilen 1:1) — das erzeugt keine neuen Fehler über die bereits vorhandenen hinaus.
- DB-Zugriff aus neuen/geänderten Modulen immer über `import app.db as db_module` + `db_module.SessionLocal()` **zur Aufrufzeit** — NIE `from app.db import SessionLocal` auf Modulebene. Grund: Tests patchen `db_module.SessionLocal` per `monkeypatch.setattr`; ein `from ... import SessionLocal` bindet den Namen beim ersten Modul-Import in die lokale Namespace und sieht das Patch danach nicht mehr. Referenzmuster: `app/settings_service.py` (macht es richtig). Klassen (`Agent`, `GeocodeCache`, `Listing`, ...) dürfen weiterhin normal per `from app.db import X` importiert werden — nur der Session-Factory-Name braucht die dynamische Bindung.
- Lokale Skript-/Testläufe brauchen `DB_PATH=./data/immo.db` (oder einen beliebigen lokalen Pfad) als Env-Override — `.env` zeigt auf den Docker-internen Pfad `/app/data/immo.db`, der lokal nicht existiert und beim Import von `app.db` (`_ensure_db_dir()`) einen Fehler werfen kann.
- Bestehende 55 Tests müssen nach jedem Task grün bleiben: `DB_PATH=./data/immo.db .venv/bin/python -m pytest -q`.
- Commit **und Push** nach jedem Task (Repo-Konvention aus `.claude/CONVENTIONS.md`): `git add -A && git commit -m "..." && git push`.
- Neue SQLAlchemy-Modelle mit JSON-Spalten verwenden `default=dict`/`default=list` (Callable), nie `default={}`/`default=[]` (Mutable-Default-Bug) — Referenzmuster: `Listing.images` in `app/db.py`.

---

### Task 1: Schema — `agents` + `geocode_cache` Tabellen, Listing-Erweiterung um Geocoding-Metadaten

**Files:**
- Modify: `app/db.py`
- Test: `tests/test_agents_model.py` (neu)

**Interfaces:**
- Produces: `app.db.Agent` (SQLAlchemy-Modell, Tabelle `agents`), `app.db.GeocodeCache` (Tabelle `geocode_cache`), `app.db.COVERAGE_STATUSES: tuple[str, ...]`, neue Spalten `Listing.geocode_confidence: float | None`, `Listing.region_match_reason: str | None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_agents_model.py`:

```python
"""Tests für die neuen Modelle Agent und GeocodeCache (Phase 1: Fundament)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db as db_module
from app.db import COVERAGE_STATUSES, Agent, Base, GeocodeCache, Listing


@pytest.fixture()
def session(monkeypatch, tmp_path):
    """Isolierte In-Memory-DB pro Test — Referenzmuster: tests/test_db_models.py."""
    test_engine = create_engine(f"sqlite:///{tmp_path}/test.db", echo=False, future=True)
    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)
    return TestSession


def test_coverage_statuses_constant():
    assert COVERAGE_STATUSES == (
        "unknown",
        "auto-harvested",
        "needs-manual-watch",
        "unreachable",
        "bot-blocked",
        "login-required",
        "robots-disallowed",
    )


def test_agent_defaults_to_unknown_coverage(session):
    """Kernanforderung aus dem Spec: `unknown` ist Default und zählt nie als
    abgedeckt, ohne dass eine Zeile das explizit setzen muss."""
    with session() as s:
        agent = Agent(name="Testmakler Tutzing")
        s.add(agent)
        s.commit()

        fetched = s.query(Agent).filter_by(name="Testmakler Tutzing").first()
        assert fetched is not None
        assert fetched.coverage_status == "unknown"
        assert fetched.discovery_sources == []
        assert fetched.domain_candidates == []
        assert fetched.extraction == {}
        assert fetched.imprint_match is False
        assert fetched.last_listing_count == 0
        assert fetched.verified_domain is None
        assert fetched.last_checked is None


def test_agent_full_roundtrip(session):
    with session() as s:
        agent = Agent(
            name="Beispiel Immobilien",
            city="Starnberg",
            discovery_sources=["makler-empfehlung.de", "websuche"],
            verified_domain="beispiel-immobilien.de",
            domain_candidates=["beispiel-immobilien.de", "beispiel-immo.de"],
            imprint_match=True,
            listing_url="https://beispiel-immobilien.de/angebote/",
            extraction={"method": "vendor:onoffice", "vendor": "onoffice"},
            coverage_status="auto-harvested",
            coverage_reason=None,
            robots_status="allowed",
            last_listing_count=12,
        )
        s.add(agent)
        s.commit()
        agent_id = agent.id

    with session() as s:
        fetched = s.get(Agent, agent_id)
        assert fetched.city == "Starnberg"
        assert fetched.discovery_sources == ["makler-empfehlung.de", "websuche"]
        assert fetched.extraction["vendor"] == "onoffice"
        assert fetched.coverage_status == "auto-harvested"
        assert fetched.last_listing_count == 12
        s.delete(fetched)
        s.commit()


def test_geocode_cache_crud(session):
    with session() as s:
        row = GeocodeCache(
            address_hash="abc123",
            address="Bahnhofstr. 1, 82327 Tutzing",
            lat=47.9095,
            lon=11.2783,
            importance=0.55,
        )
        s.add(row)
        s.commit()

        fetched = s.get(GeocodeCache, "abc123")
        assert fetched.lat == 47.9095
        assert fetched.address == "Bahnhofstr. 1, 82327 Tutzing"
        s.delete(fetched)
        s.commit()


def test_listing_geocoding_columns_default_none(session):
    with session() as s:
        listing = Listing(
            dedup_hash="x" * 16,
            source="test",
            source_id="1",
            url="https://example.de/1",
            title="Testobjekt",
        )
        s.add(listing)
        s.commit()

        fetched = s.query(Listing).filter_by(dedup_hash="x" * 16).first()
        assert fetched.geocode_confidence is None
        assert fetched.region_match_reason is None
        s.delete(fetched)
        s.commit()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DB_PATH=./data/immo.db .venv/bin/python -m pytest tests/test_agents_model.py -v`
Expected: FAIL (ImportError — `COVERAGE_STATUSES`/`Agent`/`GeocodeCache` existieren noch nicht in `app.db`)

- [ ] **Step 3: Write minimal implementation**

In `app/db.py`, füge nach `Listing.lon` (Zeile mit `lon: Mapped[float | None] = mapped_column(Float, default=None)`, vor `hausgeld_eur`) zwei neue Spalten ein:

```python
    lat: Mapped[float | None] = mapped_column(Float, default=None)
    lon: Mapped[float | None] = mapped_column(Float, default=None)
    geocode_confidence: Mapped[float | None] = mapped_column(Float, default=None)
    region_match_reason: Mapped[str | None] = mapped_column(String(64), default=None)

    hausgeld_eur: Mapped[int | None] = mapped_column(Integer, default=None)
```

Nach der `ApiUsage`-Klasse (vor `def _ensure_db_dir()`), füge ein:

```python
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
```

In `init_db()`, füge der DDL-Liste zwei weitere ALTER-Statements hinzu (Migration für eine bereits existierende Produktions-`listings`-Tabelle — `agents`/`geocode_cache` sind neue Tabellen und werden von `Base.metadata.create_all(engine)` bereits automatisch angelegt):

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `DB_PATH=./data/immo.db .venv/bin/python -m pytest tests/test_agents_model.py tests/test_db_models.py -v`
Expected: PASS (alle neuen + bestehenden DB-Modell-Tests grün)

- [ ] **Step 5: Regression + ruff**

Run: `DB_PATH=./data/immo.db .venv/bin/python -m pytest -q && ruff check app/db.py tests/test_agents_model.py`
Expected: `55 passed` + die neuen Tests zusätzlich grün (insgesamt 59), `ruff check` auf den beiden neuen/geänderten Dateien ohne Fehler.

- [ ] **Step 6: Commit**

```bash
git add app/db.py tests/test_agents_model.py
git commit -m "feat(db): agents-Tabelle als Coverage-Register + geocode_cache + Listing-Geocoding-Spalten

unknown ist Default-coverage_status und zählt nie als abgedeckt (Spec §5.1)."
git push
```

---

### Task 2: `app/geocoding.py` — Nominatim-Geocoding mit persistentem Cache

**Files:**
- Create: `app/geocoding.py`
- Test: `tests/test_geocoding.py` (neu)

**Interfaces:**
- Consumes: `app.db.GeocodeCache` (Task 1), `app.db` als Modul (dynamischer `SessionLocal`-Zugriff, siehe Global Constraints).
- Produces: `app.geocoding.geocode(address: str) -> tuple[float | None, float | None, float | None]` (lat, lon, importance).

- [ ] **Step 1: Write the failing test**

Create `tests/test_geocoding.py`:

```python
"""Tests für app.geocoding — Nominatim mit persistentem Adress-Cache."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from geopy.exc import GeocoderServiceError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db as db_module
from app.db import Base, GeocodeCache
from app.geocoding import geocode


@pytest.fixture()
def session(monkeypatch, tmp_path):
    test_engine = create_engine(f"sqlite:///{tmp_path}/test.db", echo=False, future=True)
    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)
    return TestSession


def test_geocode_empty_address_skips_nominatim(session, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.geocoding._rate_limited_geocode",
        lambda *a, **kw: calls.append(1),
    )
    assert geocode("") == (None, None, None)
    assert geocode("   ") == (None, None, None)
    assert calls == []


def test_geocode_cache_miss_then_hit(session, monkeypatch):
    calls = []

    def fake_geocode(address, **kwargs):
        calls.append(address)
        return SimpleNamespace(latitude=47.91, longitude=11.28, raw={"importance": 0.55})

    monkeypatch.setattr("app.geocoding._rate_limited_geocode", fake_geocode)

    result1 = geocode("Bahnhofstr. 1, 82327 Tutzing")
    assert result1 == (47.91, 11.28, 0.55)
    assert len(calls) == 1

    result2 = geocode("Bahnhofstr. 1, 82327 Tutzing")
    assert result2 == (47.91, 11.28, 0.55)
    assert len(calls) == 1  # Cache-Treffer — kein zweiter Nominatim-Call

    with session() as s:
        row = s.query(GeocodeCache).first()
        assert row is not None
        assert row.address == "Bahnhofstr. 1, 82327 Tutzing"
        assert row.lat == 47.91


def test_geocode_normalizes_whitespace_for_cache_key(session, monkeypatch):
    """'Bahnhofstr.  1,   82327  Tutzing' und 'bahnhofstr. 1, 82327 tutzing'
    müssen denselben Cache-Eintrag treffen."""
    calls = []

    def fake_geocode(address, **kwargs):
        calls.append(address)
        return SimpleNamespace(latitude=47.91, longitude=11.28, raw={})

    monkeypatch.setattr("app.geocoding._rate_limited_geocode", fake_geocode)

    geocode("Bahnhofstr.  1,   82327  Tutzing")
    geocode("bahnhofstr. 1, 82327 tutzing")
    assert len(calls) == 1


def test_geocode_no_result_is_cached_as_permanent_miss(session, monkeypatch):
    calls = []

    def fake_geocode(address, **kwargs):
        calls.append(address)
        return None

    monkeypatch.setattr("app.geocoding._rate_limited_geocode", fake_geocode)

    assert geocode("Nirgendwostr. 999, 00000 Nirgendwo") == (None, None, None)
    assert geocode("Nirgendwostr. 999, 00000 Nirgendwo") == (None, None, None)
    assert len(calls) == 1  # zweiter Aufruf trifft den (negativen) Cache


def test_geocode_transient_error_is_not_cached(session, monkeypatch):
    calls = []

    def failing_geocode(address, **kwargs):
        calls.append(address)
        raise GeocoderServiceError("timeout")

    monkeypatch.setattr("app.geocoding._rate_limited_geocode", failing_geocode)

    assert geocode("Teststr. 1, 82327 Tutzing") == (None, None, None)
    assert geocode("Teststr. 1, 82327 Tutzing") == (None, None, None)
    assert len(calls) == 2  # kein Cache-Eintrag bei transientem Fehler → jeder Aufruf versucht erneut
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DB_PATH=./data/immo.db .venv/bin/python -m pytest tests/test_geocoding.py -v`
Expected: FAIL (ModuleNotFoundError: `app.geocoding` existiert noch nicht)

- [ ] **Step 3: Write minimal implementation**

Create `app/geocoding.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `DB_PATH=./data/immo.db .venv/bin/python -m pytest tests/test_geocoding.py -v`
Expected: PASS (alle 5 neuen Tests)

- [ ] **Step 5: Regression + ruff**

Run: `DB_PATH=./data/immo.db .venv/bin/python -m pytest -q && ruff check app/geocoding.py tests/test_geocoding.py`
Expected: `64 passed` (59 + 5 neue), 0 ruff-Fehler.

- [ ] **Step 6: Commit**

```bash
git add app/geocoding.py tests/test_geocoding.py
git commit -m "feat(geocoding): Nominatim-Geocoding mit persistentem Adress-Hash-Cache

Transiente Fehler werden nicht gecacht (Retry am nächsten Lauf), ein
bestätigter Nicht-Treffer schon (spart wiederholte Anfragen)."
git push
```

---

### Task 3: `app/robots.py` — robots.txt-Check

**Files:**
- Create: `app/robots.py`
- Test: `tests/test_robots.py` (neu)

**Interfaces:**
- Consumes: `httpx.AsyncClient` (vom Aufrufer übergeben, z. B. `SourceAdapter.client`).
- Produces: `app.robots.is_allowed(client: httpx.AsyncClient, url: str) -> bool`, `app.robots.USER_AGENT: str`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_robots.py`:

```python
"""Tests für app.robots — robots.txt-Respekt vor dem Crawlen einer Makler-Site."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.robots import is_allowed


@pytest.mark.asyncio
async def test_is_allowed_no_robots_txt_means_allowed():
    """404 auf robots.txt = kein Verbot vorhanden = erlaubt."""
    client = AsyncMock()
    resp = MagicMock()
    resp.status_code = 404
    client.get = AsyncMock(return_value=resp)

    assert await is_allowed(client, "https://example.de/angebote/") is True


@pytest.mark.asyncio
async def test_is_allowed_disallow_all():
    client = AsyncMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.text = "User-agent: *\nDisallow: /"
    client.get = AsyncMock(return_value=resp)

    assert await is_allowed(client, "https://example.de/angebote/") is False


@pytest.mark.asyncio
async def test_is_allowed_disallow_specific_path_only():
    client = AsyncMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.text = "User-agent: *\nDisallow: /admin/"
    client.get = AsyncMock(return_value=resp)

    assert await is_allowed(client, "https://example.de/angebote/") is True


@pytest.mark.asyncio
async def test_is_allowed_fetches_robots_txt_from_host_root():
    client = AsyncMock()
    resp = MagicMock()
    resp.status_code = 404
    client.get = AsyncMock(return_value=resp)

    await is_allowed(client, "https://example.de/angebote/liste?seite=2")

    client.get.assert_awaited_once_with("https://example.de/robots.txt")


@pytest.mark.asyncio
async def test_is_allowed_network_error_fails_open():
    """Ein Netzwerkfehler beim robots.txt-Abruf darf den Crawl nicht
    blockieren — konservativ genug ist bereits, dass jede Detailseite später
    ihre eigene Fehlerbehandlung hat."""
    client = AsyncMock()
    client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))

    assert await is_allowed(client, "https://example.de/angebote/") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DB_PATH=./data/immo.db .venv/bin/python -m pytest tests/test_robots.py -v`
Expected: FAIL (ModuleNotFoundError: `app.robots`)

- [ ] **Step 3: Write minimal implementation**

Create `app/robots.py`:

```python
"""robots.txt-Respekt (Vollabdeckung-Spec §8: "robots.txt wird pro Lauf
gelesen und respektiert; Disallow -> kein Abruf.").
"""

from __future__ import annotations

from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import httpx

from app.logging_setup import log

USER_AGENT = "immo-radar/0.1 (privates Immobilien-Scouting; Kontakt via immo.herrlich.dev)"


async def is_allowed(client: httpx.AsyncClient, url: str) -> bool:
    """Prüft robots.txt des Hosts von `url`. Kein robots.txt = erlaubt.
    Netzwerkfehler beim Abruf von robots.txt selbst = erlaubt (fail open —
    ein einzelner Hiccup soll den Crawl nicht lahmlegen)."""
    robots_url = urljoin(url, "/robots.txt")
    try:
        r = await client.get(robots_url)
    except httpx.HTTPError as e:
        log.warning("robots.fetch_failed", url=robots_url, error=str(e))
        return True

    parser = RobotFileParser()
    if r.status_code == 200:
        parser.parse(r.text.splitlines())
    else:
        return True

    return parser.can_fetch(USER_AGENT, url)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `DB_PATH=./data/immo.db .venv/bin/python -m pytest tests/test_robots.py -v`
Expected: PASS (alle 5 neuen Tests)

- [ ] **Step 5: Regression + ruff**

Run: `DB_PATH=./data/immo.db .venv/bin/python -m pytest -q && ruff check app/robots.py tests/test_robots.py`
Expected: `69 passed` (64 + 5 neue), 0 ruff-Fehler.

- [ ] **Step 6: Commit**

```bash
git add app/robots.py tests/test_robots.py
git commit -m "feat(robots): robots.txt-Check für den Makler-Crawl

Kein robots.txt oder Netzwerkfehler beim Abruf = erlaubt (fail open);
ein Disallow-Treffer blockiert den Zugriff."
git push
```

---

### Task 4: Ehrlicher User-Agent statt Chrome-Fake + Live-Verifikation der Bestandsquellen

**Files:**
- Modify: `app/sources/base.py:29-34`
- Test: `tests/test_source_base.py` (neu)

**Interfaces:**
- Consumes: nichts Neues.
- Produces: `SourceAdapter.__aenter__()` setzt jetzt einen identifizierenden User-Agent statt eines Chrome-Fakes. Betrifft alle httpx-basierten Adapter (`bs_immo`, `riedel`, `starnberg_bader`, `tutzing24`, `immoscout24`, das neue `agents` aus Task 5) — **nicht** `kleinanzeigen` (nutzt Playwright über `app/sources/browser.py` mit eigenem, unverändertem UA).

- [ ] **Step 1: Write the failing test**

Create `tests/test_source_base.py`:

```python
"""Regressionstest: SourceAdapter setzt einen ehrlichen, identifizierenden
User-Agent statt eines Chrome-Fakes (Vollabdeckung-Spec §8)."""

from __future__ import annotations

import pytest

from app.sources.base import SourceAdapter


class _DummySource(SourceAdapter):
    name = "dummy"

    async def fetch(self):
        return
        yield  # pragma: no cover


@pytest.mark.asyncio
async def test_user_agent_is_honest_not_a_chrome_fake():
    async with _DummySource() as adapter:
        ua = adapter.client.headers["User-Agent"]
        assert "immo-radar" in ua
        assert "Chrome" not in ua
        assert "Macintosh" not in ua
        assert "herrlich.dev" in ua  # Kontakt-URL laut Spec §8 Pflicht
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DB_PATH=./data/immo.db .venv/bin/python -m pytest tests/test_source_base.py -v`
Expected: FAIL (`assert "immo-radar" in ua` schlägt fehl — aktueller UA ist der Chrome-Fake)

- [ ] **Step 3: Write minimal implementation**

In `app/sources/base.py`, ersetze den `headers`-Block in `__aenter__`:

```python
    async def __aenter__(self) -> "SourceAdapter":
        self.client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "immo-radar/0.1 (privates Immobilien-Scouting; "
                    "Kontakt via immo.herrlich.dev)"
                ),
                "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
            },
        )
        return self
```

- [ ] **Step 4: Run test to verify it passes**

Run: `DB_PATH=./data/immo.db .venv/bin/python -m pytest tests/test_source_base.py -v`
Expected: PASS

- [ ] **Step 5: Live-Verifikation der 4 betroffenen Bestandsquellen (manuell, kein pytest)**

Dieser Schritt prüft, ob der ehrliche UA eine der vier aktiven httpx-Quellen
bricht (Risiko: simples UA-Sniffing auf einer kleinen Makler-Website blockt
einen erkennbaren Bot, obwohl es Chrome erlaubt hätte). Live-Netzwerkaufrufe
gegen echte externe Sites — nicht Teil der automatisierten Suite.

Run:
```bash
for src in bs_immo riedel starnberg_bader tutzing24; do
  echo "== $src =="
  DB_PATH=./data/immo.db .venv/bin/python -m scripts.verify_source "$src" 2>&1 | tail -3
done
```

Expected: Jede Quelle liefert weiterhin `total: N` mit N > 0 (Vergleichswert:
laut `CLAUDE.md`-Quellen-Status-Tabelle sind alle vier aktuell "✅ aktiv").
Falls eine Quelle nach dem UA-Wechsel plötzlich `total: 0` liefert, wo sie
vorher Objekte lieferte: **nicht** stillschweigend auf den Chrome-Fake
zurückrudern (das widerspricht der expliziten Spec-Entscheidung §8) —
stattdessen dem Nutzer melden, welche Quelle betroffen ist. Das ist exakt
der Coverage-Transparenz-Fall, den Phase 4 (Dashboard) sichtbar machen wird;
für Phase 1 reicht die Meldung im Plan-Verlauf.

- [ ] **Step 6: Regression + ruff**

Run: `DB_PATH=./data/immo.db .venv/bin/python -m pytest -q && ruff check tests/test_source_base.py`
Expected: `70 passed` (69 + 1 neuer). `app/sources/base.py` hat schon vor diesem Task 1 Altlast-Fehler (`UP037`, siehe Global Constraints) — nicht Teil dieses Checks.

- [ ] **Step 7: Commit**

```bash
git add app/sources/base.py tests/test_source_base.py
git commit -m "fix(sources): ehrlicher User-Agent statt Chrome-Fake in SourceAdapter

Der Chrome-Fake widersprach der im Spec zugesagten Höflichkeit (§8).
Live-Verifikation gegen bs_immo/riedel/starnberg_bader/tutzing24 zeigt
keine Regression."
git push
```

---

### Task 5: `app/sources/agents_adapter.py` — generischer DB-getriebener Adapter, additiv zur REGISTRY

**Files:**
- Create: `app/sources/agents_adapter.py`
- Modify: `app/sources/registry.py`
- Test: `tests/test_agents_adapter.py` (neu)

**Interfaces:**
- Consumes: `app.db.Agent` (Task 1), `app.robots.is_allowed` (Task 3), `app.sources.base.SourceAdapter` (unverändert bis auf Task 4s UA), `app.models.RawListing`.
- Produces: `app.sources.agents_adapter.AgentSiteSource` (SourceAdapter-Subklasse, `name = "agents"`), `app.sources.agents_adapter.EXTRACTION_METHODS: dict[str, ExtractionMethod]` (in Phase 1 leer — Phase 2 registriert hier die Vendor-Adapter), `app.sources.agents_adapter.ExtractionMethod` (Type-Alias: `Callable[[Agent, httpx.AsyncClient], AsyncIterator[RawListing]]`). `app.sources.REGISTRY["agents"]` neu, alle bestehenden Keys unverändert.

- [ ] **Step 1: Write the failing test**

Create `tests/test_agents_adapter.py`:

```python
"""Tests für AgentSiteSource — generischer, DB-getriebener Adapter für die
agents-Tabelle. Additiv zur REGISTRY (Vollabdeckung-Spec §5.3)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db as db_module
from app.db import Agent, Base
from app.models import PropertyType, RawListing
from app.sources.agents_adapter import EXTRACTION_METHODS, AgentSiteSource


@pytest.fixture()
def session(monkeypatch, tmp_path):
    test_engine = create_engine(f"sqlite:///{tmp_path}/test.db", echo=False, future=True)
    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)
    return TestSession


@pytest.fixture(autouse=True)
def clean_extraction_methods():
    EXTRACTION_METHODS.clear()
    yield
    EXTRACTION_METHODS.clear()


def _make_agent(session, **overrides) -> int:
    defaults = dict(
        name="Test Makler",
        coverage_status="auto-harvested",
        listing_url="https://example.de/angebote/",
        extraction={"method": "fake"},
    )
    defaults.update(overrides)
    with session() as s:
        agent = Agent(**defaults)
        s.add(agent)
        s.commit()
        return agent.id


@pytest.mark.asyncio
async def test_fetch_yields_from_registered_method(session, monkeypatch):
    agent_id = _make_agent(session)

    async def fake_method(agent, client) -> AsyncIterator[RawListing]:
        yield RawListing(
            source="agents",
            source_id=f"agent-{agent.id}-1",
            url="https://example.de/angebote/1",
            title="Testobjekt",
            property_type=PropertyType.HAUS,
        )

    EXTRACTION_METHODS["fake"] = fake_method
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=True))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert len(results) == 1
    assert results[0].source_id == f"agent-{agent_id}-1"


@pytest.mark.asyncio
async def test_fetch_skips_agents_not_auto_harvested(session, monkeypatch):
    """Strukturelle Garantie der Transparenz-Anforderung: nur
    coverage_status == 'auto-harvested' wird überhaupt angefasst — 'unknown'
    zählt nie als abgedeckt."""
    _make_agent(session, coverage_status="unknown")

    async def fake_method(agent, client) -> AsyncIterator[RawListing]:
        yield RawListing(source="agents", source_id="x", url="https://x", title="x")

    EXTRACTION_METHODS["fake"] = fake_method
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=True))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert results == []


@pytest.mark.asyncio
async def test_fetch_skips_agent_without_method(session, monkeypatch):
    _make_agent(session, extraction={})
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=True))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert results == []


@pytest.mark.asyncio
async def test_fetch_skips_unregistered_method(session, monkeypatch):
    _make_agent(session, extraction={"method": "does-not-exist"})
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=True))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert results == []


@pytest.mark.asyncio
async def test_fetch_marks_robots_disallowed_and_persists_reason(session, monkeypatch):
    agent_id = _make_agent(session)

    async def fake_method(agent, client) -> AsyncIterator[RawListing]:
        yield RawListing(source="agents", source_id="x", url="https://x", title="x")

    EXTRACTION_METHODS["fake"] = fake_method
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=False))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert results == []
    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.coverage_status == "robots-disallowed"
        assert agent.coverage_reason is not None
        assert agent.last_checked is not None


@pytest.mark.asyncio
async def test_fetch_isolates_a_failing_agent_from_the_rest(session, monkeypatch):
    """Spec §7: 'Ein fehlschlagender Makler bricht nie den Gesamtlauf ab.'"""
    _make_agent(session, name="Broken Makler")
    ok_id = _make_agent(session, name="OK Makler", listing_url="https://ok.example.de/angebote/")

    call_count = {"n": 0}

    async def flaky_method(agent, client) -> AsyncIterator[RawListing]:
        call_count["n"] += 1
        if agent.name == "Broken Makler":
            raise RuntimeError("boom")
        yield RawListing(source="agents", source_id=f"agent-{agent.id}", url=agent.listing_url, title="OK")

    EXTRACTION_METHODS["fake"] = flaky_method
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=True))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert call_count["n"] == 2
    assert len(results) == 1
    assert results[0].source_id == f"agent-{ok_id}"


def test_registry_includes_agents_source_additively():
    from app.sources import REGISTRY, get_all_adapters
    from app.sources.agents_adapter import AgentSiteSource
    from app.sources.kleinanzeigen import KleinanzeigenSource

    assert REGISTRY["agents"] is AgentSiteSource
    assert REGISTRY["kleinanzeigen"] is KleinanzeigenSource  # unverändert

    adapters = get_all_adapters()
    assert any(isinstance(a, AgentSiteSource) for a in adapters)
    assert len(adapters) == len(REGISTRY)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DB_PATH=./data/immo.db .venv/bin/python -m pytest tests/test_agents_adapter.py -v`
Expected: FAIL (ModuleNotFoundError: `app.sources.agents_adapter`)

- [ ] **Step 3: Write minimal implementation**

Create `app/sources/agents_adapter.py`:

```python
"""Generischer, DB-getriebener Adapter für die agents-Tabelle.

Tritt NEBEN die statische REGISTRY, ersetzt sie nicht (Vollabdeckung-Spec
§5.3). Verteilt jede agents-Zeile mit coverage_status == "auto-harvested" an
die in EXTRACTION_METHODS registrierte Methode. EXTRACTION_METHODS ist in
Phase 1 bewusst leer — Phase 2 registriert hier die acht Vendor-Adapter und
die strukturelle Detail-Link-Erkennung. Eine leere Registry bedeutet, dass
fetch() nichts liefert, was bis Phase 2 korrekt ist.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import datetime

import httpx
from sqlalchemy import select

import app.db as db_module
from app.db import Agent
from app.logging_setup import log
from app.models import RawListing
from app.robots import is_allowed
from app.sources.base import SourceAdapter

ExtractionMethod = Callable[[Agent, httpx.AsyncClient], AsyncIterator[RawListing]]

EXTRACTION_METHODS: dict[str, ExtractionMethod] = {}


class AgentSiteSource(SourceAdapter):
    """Ein Adapter-Objekt repräsentiert alle Makler-eigenen Websites
    zusammen — jede agents-Zeile wird einzeln isoliert verarbeitet, ein
    fehlschlagender Makler bricht nie den Gesamtlauf ab (Spec §7)."""

    name = "agents"

    async def fetch(self) -> AsyncIterator[RawListing]:
        assert self.client is not None
        with db_module.SessionLocal() as session:
            agents = list(
                session.scalars(select(Agent).where(Agent.coverage_status == "auto-harvested"))
            )

        for agent in agents:
            method_name = (agent.extraction or {}).get("method")
            if not method_name:
                log.warning("agents_adapter.no_method", agent_id=agent.id, agent_name=agent.name)
                continue
            handler = EXTRACTION_METHODS.get(method_name)
            if handler is None:
                log.warning("agents_adapter.unknown_method", agent_id=agent.id, method=method_name)
                continue
            if not agent.listing_url:
                log.warning("agents_adapter.no_listing_url", agent_id=agent.id)
                continue

            if not await is_allowed(self.client, agent.listing_url):
                log.info("agents_adapter.robots_disallowed", agent_id=agent.id, url=agent.listing_url)
                with db_module.SessionLocal() as session:
                    db_agent = session.get(Agent, agent.id)
                    if db_agent is not None:
                        db_agent.coverage_status = "robots-disallowed"
                        db_agent.coverage_reason = f"robots.txt verbietet Zugriff auf {agent.listing_url}"
                        db_agent.last_checked = datetime.utcnow()
                        session.commit()
                continue

            try:
                async for raw in handler(agent, self.client):
                    yield raw
            except Exception as e:
                log.error(
                    "agents_adapter.agent_failed",
                    agent_id=agent.id,
                    agent_name=agent.name,
                    error=str(e),
                )
                continue
```

In `app/sources/registry.py`, füge den Import und den REGISTRY-Eintrag hinzu (nur Ergänzung, keine bestehende Zeile ändern):

```python
from __future__ import annotations

from app.sources.agents_adapter import AgentSiteSource
from app.sources.base import SourceAdapter
from app.sources.immoscout24_rss import ImmoScout24RSSSource
from app.sources.kleinanzeigen import KleinanzeigenSource
from app.sources.makler_bsimmo import BsImmoSource
from app.sources.makler_riedel import RiedelSource
from app.sources.makler_starnberg_immo import StarnbergImmoSource
from app.sources.tutzing24 import Tutzing24Source

REGISTRY: dict[str, type[SourceAdapter]] = {
    "immoscout24": ImmoScout24RSSSource,
    "kleinanzeigen": KleinanzeigenSource,
    "riedel": RiedelSource,
    "starnberg_bader": StarnbergImmoSource,
    "bs_immo": BsImmoSource,
    "tutzing24": Tutzing24Source,
    "agents": AgentSiteSource,
}


def get_all_adapters() -> list[SourceAdapter]:
    return [cls() for cls in REGISTRY.values()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `DB_PATH=./data/immo.db .venv/bin/python -m pytest tests/test_agents_adapter.py -v`
Expected: PASS (alle 7 neuen Tests)

- [ ] **Step 5: Regression + ruff**

Run: `DB_PATH=./data/immo.db .venv/bin/python -m pytest -q && ruff check app/sources/agents_adapter.py app/sources/registry.py tests/test_agents_adapter.py`
Expected: `77 passed` (70 + 7 neue), 0 ruff-Fehler. Zusätzlich manuell: `DB_PATH=./data/immo.db .venv/bin/python -m scripts.verify_source agents` sollte sauber `total: 0` melden (leere `agents`-Tabelle, kein Crash).

- [ ] **Step 6: Commit**

```bash
git add app/sources/agents_adapter.py app/sources/registry.py tests/test_agents_adapter.py
git commit -m "feat(sources): generischer AgentSiteSource-Adapter, additiv zur REGISTRY

Verteilt agents-Zeilen mit coverage_status=auto-harvested an
EXTRACTION_METHODS (Phase 2 füllt die Registry). robots.txt-Disallow
schreibt sich selbst als coverage_status zurück. Ein fehlschlagender
Makler isoliert sich, bricht den Lauf nicht ab."
git push
```

---

### Task 6: Geocoding in die Pipeline verdrahten — Objekt-Regionsfilter-Reparatur

**Files:**
- Modify: `app/models.py` (RawListing um zwei Felder erweitern)
- Modify: `app/pipeline.py` (`_matches_profile`, `_upsert`)
- Test: `tests/test_pipeline.py` (neu)

**Interfaces:**
- Consumes: `app.geocoding.geocode` (Task 2), `app.scoring.lage.in_search_area` (unverändert), `app.settings_service.get_setting` (unverändert).
- Produces: `RawListing.geocode_confidence: float | None`, `RawListing.region_match_reason: str | None`; `Listing.geocode_confidence`/`Listing.region_match_reason` werden bei jedem Insert/Update befüllt.

Dies repariert den in Spec §2 dokumentierten Bug: *"Kein Adapter setzt lat/lon
-> in_search_area() gibt immer True zurück"* — der Regionsfilter hat de facto
nie etwas ausgefiltert, weil `in_search_area()` bei fehlenden Koordinaten
absichtlich `True` liefert (siehe `app/scoring/lage.py:46-47`, unverändert).

- [ ] **Step 1: Write the failing test**

Create `tests/test_pipeline.py`:

```python
"""Tests für app.pipeline — insbesondere die Geocoding-Integration, die den
Regionsfilter repariert (Vollabdeckung-Spec §4.3)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db as db_module
from app.db import Base
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
    with patch("app.pipeline.geocode", return_value=(47.9095, 11.2783, 0.6)):
        assert _matches_profile(raw) is True
    assert raw.region_match_reason == "geocoded"
    assert raw.geocode_confidence == 0.6
    assert raw.lat == 47.9095


def test_matches_profile_rejects_geocoded_object_outside_area(session):
    """Regression für den historischen Bug: früher gab in_search_area() ohne
    lat/lon immer True zurück, egal wo das Objekt tatsächlich lag. Der
    Regex-Vorfilter matcht hier zwar ("Starnberg" im Titel erwähnt), die
    echten geocodierten Koordinaten (München) müssen den Regionsfilter
    trotzdem greifen lassen."""
    set_setting("search_locations", TUTZING_LOCATIONS)
    raw = _raw(
        address="Marienplatz 1, 80331 München",
        title="Wohnung München (erwähnt Starnberg im Text)",
    )
    with patch("app.pipeline.geocode", return_value=(48.1374, 11.5755, 0.7)):
        assert _matches_profile(raw) is False


def test_matches_profile_uses_source_coordinates_without_geocoding(session):
    set_setting("search_locations", TUTZING_LOCATIONS)
    raw = _raw(lat=47.91, lon=11.28)
    with patch("app.pipeline.geocode") as mock_geocode:
        assert _matches_profile(raw) is True
        mock_geocode.assert_not_called()
    assert raw.region_match_reason == "coordinates-from-source"


def test_matches_profile_falls_back_to_regex_on_geocode_failure(session):
    set_setting("search_locations", TUTZING_LOCATIONS)
    raw = _raw()
    with patch("app.pipeline.geocode", return_value=(None, None, None)):
        assert _matches_profile(raw) is True
    assert raw.region_match_reason == "geocode-failed-regex-fallback"


def test_matches_profile_rejects_without_geocoding_when_no_location_text(session):
    """Der Regex-Vorfilter spart die Geocoding-Anfrage, wenn gar kein
    Ortstext vorhanden ist — unverändertes Verhalten von _location_ok."""
    raw = _raw(address=None, city=None, plz=None, title="Haus")
    with patch("app.pipeline.geocode") as mock_geocode:
        assert _matches_profile(raw) is False
        mock_geocode.assert_not_called()


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

    raw.region_match_reason = "geocode-failed-regex-fallback"
    raw.geocode_confidence = None

    with session() as s:
        listing, is_new = _upsert(s, raw)
        s.commit()
        assert is_new is False
        assert listing.region_match_reason == "geocode-failed-regex-fallback"
        assert listing.geocode_confidence is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DB_PATH=./data/immo.db .venv/bin/python -m pytest tests/test_pipeline.py -v`
Expected: FAIL (`AttributeError`/`ValidationError` — `RawListing` hat noch keine `geocode_confidence`/`region_match_reason`-Felder, `_matches_profile` filtert noch nicht gegen echte Koordinaten)

- [ ] **Step 3: Write minimal implementation**

In `app/models.py`, füge in `RawListing` nach `lon` zwei neue Felder ein:

```python
    lat: Optional[float] = None
    lon: Optional[float] = None
    geocode_confidence: Optional[float] = None
    region_match_reason: Optional[str] = None
    hausgeld_eur: Optional[int] = None
```

In `app/pipeline.py`, ergänze den Import und eine neue Funktion `_resolve_location`, und verdrahte sie in `_matches_profile`:

```python
from app.config import settings
from app.db import FetchRun, Listing, ListingHistory, SessionLocal
from app.geocoding import geocode
from app.logging_setup import log
from app.models import RawListing
from app.scoring.lage import in_search_area
from app.settings_service import get_setting
from app.sources import get_all_adapters
```

```python
def _resolve_location(raw: RawListing) -> None:
    """Füllt raw.lat/lon per Geocoding, falls die Quelle sie nicht mitliefert,
    und dokumentiert in region_match_reason, worauf die spätere
    in_search_area()-Entscheidung beruht (Spec §4.3 Punkt 4)."""
    if raw.lat is not None and raw.lon is not None:
        raw.region_match_reason = "coordinates-from-source"
        return

    address = " ".join(filter(None, [raw.address, raw.plz, raw.city])).strip()
    if not address:
        raw.region_match_reason = "no-address-info"
        return

    lat, lon, importance = geocode(address)
    if lat is not None and lon is not None:
        raw.lat, raw.lon = lat, lon
        raw.geocode_confidence = importance
        raw.region_match_reason = "geocoded"
    else:
        raw.region_match_reason = "geocode-failed-regex-fallback"


def _matches_profile(raw: RawListing) -> bool:
    if _is_junk(raw):
        return False
    if not _location_ok(raw):
        return False
    _resolve_location(raw)
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
```

In `_upsert`, ergänze im Insert-Zweig (`Listing(...)`-Konstruktor, nach `lon=raw.lon,`):

```python
            lat=raw.lat,
            lon=raw.lon,
            geocode_confidence=raw.geocode_confidence,
            region_match_reason=raw.region_match_reason,
            hausgeld_eur=raw.hausgeld_eur,
```

und im Update-Zweig (nach `existing.is_active = True`):

```python
    existing.last_seen_at = now
    existing.is_active = True
    existing.lat = raw.lat
    existing.lon = raw.lon
    existing.geocode_confidence = raw.geocode_confidence
    existing.region_match_reason = raw.region_match_reason
    if raw.images and not existing.images:
        existing.images = raw.images
    return existing, False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `DB_PATH=./data/immo.db .venv/bin/python -m pytest tests/test_pipeline.py -v`
Expected: PASS (alle 6 neuen Tests, insbesondere `test_matches_profile_rejects_geocoded_object_outside_area` — der Beweis, dass der historische Bug behoben ist)

- [ ] **Step 5: Regression + ruff**

Run: `DB_PATH=./data/immo.db .venv/bin/python -m pytest -q && ruff check app/pipeline.py tests/test_pipeline.py`
Expected: `83 passed` (77 + 6 neue). `app/models.py` hat schon vor diesem Task Altlast-Fehler (siehe Global Constraints) — die zwei neuen Zeilen im gleichen `Optional[...]`-Stil erzeugen keine zusätzlichen.

- [ ] **Step 6: Commit**

```bash
git add app/models.py app/pipeline.py tests/test_pipeline.py
git commit -m "fix(pipeline): Geocoding repariert den Objekt-Regionsfilter

in_search_area() gab bislang mangels lat/lon immer True zurück (Spec §2).
Die Ortsnamen-Regex bleibt Vorfilter + Fallback bei Geocoding-Fehlschlag,
ist aber nicht mehr der Hauptfilter. geocode_confidence und
region_match_reason machen nachvollziehbar, warum ein Objekt drin oder
draußen ist (Spec §4.3)."
git push
```

---

### Task 7: Doku-Update, volle Regression, Abschluss

**Files:**
- Modify: `CLAUDE.md` (Struktur-Sektion)
- Modify: `docs/STATUS.md` (nächster Schritt)
- Modify: `docs/superpowers/specs/2026-08-04-makler-vollabdeckung-design.md` (Phase 1 als abgeschlossen markieren)

**Interfaces:**
- Consumes: nichts Neues — reine Doku- und Verifikationsarbeit.
- Produces: aktualisierte Doku, die den tatsächlichen Stand nach Phase 1 abbildet.

- [ ] **Step 1: `CLAUDE.md` — neue Dateien in die Struktur-Tour aufnehmen**

In der `## Struktur`-Sektion, im `app/`-Block, ergänze nach der Zeile mit `scoring/`:

```
  geocoding.py    Nominatim-Geocoding mit persistentem Adress-Hash-Cache
  robots.py       robots.txt-Respekt für den Makler-Crawl
```

und im `sources/`-Block, nach der Zeile mit `immoscout24_rss.py`:

```
                  agents_adapter.py  ← generischer, DB-getriebener Adapter für die agents-Tabelle (additiv zur REGISTRY)
```

- [ ] **Step 2: `docs/STATUS.md` — nächster Schritt aktualisieren**

Ersetze den Inhalt der `## Offener Backlog`-Sektion:

```markdown
## Offener Backlog

Offene Items → **Linear** (HER-577/578). Feature-Backlog: `docs/backlog.md`
(Stand 2026-05-11, ~17 Posten, noch nicht vollständig nach Linear triagiert).

**Makler-Vollabdeckung** (`docs/superpowers/specs/2026-08-04-makler-vollabdeckung-design.md`):
Phase 0 (Vermessung) und Phase 1 (Fundament: `agents`-Tabelle, generischer
Adapter, Geocoding, ehrlicher User-Agent) sind abgeschlossen. Nächster
Schritt: Implementierungsplan für Phase 2 (Kaskade — acht Vendor-Adapter +
strukturelle Detail-Link-Erkennung, Change-Gate, Selbsttest).
```

- [ ] **Step 3: Design-Spec — Phase 1 als abgeschlossen markieren**

In `docs/superpowers/specs/2026-08-04-makler-vollabdeckung-design.md`, Abschnitt „## 10. Umsetzungsphasen", ersetze die Überschrift der Phase 1:

```bash
TODAY=$(date +%F)
```

Ersetze `### Phase 1 — Fundament` durch `### Phase 1 — Fundament ✅ abgeschlossen ($TODAY)` (den tatsächlichen Wert von `$TODAY` einsetzen, nicht das Literal `$TODAY`).

- [ ] **Step 4: Volle Regression**

Run: `DB_PATH=./data/immo.db .venv/bin/python -m pytest -q`
Expected: `83 passed` (alle 55 ursprünglichen + 28 neuen aus Task 1-6).

Run: `ruff check app/db.py app/geocoding.py app/robots.py app/sources/base.py app/sources/agents_adapter.py app/sources/registry.py app/pipeline.py app/models.py tests/`
Expected: 0 Fehler außer den in Global Constraints dokumentierten 20 Altlast-Fehlern in `app/models.py` (19) und `app/sources/base.py` (1) — beide unverändert gegenüber dem Stand vor diesem Plan.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md docs/STATUS.md docs/superpowers/specs/2026-08-04-makler-vollabdeckung-design.md
git commit -m "docs: Phase 1 (Fundament) der Makler-Vollabdeckung abgeschlossen

agents-Tabelle, generischer Adapter, Geocoding-Regionsfilter, ehrlicher
User-Agent. Nächster Schritt: Phase 2 (Kaskade)."
git push
```

---

## Self-Review (durchgeführt beim Schreiben dieses Plans)

- **Spec-Abdeckung:** §4.3 (Geocoding + Vorfilter/Fallback) → Task 6. §5.1 (agents-Tabelle inkl. `unknown`-Default) → Task 1. §5.3 (additiv zur Registry) → Task 5. §8 (ehrlicher User-Agent, robots.txt) → Task 3+4+5. Phase 1s explizite Ein-Satz-Beschreibung in §10 ("agents-Tabelle, generischer DB-getriebener Adapter, Geocoding beim Ingest, höflicher User-Agent + robots.txt") ist vollständig auf Tasks 1-6 abgebildet. §5.2 (Abdeckungsquote-Anzeige), §6 (Discovery-Pipeline), §7 (Bruch-Erkennung/Selbsttest/field_completeness), §9 (Rezept-Lernkosten) sind bewusst Phase 2-4 und nicht Teil dieses Plans.
- **Platzhalter-Scan:** Kein TBD/TODO; jeder Code-Schritt enthält vollständigen, lauffähigen Code statt Beschreibungen.
- **Scope-Check:** Sieben Tasks, jede unabhängig testbar, keine Task hängt von einer noch nicht geschriebenen Phase-2-Komponente ab (EXTRACTION_METHODS bleibt in Task 5 bewusst leer und wird per Fake-Handler getestet).
- **Typ-Konsistenz geprüft:** `geocode()`-Signatur `tuple[float | None, float | None, float | None]` identisch in Task 2 (Definition) und Task 6 (Aufruf in `_resolve_location`). `ExtractionMethod`-Signatur `Callable[[Agent, httpx.AsyncClient], AsyncIterator[RawListing]]` identisch in Task 5s Typalias und den Fake-Handlern in Task 5s Tests. `COVERAGE_STATUSES`-Werte identisch zwischen Spec §5.1, Task 1s Konstante und Task 5s `"robots-disallowed"`-Literal.
