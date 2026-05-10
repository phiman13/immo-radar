# Backend API & Bugfixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drei kritische Bugs fixen und eine vollständige JSON-API bauen, die das React-Frontend (Plan 2) konsumieren kann — kein `.env`-Editing mehr nötig für Einstellungen.

**Architecture:** FastAPI-Backend bekommt neue Endpoints unter `/api/v1/`. Einstellungen wandern aus `.env` in eine SQLite-Tabelle `app_settings`; der Scheduler liest sie live ohne Restart. Bugfixes laufen unabhängig vom API-Bau.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy (mapped_column-Stil), SQLite, pytest, httpx (für Tests)

---

## Datei-Übersicht

| Datei | Aktion | Verantwortung |
|---|---|---|
| `app/db.py` | Modify | Neue Modelle: AppSetting, Source, ListingDuplicate; enrich_attempts in Listing |
| `app/enrich.py` | Modify | Retry-Limit via enrich_attempts; Logging des API-Fehlergrunds |
| `app/notify/telegram.py` | Modify | Score-Threshold aus DB lesen |
| `app/settings_service.py` | Create | Lesen/Schreiben von Settings aus DB (Key-Value) |
| `app/web/server.py` | Modify | API-Router mounten, CORS, Static-File-Serving für Frontend-Build |
| `app/web/api/__init__.py` | Create | API-Router aggregieren |
| `app/web/api/listings.py` | Create | GET/PATCH Listings-Endpoints |
| `app/web/api/settings.py` | Create | GET/PATCH Settings-Endpoints |
| `app/web/api/sources.py` | Create | GET/PATCH Sources-Endpoints |
| `app/web/api/system.py` | Create | Stats, FetchRuns, Crawl-Trigger |
| `app/web/api/telegram.py` | Create | Test-Nachricht senden |
| `scripts/deploy.sh` | Modify | docker-compose → docker compose (V2) |
| `tests/test_api_listings.py` | Create | Listings-API-Tests |
| `tests/test_settings_service.py` | Create | Settings-Service-Tests |
| `tests/conftest.py` | Create | Pytest-Fixtures (In-Memory-DB, Test-Client) |

---

## Task 1: deploy.sh reparieren (docker-compose → docker compose)

**Files:**
- Modify: `scripts/deploy.sh`

- [ ] **Schritt 1: Zeile ändern**

In `scripts/deploy.sh` Zeile mit `docker-compose up` ersetzen:

```bash
# Vorher:
ssh "$TARGET" "cd $APP_DIR && docker-compose up -d --build"

# Nachher:
ssh "$TARGET" "cd $APP_DIR && docker compose up -d --build"
```

Und die `docker-compose ps` Zeile:
```bash
# Vorher:
ssh "$TARGET" "cd $APP_DIR && docker-compose ps"

# Nachher:
ssh "$TARGET" "cd $APP_DIR && docker compose ps"
```

- [ ] **Schritt 2: Lokal testen**

```bash
bash scripts/deploy.sh
```

Erwartete Ausgabe: `✓ Deployed.` ohne Fehler.

- [ ] **Schritt 3: Committen**

```bash
git add scripts/deploy.sh
git commit -m "fix(deploy): docker-compose V1 auf docker compose V2 umstellen"
```

---

## Task 2: enrich_pending Endlosschleife fixen

**Files:**
- Modify: `app/db.py` (Listing-Modell, enrich_attempts Spalte)
- Modify: `app/enrich.py` (Retry-Limit, Attempt-Zähler)
- Create: `tests/conftest.py`
- Create: `tests/test_enrich.py`

- [ ] **Schritt 1: Testdatei + Fixture anlegen**

`tests/conftest.py`:
```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base, Listing, init_db


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with Session() as session:
        yield session


@pytest.fixture
def sample_listing(db_session):
    listing = Listing(
        dedup_hash="abc123",
        source="test",
        source_id="1",
        url="https://example.com/1",
        title="Testhaus",
        property_type="haus",
        status="new",
    )
    db_session.add(listing)
    db_session.commit()
    db_session.refresh(listing)
    return listing
```

- [ ] **Schritt 2: Failing Test schreiben**

`tests/test_enrich.py`:
```python
import pytest
from app.db import Listing


def test_listing_has_enrich_attempts_field(sample_listing):
    assert hasattr(sample_listing, "enrich_attempts")
    assert sample_listing.enrich_attempts == 0


def test_enrich_attempts_default_is_zero(db_session):
    listing = Listing(
        dedup_hash="xyz999",
        source="test",
        source_id="2",
        url="https://example.com/2",
        property_type="wohnung",
        status="new",
    )
    db_session.add(listing)
    db_session.commit()
    db_session.refresh(listing)
    assert listing.enrich_attempts == 0
```

- [ ] **Schritt 3: Test laufen lassen (erwartet: FAIL)**

```bash
python -m pytest tests/test_enrich.py -v
```

Erwartet: `AttributeError: 'Listing' object has no attribute 'enrich_attempts'`

- [ ] **Schritt 4: Spalte in db.py hinzufügen**

In `app/db.py`, in der `Listing`-Klasse nach `is_active` hinzufügen:

```python
enrich_attempts: Mapped[int] = mapped_column(Integer, default=0)
```

- [ ] **Schritt 5: Test laufen lassen (erwartet: PASS)**

```bash
python -m pytest tests/test_enrich.py -v
```

Erwartet: 2 passed

- [ ] **Schritt 6: enrich.py anpassen — Attempts hochzählen**

In `app/enrich.py`, in `enrich_listing()`, direkt nach dem `if listing is None: return`:

```python
async def enrich_listing(listing_id: int) -> None:
    with SessionLocal() as session:
        listing = session.get(Listing, listing_id)
        if listing is None:
            return

        listing.enrich_attempts = (listing.enrich_attempts or 0) + 1  # neu

        text = " ".join(filter(None, [listing.title, listing.description]))
        # ... Rest bleibt gleich
```

- [ ] **Schritt 7: enrich_pending mit Retry-Limit**

In `app/enrich.py`, `enrich_pending()` anpassen:

```python
async def enrich_pending(limit: int = 20) -> int:
    """Enrich listings ohne AI-Score, max. 3 Versuche pro Listing."""
    count = 0
    with SessionLocal() as session:
        ids = session.scalars(
            select(Listing.id)
            .where(Listing.ai_score.is_(None))
            .where(Listing.enrich_attempts < 3)
            .limit(limit)
        ).all()

    for lid in ids:
        try:
            await enrich_listing(lid)
            count += 1
        except Exception as e:
            log.error("enrich.failed", id=lid, error=str(e))
    return count
```

- [ ] **Schritt 8: Tests laufen lassen**

```bash
python -m pytest tests/test_enrich.py -v
```

Erwartet: alle passed

- [ ] **Schritt 9: Committen**

```bash
git add app/db.py app/enrich.py tests/conftest.py tests/test_enrich.py
git commit -m "fix(enrich): Endlosschleife durch enrich_attempts-Limit (max 3 Versuche)"
```

---

## Task 3: AI-Scoring-Fehler debuggen und fixen

**Files:**
- Modify: `app/scoring/ai_match.py` (Logging verbessern)
- Modify: `app/enrich.py` (Warning-Log sichtbar machen)

- [ ] **Schritt 1: Besseres Logging in ai_match.py**

In `app/scoring/ai_match.py`, den except-Block erweitern:

```python
    except Exception as e:
        log.warning(
            "ai_match.failed",
            error=str(e),
            error_type=type(e).__name__,
            id=listing.id,
            model=settings.ai_model,
            has_key=bool(settings.anthropic_api_key),
        )
        return None
```

- [ ] **Schritt 2: Auf VPS deployen und Logs prüfen**

```bash
bash scripts/deploy.sh
ssh root@89.167.67.26 "docker logs immo-radar-worker --tail=50 2>&1 | grep -E 'ai_match|warning' | sed 's/\x1b\[[0-9;]*m//g'"
```

Erwartet: Zeile mit `ai_match.failed` + `error_type` und `model`. Häufige Ursachen:
- `AuthenticationError` → API-Key falsch/abgelaufen
- `NotFoundError` → Model-Name falsch (prüfe `AI_MODEL` in VPS `.env`)
- `RateLimitError` → Quota erschöpft

- [ ] **Schritt 3: Ursache beheben**

Falls Model-Name falsch: In VPS `.env` setzen:
```bash
ssh root@89.167.67.26 "grep AI_MODEL /opt/immo-radar/.env"
# Korrekte Werte: claude-haiku-4-5-20251001
```

Falls nötig, `.env` auf VPS direkt editieren:
```bash
ssh root@89.167.67.26 "sed -i 's/AI_MODEL=.*/AI_MODEL=claude-haiku-4-5-20251001/' /opt/immo-radar/.env && docker compose -f /opt/immo-radar/docker-compose.yml restart worker"
```

- [ ] **Schritt 4: enrich_attempts für bestehende Listings zurücksetzen**

Da die 3 existierenden Listings jetzt max. 3 Versuche hatten, nach dem Fix zurücksetzen:
```bash
ssh root@89.167.67.26 "sqlite3 /opt/immo-radar/data/immo.db 'UPDATE listings SET enrich_attempts = 0 WHERE ai_score IS NULL;'"
```

Falls sqlite3 nicht installiert: via Python:
```bash
ssh root@89.167.67.26 "cd /opt/immo-radar && docker compose exec worker python -c \"
from app.db import Listing, SessionLocal
with SessionLocal() as s:
    s.query(Listing).filter(Listing.ai_score.is_(None)).update({'enrich_attempts': 0})
    s.commit()
    print('Reset done')
\""
```

- [ ] **Schritt 5: Committen**

```bash
git add app/scoring/ai_match.py
git commit -m "fix(ai_match): besseres Error-Logging inkl. model und error_type"
```

---

## Task 4: Neue DB-Modelle (AppSetting, Source)

**Files:**
- Modify: `app/db.py`
- Modify: `tests/conftest.py`
- Create: `tests/test_db_models.py`

- [ ] **Schritt 1: Failing Tests schreiben**

`tests/test_db_models.py`:
```python
from app.db import AppSetting, Source, SessionLocal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base
import pytest


@pytest.fixture
def mem_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with Session() as s:
        yield s


def test_app_setting_roundtrip(mem_session):
    setting = AppSetting(key="price_max", value="1500000")
    mem_session.add(setting)
    mem_session.commit()
    fetched = mem_session.get(AppSetting, "price_max")
    assert fetched.value == "1500000"


def test_source_defaults(mem_session):
    source = Source(name="Test Makler", url="https://makler.de", adapter_type="builtin")
    mem_session.add(source)
    mem_session.commit()
    assert source.is_active is True
    assert source.adapter_type == "builtin"
```

- [ ] **Schritt 2: Tests laufen (erwartet: FAIL — ImportError)**

```bash
python -m pytest tests/test_db_models.py -v
```

- [ ] **Schritt 3: Modelle in db.py hinzufügen**

Am Ende von `app/db.py`, vor `_ensure_db_dir()`:

```python
class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    url: Mapped[str] = mapped_column(String(512))
    adapter_code: Mapped[str | None] = mapped_column(Text, default=None)
    adapter_type: Mapped[str] = mapped_column(String(32), default="builtin")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_crawl_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

- [ ] **Schritt 4: Tests laufen (erwartet: PASS)**

```bash
python -m pytest tests/test_db_models.py -v
```

- [ ] **Schritt 5: Committen**

```bash
git add app/db.py tests/test_db_models.py
git commit -m "feat(db): AppSetting und Source Modelle hinzufügen"
```

---

## Task 5: Settings Service

**Files:**
- Create: `app/settings_service.py`
- Create: `tests/test_settings_service.py`

- [ ] **Schritt 1: Failing Tests schreiben**

`tests/test_settings_service.py`:
```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch
from app.db import Base, AppSetting


@pytest.fixture(autouse=True)
def mem_db(monkeypatch):
    """Patcht SessionLocal auf In-Memory-DB."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr("app.settings_service.SessionLocal", Session)
    return Session


def test_get_setting_returns_default_when_not_in_db():
    from app.settings_service import get_setting
    # "price_max" ist in _DEFAULTS definiert
    result = get_setting("price_max")
    assert isinstance(result, int)
    assert result > 0


def test_set_and_get_setting():
    from app.settings_service import get_setting, set_setting
    set_setting("price_max", 999000)
    assert get_setting("price_max") == 999000


def test_set_setting_overrides_default():
    from app.settings_service import get_setting, set_setting
    default = get_setting("poll_interval_minutes")
    set_setting("poll_interval_minutes", 42)
    assert get_setting("poll_interval_minutes") == 42


def test_get_all_settings_returns_dict():
    from app.settings_service import get_all_settings
    result = get_all_settings()
    assert isinstance(result, dict)
    assert "price_max" in result
    assert "poll_interval_minutes" in result
    assert "telegram_score_threshold" in result
```

- [ ] **Schritt 2: Tests laufen (erwartet: ImportError)**

```bash
python -m pytest tests/test_settings_service.py -v
```

- [ ] **Schritt 3: settings_service.py implementieren**

`app/settings_service.py`:
```python
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.config import settings as env
from app.db import AppSetting, SessionLocal

# Alle konfigurierbaren Settings mit .env-Defaults
_DEFAULTS: dict[str, Any] = {
    # Suchprofil
    "price_min": env.price_min,
    "price_max": env.price_max,
    "qm_min": env.qm_min,
    "qm_max": env.qm_max,
    "rooms_min": env.rooms_min,
    "property_types": env.property_types,
    "year_built_min": env.year_built_min,
    # Ort
    "search_center_lat": env.search_center_lat,
    "search_center_lon": env.search_center_lon,
    "search_radius_km": env.search_radius_km,
    "location_allowlist_extra": [],  # zusätzliche Orte/PLZ (Liste von Strings)
    # Telegram
    "telegram_bot_token": env.telegram_bot_token,
    "telegram_chat_id": env.telegram_chat_id,
    "telegram_score_threshold": 0,   # 0 = alle Listings notifizieren
    # Mechanik
    "poll_interval_minutes": env.poll_interval_minutes,
    "detail_fetch_interval_minutes": env.detail_fetch_interval_minutes,
    "junk_keywords_extra": [],        # zusätzliche Junk-Keywords (Liste von Strings)
}


def get_setting(key: str) -> Any:
    with SessionLocal() as session:
        row = session.get(AppSetting, key)
    if row is None:
        return _DEFAULTS.get(key)
    return json.loads(row.value)


def set_setting(key: str, value: Any) -> None:
    with SessionLocal() as session:
        existing = session.get(AppSetting, key)
        if existing:
            existing.value = json.dumps(value)
            existing.updated_at = datetime.utcnow()
        else:
            session.add(AppSetting(key=key, value=json.dumps(value)))
        session.commit()


def get_all_settings() -> dict[str, Any]:
    with SessionLocal() as session:
        rows = session.scalars(select(AppSetting)).all()
        db_values = {row.key: json.loads(row.value) for row in rows}
    return {**_DEFAULTS, **db_values}


def patch_settings(updates: dict[str, Any]) -> None:
    for key, value in updates.items():
        if key in _DEFAULTS:
            set_setting(key, value)
```

- [ ] **Schritt 4: Tests laufen (erwartet: PASS)**

```bash
python -m pytest tests/test_settings_service.py -v
```

- [ ] **Schritt 5: Committen**

```bash
git add app/settings_service.py tests/test_settings_service.py
git commit -m "feat(settings): Settings Service — DB-basierte Konfiguration mit .env-Defaults"
```

---

## Task 6: Score-Threshold in Telegram-Notifications

**Files:**
- Modify: `app/notify/telegram.py`

- [ ] **Schritt 1: Test schreiben**

In `tests/test_enrich.py` ergänzen:

```python
import asyncio
from unittest.mock import AsyncMock, patch


def test_notify_skips_below_threshold(sample_listing, monkeypatch):
    """Listing mit Score 40 wird nicht notifiziert wenn Threshold 70."""
    sample_listing.ai_score = 40
    monkeypatch.setattr("app.settings_service.get_setting", lambda key: 70 if key == "telegram_score_threshold" else None)
    
    sent = []

    async def fake_send(text, **kwargs):
        sent.append(text)
        return True

    with patch("app.notify.telegram.send_telegram", fake_send):
        asyncio.get_event_loop().run_until_complete(
            __import__("app.notify.telegram", fromlist=["notify_new_listing"]).notify_new_listing(sample_listing)
        )

    assert len(sent) == 0, "Listing unterhalb Threshold wurde trotzdem notifiziert"


def test_notify_sends_above_threshold(sample_listing, monkeypatch):
    """Listing mit Score 80 wird notifiziert wenn Threshold 70."""
    sample_listing.ai_score = 80
    monkeypatch.setattr("app.settings_service.get_setting", lambda key: 70 if key == "telegram_score_threshold" else "")

    sent = []

    async def fake_send(text, **kwargs):
        sent.append(text)
        return True

    with patch("app.notify.telegram.send_telegram", fake_send):
        asyncio.get_event_loop().run_until_complete(
            __import__("app.notify.telegram", fromlist=["notify_new_listing"]).notify_new_listing(sample_listing)
        )

    assert len(sent) == 1
```

- [ ] **Schritt 2: Tests laufen (erwartet: FAIL)**

```bash
python -m pytest tests/test_enrich.py::test_notify_skips_below_threshold -v
```

- [ ] **Schritt 3: notify_new_listing in telegram.py anpassen**

In `app/notify/telegram.py`, die `notify_new_listing`-Funktion anpassen:

```python
async def notify_new_listing(listing: Listing) -> None:
    from app.settings_service import get_setting

    threshold: int = get_setting("telegram_score_threshold") or 0
    if threshold > 0 and (listing.ai_score is None or listing.ai_score < threshold):
        log.debug(
            "telegram.skip_below_threshold",
            id=listing.id,
            score=listing.ai_score,
            threshold=threshold,
        )
        return

    text = _format_listing(listing)
    image = listing.images[0] if listing.images else None
    buttons = [{"text": "Exposé", "url": listing.url}]

    ok = await send_telegram(text, image_url=image, buttons=buttons)
    if ok:
        with SessionLocal() as session:
            session.query(Listing).filter(Listing.id == listing.id).update(
                {"notified_at": datetime.utcnow()}
            )
            session.commit()
```

- [ ] **Schritt 4: Tests laufen (erwartet: PASS)**

```bash
python -m pytest tests/test_enrich.py -v
```

- [ ] **Schritt 5: Committen**

```bash
git add app/notify/telegram.py tests/test_enrich.py
git commit -m "feat(telegram): Score-Threshold — Notifications nur ab konfiguriertem Mindestscore"
```

---

## Task 7: Pytest + FastAPI Test-Client Setup

**Files:**
- Modify: `tests/conftest.py`
- Modify: `pyproject.toml` (pytest + httpx als dev-dependencies)

- [ ] **Schritt 1: httpx in pyproject.toml ergänzen**

In `pyproject.toml`, im `[project.optional-dependencies]` dev-Block:
```toml
[project.optional-dependencies]
dev = [
    "ruff",
    "pytest",
    "pytest-asyncio",
    "httpx",       # für FastAPI TestClient
]
```

- [ ] **Schritt 2: Installieren**

```bash
pip install -e ".[dev]"
```

- [ ] **Schritt 3: FastAPI TestClient Fixture in conftest.py hinzufügen**

In `tests/conftest.py` ergänzen:

```python
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base


@pytest.fixture(scope="session")
def test_engine():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def api_client(test_engine, monkeypatch):
    """FastAPI TestClient mit In-Memory-DB und übergangenem Auth."""
    TestSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr("app.db.SessionLocal", TestSession)
    monkeypatch.setattr("app.settings_service.SessionLocal", TestSession)

    # Auth überspringen
    from app.web import server as srv
    from app.web.auth import require_auth
    srv.app.dependency_overrides[require_auth] = lambda: "test_user"

    from app.web.server import app
    with TestClient(app) as client:
        yield client

    srv.app.dependency_overrides.clear()
```

- [ ] **Schritt 4: Basis-Test schreiben und laufen lassen**

```bash
python -m pytest tests/ -v --tb=short
```

Erwartet: alle bisherigen Tests grün, kein Import-Fehler.

- [ ] **Schritt 5: Committen**

```bash
git add tests/conftest.py pyproject.toml
git commit -m "test: FastAPI TestClient Fixture + httpx dependency"
```

---

## Task 8: API-Router Grundstruktur

**Files:**
- Create: `app/web/api/__init__.py`
- Modify: `app/web/server.py`

- [ ] **Schritt 1: API-Package anlegen**

`app/web/api/__init__.py`:
```python
from fastapi import APIRouter

from app.web.api import listings, settings, sources, system, telegram

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(listings.router)
api_router.include_router(settings.router)
api_router.include_router(sources.router)
api_router.include_router(system.router)
api_router.include_router(telegram.router)
```

Leere Stub-Dateien damit der Import nicht kracht (werden in späteren Tasks gefüllt):

```bash
touch app/web/api/listings.py app/web/api/settings.py app/web/api/sources.py app/web/api/system.py app/web/api/telegram.py
```

Jeden Stub mit Minimalinhalt:
```python
# app/web/api/listings.py  (und analog die anderen)
from fastapi import APIRouter
router = APIRouter()
```

- [ ] **Schritt 2: Router in server.py mounten + CORS + Static-Files**

In `app/web/server.py` ergänzen (nach den bestehenden Imports):

```python
from fastapi.middleware.cors import CORSMiddleware
from app.web.api import api_router

# Nach app = FastAPI(...):
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(api_router)

# Statische Dateien für Frontend-Build (wird in Plan 2 gebaut)
_DIST = BASE_DIR / "static" / "dist"
if _DIST.exists():
    from fastapi.staticfiles import StaticFiles as _SF
    app.mount("/assets", _SF(directory=str(_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        from fastapi.responses import FileResponse
        index = _DIST / "index.html"
        if index.exists():
            return FileResponse(str(index))
        raise HTTPException(404)
```

- [ ] **Schritt 3: Testen**

```bash
python -m scripts.run_web &
curl http://localhost:8000/api/v1/  # erwartet: 404 (kein root endpoint)
kill %1
```

- [ ] **Schritt 4: Committen**

```bash
git add app/web/api/ app/web/server.py
git commit -m "feat(api): API-Router Grundstruktur + CORS + SPA-Fallback"
```

---

## Task 9: Listings API

**Files:**
- Modify: `app/web/api/listings.py`
- Create: `tests/test_api_listings.py`

- [ ] **Schritt 1: Failing Tests schreiben**

`tests/test_api_listings.py`:
```python
import pytest
from app.db import Listing, SessionLocal


@pytest.fixture
def listing_in_db(test_engine):
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    with Session() as s:
        listing = Listing(
            dedup_hash="test001",
            source="immoscout24",
            source_id="101",
            url="https://example.com/101",
            title="Schönes Haus Tutzing",
            price_eur=850000,
            qm=140.0,
            rooms=4.0,
            property_type="haus",
            status="new",
            is_active=True,
        )
        s.add(listing)
        s.commit()
        s.refresh(listing)
        return listing


def test_list_listings_returns_list(api_client, listing_in_db):
    response = api_client.get("/api/v1/listings")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_listing_has_price_per_sqm(api_client, listing_in_db):
    response = api_client.get("/api/v1/listings")
    assert response.status_code == 200
    listing = next(l for l in response.json() if l["id"] == listing_in_db.id)
    assert listing["price_per_sqm"] == round(850000 / 140.0)


def test_filter_by_status(api_client, listing_in_db):
    response = api_client.get("/api/v1/listings?status=new")
    assert response.status_code == 200
    assert all(l["status"] == "new" for l in response.json())


def test_filter_by_min_price(api_client, listing_in_db):
    response = api_client.get("/api/v1/listings?min_price=900000")
    assert response.status_code == 200
    assert all(l for l in response.json() if l.get("price_eur") is None or l["price_eur"] >= 900000)


def test_get_listing_detail(api_client, listing_in_db):
    response = api_client.get(f"/api/v1/listings/{listing_in_db.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == listing_in_db.id
    assert data["title"] == "Schönes Haus Tutzing"


def test_patch_listing_status(api_client, listing_in_db):
    response = api_client.patch(
        f"/api/v1/listings/{listing_in_db.id}",
        json={"status": "interesting"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "interesting"


def test_patch_listing_notes(api_client, listing_in_db):
    response = api_client.patch(
        f"/api/v1/listings/{listing_in_db.id}",
        json={"notes": "Guter Standort, Preis verhandelbar"},
    )
    assert response.status_code == 200
    assert response.json()["notes"] == "Guter Standort, Preis verhandelbar"
```

- [ ] **Schritt 2: Tests laufen (erwartet: FAIL — 404)**

```bash
python -m pytest tests/test_api_listings.py -v
```

- [ ] **Schritt 3: Listings API implementieren**

`app/web/api/listings.py`:
```python
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import asc, desc, select

from app.db import Listing, SessionLocal
from app.web.auth import require_auth

router = APIRouter(prefix="/listings", tags=["listings"])


def _serialize(listing: Listing) -> dict[str, Any]:
    price_per_sqm = None
    if listing.price_eur and listing.qm:
        price_per_sqm = round(listing.price_eur / listing.qm)
    return {
        "id": listing.id,
        "source": listing.source,
        "url": listing.url,
        "title": listing.title,
        "price_eur": listing.price_eur,
        "price_per_sqm": price_per_sqm,
        "qm": listing.qm,
        "rooms": listing.rooms,
        "year_built": listing.year_built,
        "property_type": listing.property_type,
        "address": listing.address,
        "city": listing.city,
        "ortsteil": listing.ortsteil,
        "lat": listing.lat,
        "lon": listing.lon,
        "hausgeld_eur": listing.hausgeld_eur,
        "energie_class": listing.energie_class,
        "energie_kwh": listing.energie_kwh,
        "images": listing.images or [],
        "status": listing.status,
        "notes": listing.notes,
        "ai_score": listing.ai_score,
        "ai_reasoning": listing.ai_reasoning,
        "risk_flags": listing.risk_flags or [],
        "lage_score": listing.lage_score,
        "first_seen_at": listing.first_seen_at.isoformat() if listing.first_seen_at else None,
        "last_seen_at": listing.last_seen_at.isoformat() if listing.last_seen_at else None,
        "notified_at": listing.notified_at.isoformat() if listing.notified_at else None,
        "is_active": listing.is_active,
    }


class ListingPatch(BaseModel):
    status: str | None = None
    notes: str | None = None


_VALID_STATUSES = {"new", "interesting", "maybe", "seen", "rejected"}
_SORT_COLS = {
    "first_seen_at": Listing.first_seen_at,
    "price_eur": Listing.price_eur,
    "ai_score": Listing.ai_score,
    "qm": Listing.qm,
}


@router.get("")
def list_listings(
    status: str | None = None,
    min_score: int = 0,
    source: str | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    min_qm: float | None = None,
    max_qm: float | None = None,
    min_rooms: float | None = None,
    sort: str = "first_seen_at",
    order: str = "desc",
    limit: int = 200,
    _: str = Depends(require_auth),
):
    with SessionLocal() as session:
        q = select(Listing).where(Listing.is_active.is_(True))
        if status:
            q = q.where(Listing.status == status)
        if min_score > 0:
            q = q.where(Listing.ai_score >= min_score)
        if source:
            q = q.where(Listing.source == source)
        if min_price is not None:
            q = q.where(Listing.price_eur >= min_price)
        if max_price is not None:
            q = q.where(Listing.price_eur <= max_price)
        if min_qm is not None:
            q = q.where(Listing.qm >= min_qm)
        if max_qm is not None:
            q = q.where(Listing.qm <= max_qm)
        if min_rooms is not None:
            q = q.where(Listing.rooms >= min_rooms)
        sort_col = _SORT_COLS.get(sort, Listing.first_seen_at)
        q = q.order_by(desc(sort_col) if order == "desc" else asc(sort_col))
        q = q.limit(min(limit, 500))
        listings = session.scalars(q).all()
        return [_serialize(l) for l in listings]


@router.get("/{listing_id}")
def get_listing(listing_id: int, _: str = Depends(require_auth)):
    with SessionLocal() as session:
        listing = session.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(404, "Listing nicht gefunden")
    return _serialize(listing)


@router.patch("/{listing_id}")
def patch_listing(listing_id: int, body: ListingPatch, _: str = Depends(require_auth)):
    if body.status and body.status not in _VALID_STATUSES:
        raise HTTPException(422, f"Ungültiger Status. Erlaubt: {_VALID_STATUSES}")
    with SessionLocal() as session:
        listing = session.get(Listing, listing_id)
        if listing is None:
            raise HTTPException(404)
        if body.status is not None:
            listing.status = body.status
        if body.notes is not None:
            listing.notes = body.notes
        session.commit()
        session.refresh(listing)
        return _serialize(listing)
```

- [ ] **Schritt 4: Tests laufen (erwartet: PASS)**

```bash
python -m pytest tests/test_api_listings.py -v
```

- [ ] **Schritt 5: Committen**

```bash
git add app/web/api/listings.py tests/test_api_listings.py
git commit -m "feat(api): Listings-Endpoints GET/PATCH inkl. price_per_sqm"
```

---

## Task 10: Settings API

**Files:**
- Modify: `app/web/api/settings.py`
- Create: `tests/test_api_settings.py`

- [ ] **Schritt 1: Failing Tests**

`tests/test_api_settings.py`:
```python
def test_get_settings_returns_dict(api_client):
    response = api_client.get("/api/v1/settings")
    assert response.status_code == 200
    data = response.json()
    assert "price_max" in data
    assert "poll_interval_minutes" in data
    assert "telegram_score_threshold" in data


def test_patch_settings_updates_value(api_client):
    api_client.patch("/api/v1/settings", json={"price_max": 1200000})
    response = api_client.get("/api/v1/settings")
    assert response.json()["price_max"] == 1200000


def test_patch_settings_rejects_unknown_key(api_client):
    response = api_client.patch("/api/v1/settings", json={"unknown_key_xyz": 42})
    assert response.status_code == 422
```

- [ ] **Schritt 2: Tests laufen (erwartet: FAIL)**

```bash
python -m pytest tests/test_api_settings.py -v
```

- [ ] **Schritt 3: Settings API implementieren**

`app/web/api/settings.py`:
```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.settings_service import get_all_settings, patch_settings, _DEFAULTS
from app.web.auth import require_auth

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def get_settings(_: str = Depends(require_auth)):
    return get_all_settings()


@router.patch("")
def update_settings(body: dict, _: str = Depends(require_auth)):
    unknown = [k for k in body if k not in _DEFAULTS]
    if unknown:
        raise HTTPException(422, f"Unbekannte Settings-Keys: {unknown}")
    patch_settings(body)
    return get_all_settings()
```

- [ ] **Schritt 4: Tests laufen (erwartet: PASS)**

```bash
python -m pytest tests/test_api_settings.py -v
```

- [ ] **Schritt 5: Committen**

```bash
git add app/web/api/settings.py tests/test_api_settings.py
git commit -m "feat(api): Settings GET/PATCH — DB-basierte Einstellungen"
```

---

## Task 11: Sources API

**Files:**
- Modify: `app/web/api/sources.py`

- [ ] **Schritt 1: Sources API implementieren**

`app/web/api/sources.py`:
```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.db import FetchRun, Source, SessionLocal
from app.web.auth import require_auth

router = APIRouter(prefix="/sources", tags=["sources"])

_BUILTIN_SOURCES = [
    "immoscout24", "immowelt", "kleinanzeigen",
    "makler_bsimmo", "makler_riedel", "makler_starnberg_immo",
    "sparkasse_immo", "tutzing24",
]


def _ensure_builtin_sources() -> None:
    """Builtin-Quellen in DB eintragen falls noch nicht vorhanden."""
    with SessionLocal() as session:
        for name in _BUILTIN_SOURCES:
            existing = session.scalars(
                select(Source).where(Source.name == name)
            ).first()
            if not existing:
                session.add(Source(name=name, url="", adapter_type="builtin"))
        session.commit()


def _serialize_source(source: Source) -> dict:
    return {
        "id": source.id,
        "name": source.name,
        "url": source.url,
        "adapter_type": source.adapter_type,
        "is_active": source.is_active,
        "last_crawl_at": source.last_crawl_at.isoformat() if source.last_crawl_at else None,
        "last_error": source.last_error,
        "created_at": source.created_at.isoformat(),
    }


class SourcePatch(BaseModel):
    is_active: bool | None = None


@router.get("")
def list_sources(_: str = Depends(require_auth)):
    _ensure_builtin_sources()
    with SessionLocal() as session:
        sources = session.scalars(select(Source).order_by(Source.name)).all()
        return [_serialize_source(s) for s in sources]


@router.patch("/{source_id}")
def patch_source(source_id: int, body: SourcePatch, _: str = Depends(require_auth)):
    with SessionLocal() as session:
        source = session.get(Source, source_id)
        if source is None:
            raise HTTPException(404)
        if body.is_active is not None:
            source.is_active = body.is_active
        session.commit()
        session.refresh(source)
        return _serialize_source(source)
```

- [ ] **Schritt 2: Rauchen-Test**

```bash
python -m scripts.run_web &
sleep 2
curl -u admin:tutzing2026! http://localhost:8000/api/v1/sources | python -m json.tool | head -30
kill %1
```

Erwartet: JSON-Array mit 8 Quellen.

- [ ] **Schritt 3: Committen**

```bash
git add app/web/api/sources.py
git commit -m "feat(api): Sources GET/PATCH — Quellen aktivieren/deaktivieren"
```

---

## Task 12: System API

**Files:**
- Modify: `app/web/api/system.py`

- [ ] **Schritt 1: System API implementieren**

`app/web/api/system.py`:
```python
from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import desc, func, select

from app.db import FetchRun, Listing, SessionLocal
from app.web.auth import require_auth

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/stats")
def get_stats(_: str = Depends(require_auth)):
    with SessionLocal() as session:
        total = session.scalar(select(func.count()).select_from(Listing))
        active = session.scalar(
            select(func.count()).select_from(Listing).where(Listing.is_active.is_(True))
        )
        notified = session.scalar(
            select(func.count()).select_from(Listing).where(Listing.notified_at.is_not(None))
        )
        avg_score = session.scalar(
            select(func.avg(Listing.ai_score)).where(Listing.ai_score.is_not(None))
        )
    return {
        "total_listings": total,
        "active_listings": active,
        "notified_listings": notified,
        "avg_ai_score": round(avg_score, 1) if avg_score else None,
    }


@router.get("/fetch-runs")
def get_fetch_runs(limit: int = 20, _: str = Depends(require_auth)):
    with SessionLocal() as session:
        runs = session.scalars(
            select(FetchRun).order_by(desc(FetchRun.started_at)).limit(limit)
        ).all()
        return [
            {
                "id": r.id,
                "source": r.source,
                "started_at": r.started_at.isoformat(),
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "listings_found": r.listings_found,
                "listings_new": r.listings_new,
                "error": r.error,
            }
            for r in runs
        ]


_crawl_running = False


@router.post("/crawl/trigger")
def trigger_crawl(background_tasks: BackgroundTasks, _: str = Depends(require_auth)):
    global _crawl_running
    if _crawl_running:
        return {"status": "already_running"}

    async def _run():
        global _crawl_running
        _crawl_running = True
        try:
            from app.scheduler import poll_and_notify
            await poll_and_notify()
        finally:
            _crawl_running = False

    background_tasks.add_task(asyncio.run, _run())
    return {"status": "triggered"}
```

- [ ] **Schritt 2: Committen**

```bash
git add app/web/api/system.py
git commit -m "feat(api): System-Endpoints — Stats, FetchRuns, Crawl-Trigger"
```

---

## Task 13: Telegram Test API

**Files:**
- Modify: `app/web/api/telegram.py`

- [ ] **Schritt 1: Telegram Test-Endpoint implementieren**

`app/web/api/telegram.py`:
```python
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.notify.telegram import send_telegram
from app.web.auth import require_auth

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/test")
async def test_telegram(_: str = Depends(require_auth)):
    ok = await send_telegram(
        "Test-Nachricht von immo-radar. Alles OK."
    )
    return {"success": ok}
```

- [ ] **Schritt 2: Committen**

```bash
git add app/web/api/telegram.py
git commit -m "feat(api): Telegram Test-Endpoint"
```

---

## Task 14: Gesamttest + Deploy

- [ ] **Schritt 1: Alle Tests laufen lassen**

```bash
python -m pytest tests/ -v
```

Erwartet: alle grün, keine Fehler.

- [ ] **Schritt 2: Lokaler Smoke-Test**

```bash
python -m scripts.run_web &
sleep 2
curl -u admin:tutzing2026! http://localhost:8000/api/v1/listings | python -m json.tool | head -20
curl -u admin:tutzing2026! http://localhost:8000/api/v1/settings | python -m json.tool
curl -u admin:tutzing2026! http://localhost:8000/api/v1/system/stats | python -m json.tool
kill %1
```

- [ ] **Schritt 3: Auf VPS deployen**

```bash
bash scripts/deploy.sh
```

- [ ] **Schritt 4: VPS Smoke-Test**

```bash
curl -u admin:tutzing2026! http://100.115.184.3:8001/api/v1/system/stats
```

Erwartet: JSON mit `total_listings`, `active_listings` etc.

- [ ] **Schritt 5: Abschließender Commit falls nötig**

```bash
git status
# Falls noch uncommitted changes:
git add -A && git commit -m "chore: Plan-1-Abschluss — alle Tests grün, VPS deployed"
git push
```

---

## Self-Review: Spec-Coverage

| Spec-Anforderung | Task |
|---|---|
| B1: enrich_pending Endlosschleife | Task 2 |
| B2: deploy.sh V1→V2 | Task 1 |
| B3: AI-Scoring debuggen | Task 3 |
| Score-Threshold Telegram (Phase 1.9) | Task 6 |
| `/api/v1/listings` GET+PATCH | Task 9 |
| `/api/v1/settings` GET+PATCH | Task 10 |
| `/api/v1/sources` GET+PATCH | Task 11 |
| `/api/v1/system/stats` + crawl/trigger | Task 12 |
| `/api/v1/telegram/test` | Task 13 |
| AppSetting DB-Modell | Task 4 |
| Source DB-Modell | Task 4 |
| Settings Service (DB statt .env) | Task 5 |
| CORS für Frontend-Dev-Server | Task 8 |
| SPA-Fallback für React-Router | Task 8 |
| Preis/m² in API-Response | Task 9 (_serialize) |

**Noch nicht in diesem Plan (→ Plan 2: Frontend):**
- React/Vite Setup, Listings UI, Filterleiste, Detailpanel
- Settings UI (Suchprofil, Telegram, Quellen-Toggle)
- System-Status-Seite UI
- Leaflet-Karte, Keyboard-Navigation, "Time on Market"
