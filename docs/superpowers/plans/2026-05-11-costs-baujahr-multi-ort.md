# API-Kosten · Baujahr 1850 · Multi-Ortsauswahl — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drei unabhängige Verbesserungen: (1) echtes Claude-Token-Tracking mit Kostenberechnung in den Einstellungen, (2) Baujahr-Slider auf min=1850, (3) Multi-Ortsauswahl im Suchprofil (mehrere Mittelpunkte + Radien).

**Architecture:**
- Token-Tracking: neue `ApiUsage`-DB-Tabelle, `app/usage.py` als Logging-Helper, Instrumentierung aller drei Claude-Aufrufe, neuer `GET /api/system/costs`-Endpoint, Anzeige in MechanicsTab.
- Multi-Ort: neues Setting `search_locations` (JSON-Array in `app_settings`-Tabelle), `settings_service.py` mit JSON-Handling, `lage.py` und `ai_match.py` für mehrere Standorte angepasst, neuer `MultiLocationPicker`-React-Komponent ersetzt `LocationPicker` in SearchProfileTab.
- Baujahr: ein-Zeile-Change in SearchProfileTab.tsx.

**Tech Stack:** FastAPI · SQLAlchemy · SQLite · anthropic SDK · React 18 + TypeScript + Tailwind CSS v3 · Leaflet (imperative L.map)

---

## Task 1: Baujahr-Slider min=1850

**Files:**
- Modify: `frontend/src/components/settings/SearchProfileTab.tsx`

- [ ] **Step 1: Zeile mit `min={1900}` finden und ändern**

In `SearchProfileTab.tsx` Zeile 121 ändern:

```tsx
// VORHER:
type="range" min={1900} max={2030} step={5}
// NACHHER:
type="range" min={1850} max={2030} step={5}
```

- [ ] **Step 2: TypeScript-Check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -5
```

Erwartet: keine Ausgabe (sauber).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/settings/SearchProfileTab.tsx
git commit -m "fix(ui): Baujahr-Slider min auf 1850 gesenkt"
```

---

## Task 2: ApiUsage DB-Modell

**Files:**
- Modify: `app/db.py`

- [ ] **Step 1: `ApiUsage`-Klasse lesen und verstehen**

Lies `app/db.py`. Die Datei hat bereits `Listing`, `ListingHistory`, `FetchRun`, `AppSetting`, `Source`. Füge `ApiUsage` als neue Klasse am Ende der Modelle ein (nach `Source`, vor `_ensure_db_dir`).

- [ ] **Step 2: `ApiUsage`-Modell hinzufügen**

```python
class ApiUsage(Base):
    __tablename__ = "api_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    model: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    purpose: Mapped[str] = mapped_column(String(32))  # "enrichment" | "analyze" | "discover"
```

- [ ] **Step 3: Inline-Migration in `init_db()` ergänzen**

Die bestehende Migration ist ein Loop über DDL-Strings. Ergänze nach dem `sources`-Block:

```python
with engine.connect() as conn:
    for ddl in [
        "CREATE TABLE IF NOT EXISTS api_usage (id INTEGER PRIMARY KEY, ts DATETIME, model TEXT, input_tokens INTEGER, output_tokens INTEGER, purpose TEXT)",
        "CREATE INDEX IF NOT EXISTS ix_api_usage_ts ON api_usage (ts)",
    ]:
        try:
            conn.execute(text(ddl))
            conn.commit()
        except Exception as e:
            if "already exists" not in str(e).lower():
                raise
```

Hinweis: `CREATE TABLE IF NOT EXISTS` und `CREATE INDEX IF NOT EXISTS` sind idempotent in SQLite — der try/except ist nur zusätzliche Absicherung.

- [ ] **Step 4: Test schreiben**

Datei: `tests/test_api_usage_model.py`

```python
import os
os.environ.setdefault("DB_PATH", "/tmp/immo_test_usage.db")

import pytest
from datetime import datetime, timedelta
from app.db import init_db, SessionLocal, ApiUsage


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db)
    # Re-import settings to pick up new DB_PATH
    import importlib, app.config, app.db
    importlib.reload(app.config)
    importlib.reload(app.db)
    from app.db import init_db
    init_db()
    yield


def test_api_usage_insert():
    from app.db import SessionLocal, ApiUsage
    with SessionLocal() as s:
        row = ApiUsage(
            ts=datetime.utcnow(),
            model="claude-haiku-4-5-20251001",
            input_tokens=500,
            output_tokens=80,
            purpose="enrichment",
        )
        s.add(row)
        s.commit()
        assert row.id is not None

def test_api_usage_query_by_ts():
    from app.db import SessionLocal, ApiUsage
    now = datetime.utcnow()
    with SessionLocal() as s:
        s.add(ApiUsage(ts=now, model="m", input_tokens=100, output_tokens=10, purpose="analyze"))
        s.add(ApiUsage(ts=now - timedelta(days=2), model="m", input_tokens=200, output_tokens=20, purpose="enrichment"))
        s.commit()

    cutoff = now - timedelta(hours=25)
    with SessionLocal() as s:
        recent = s.query(ApiUsage).filter(ApiUsage.ts >= cutoff).all()
    assert len(recent) == 1
    assert recent[0].purpose == "analyze"
```

- [ ] **Step 5: Test laufen lassen**

```bash
source .venv/bin/activate
DB_PATH=/tmp/immo_test2.db PYTHONPATH=. python -m pytest tests/test_api_usage_model.py -v 2>&1 | tail -10
```

Erwartet: 2 passed.

- [ ] **Step 6: Ruff-Check**

```bash
ruff check app/db.py
```

- [ ] **Step 7: Commit**

```bash
git add app/db.py tests/test_api_usage_model.py
git commit -m "feat(db): ApiUsage-Tabelle für Token-Tracking"
```

---

## Task 3: `app/usage.py` — Logging-Helper + Claude-Instrumentierung

**Files:**
- Create: `app/usage.py`
- Modify: `app/scoring/ai_match.py`
- Modify: `app/web/api/sources.py`

- [ ] **Step 1: `app/usage.py` erstellen**

```python
from __future__ import annotations

from datetime import datetime

import app.db as db_module

# USD per million tokens — update wenn Anthropic Preise ändert
_PRICES: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-haiku-3-5-20241022": {"input": 0.80, "output": 4.00},
}
_DEFAULT_PRICE = {"input": 0.80, "output": 4.00}


def tokens_to_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    price = _PRICES.get(model, _DEFAULT_PRICE)
    return (input_tokens * price["input"] + output_tokens * price["output"]) / 1_000_000


def log_usage(model: str, input_tokens: int, output_tokens: int, purpose: str) -> None:
    """Persist API token usage to DB. Call after every messages.create() success."""
    try:
        with db_module.SessionLocal() as session:
            row = db_module.ApiUsage(
                ts=datetime.utcnow(),
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                purpose=purpose,
            )
            session.add(row)
            session.commit()
    except Exception:
        pass  # Never let usage logging break the main flow
```

- [ ] **Step 2: `app/scoring/ai_match.py` instrumentieren**

Lies die Datei. Nach dem erfolgreichen `msg = await client.messages.create(...)` Call (Zeile 75) und dem Parsing, füge den `log_usage`-Aufruf ein:

```python
# In der try-Block nach msg = await client.messages.create(...)
from app.usage import log_usage  # lokaler Import, verhindert zirkuläre Importe
log_usage(
    model=settings.ai_model,
    input_tokens=msg.usage.input_tokens,
    output_tokens=msg.usage.output_tokens,
    purpose="enrichment",
)
```

Füge den Import direkt nach `msg = await client.messages.create(...)` ein, noch VOR dem `text = msg.content[0].text...`

- [ ] **Step 3: `app/web/api/sources.py` instrumentieren**

Lies die Datei. In `analyze_source`:

Nach `msg = client.messages.create(...)` in dem Claude-try-Block:

```python
from app.usage import log_usage
log_usage(
    model=_settings.ai_model,
    input_tokens=msg.usage.input_tokens,
    output_tokens=msg.usage.output_tokens,
    purpose="analyze",
)
```

In `discover_sources`:

Nach `msg = anthropic_client.messages.create(...)`:

```python
from app.usage import log_usage
log_usage(
    model=_settings.ai_model,
    input_tokens=msg.usage.input_tokens,
    output_tokens=msg.usage.output_tokens,
    purpose="discover",
)
```

- [ ] **Step 4: Ruff-Check**

```bash
ruff check app/usage.py app/scoring/ai_match.py app/web/api/sources.py
```

- [ ] **Step 5: Bestehende Tests laufen lassen**

```bash
DB_PATH=/tmp/immo_t3.db PYTHONPATH=. python -m pytest tests/ -q 2>&1 | tail -5
```

Erwartet: alle Tests grün (neue Datei app/usage.py wird nur importiert wenn Claude erfolgreich antwortet — kein Effekt auf bestehende Tests).

- [ ] **Step 6: Commit**

```bash
git add app/usage.py app/scoring/ai_match.py app/web/api/sources.py
git commit -m "feat(usage): Token-Logging nach jedem Claude-Aufruf"
```

---

## Task 4: `GET /api/system/costs` Endpoint

**Files:**
- Modify: `app/web/api/system.py`

- [ ] **Step 1: Test schreiben**

Datei: `tests/test_api_costs.py`

```python
import os
os.environ.setdefault("DB_PATH", "/tmp/immo_test_costs.db")

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db)
    import importlib, app.config, app.db
    importlib.reload(app.config)
    importlib.reload(app.db)
    from app.db import init_db, SessionLocal, ApiUsage
    init_db()

    # Seed: 2 Aufrufe heute, 1 vor 5 Tagen
    now = datetime.utcnow()
    with SessionLocal() as s:
        s.add(ApiUsage(ts=now, model="claude-haiku-4-5-20251001",
                       input_tokens=1000, output_tokens=100, purpose="enrichment"))
        s.add(ApiUsage(ts=now - timedelta(hours=2), model="claude-haiku-4-5-20251001",
                       input_tokens=500, output_tokens=50, purpose="analyze"))
        s.add(ApiUsage(ts=now - timedelta(days=5), model="claude-haiku-4-5-20251001",
                       input_tokens=800, output_tokens=80, purpose="enrichment"))
        s.commit()

    from app.web.server import app as fastapi_app
    return TestClient(fastapi_app)


def test_costs_structure(client):
    r = client.get("/api/system/costs")
    assert r.status_code == 200
    data = r.json()
    assert "last_24h" in data
    assert "last_7d" in data
    assert "breakdown_24h" in data
    assert data["last_24h"]["calls"] == 2
    assert data["last_7d"]["calls"] == 3


def test_costs_usd_positive(client):
    r = client.get("/api/system/costs")
    data = r.json()
    assert data["last_24h"]["usd"] > 0
    assert data["last_7d"]["usd"] >= data["last_24h"]["usd"]
```

- [ ] **Step 2: Test laufen lassen (FAIL erwartet)**

```bash
DB_PATH=/tmp/immo_c.db PYTHONPATH=. python -m pytest tests/test_api_costs.py -v 2>&1 | tail -10
```

Erwartet: FAIL mit "404" oder "AttributeError".

- [ ] **Step 3: Endpoint implementieren**

In `app/web/api/system.py`, füge nach den bestehenden Imports und vor den Routen folgendes hinzu:

```python
from datetime import timedelta
from app.db import ApiUsage
from app.usage import tokens_to_usd
```

Füge diese Modelle und den Route-Handler ein:

```python
class CostPeriod(BaseModel):
    usd: float
    calls: int
    input_tokens: int
    output_tokens: int


class CostsOut(BaseModel):
    last_24h: CostPeriod
    last_7d: CostPeriod
    breakdown_24h: dict[str, float]  # purpose -> usd


def _aggregate(rows: list) -> CostPeriod:
    if not rows:
        return CostPeriod(usd=0.0, calls=0, input_tokens=0, output_tokens=0)
    total_in = sum(r.input_tokens for r in rows)
    total_out = sum(r.output_tokens for r in rows)
    total_usd = sum(tokens_to_usd(r.model, r.input_tokens, r.output_tokens) for r in rows)
    return CostPeriod(
        usd=round(total_usd, 6),
        calls=len(rows),
        input_tokens=total_in,
        output_tokens=total_out,
    )


@router.get("/costs", response_model=CostsOut)
def get_costs() -> CostsOut:
    now = datetime.utcnow()
    cutoff_24h = now - timedelta(hours=24)
    cutoff_7d = now - timedelta(days=7)

    with db_module.SessionLocal() as session:
        rows_24h = session.query(ApiUsage).filter(ApiUsage.ts >= cutoff_24h).all()
        rows_7d = session.query(ApiUsage).filter(ApiUsage.ts >= cutoff_7d).all()

    breakdown: dict[str, float] = {}
    for purpose in {"enrichment", "analyze", "discover"}:
        relevant = [r for r in rows_24h if r.purpose == purpose]
        breakdown[purpose] = round(
            sum(tokens_to_usd(r.model, r.input_tokens, r.output_tokens) for r in relevant), 6
        )

    return CostsOut(
        last_24h=_aggregate(rows_24h),
        last_7d=_aggregate(rows_7d),
        breakdown_24h=breakdown,
    )
```

- [ ] **Step 4: Test laufen lassen (PASS erwartet)**

```bash
DB_PATH=/tmp/immo_c2.db PYTHONPATH=. python -m pytest tests/test_api_costs.py -v 2>&1 | tail -10
```

Erwartet: 2 passed.

- [ ] **Step 5: Ruff-Check**

```bash
ruff check app/web/api/system.py app/usage.py
```

- [ ] **Step 6: Commit**

```bash
git add app/web/api/system.py tests/test_api_costs.py
git commit -m "feat(api): GET /api/system/costs — echte Token-Kosten aus DB"
```

---

## Task 5: Frontend — Kosten-Anzeige in MechanicsTab

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api/system.ts`
- Modify: `frontend/src/components/settings/MechanicsTab.tsx`

- [ ] **Step 1: `ApiCosts`-Interface in `types.ts` ergänzen**

Lies `frontend/src/types.ts`. Füge am Ende hinzu:

```typescript
export interface CostPeriod {
  usd: number
  calls: number
  input_tokens: number
  output_tokens: number
}

export interface ApiCosts {
  last_24h: CostPeriod
  last_7d: CostPeriod
  breakdown_24h: Record<string, number>  // purpose -> usd
}
```

- [ ] **Step 2: `fetchCosts()` in `api/system.ts` ergänzen**

Lies `frontend/src/api/system.ts`. Füge hinzu:

```typescript
import type { SystemStatus, FetchRun, ApiCosts } from '../types'

// ...bestehende Funktionen...

export function fetchCosts(): Promise<ApiCosts> {
  return api.get('/api/system/costs')
}
```

- [ ] **Step 3: `MechanicsTab.tsx` — Kosten-Sektion ergänzen**

Lies `frontend/src/components/settings/MechanicsTab.tsx`. Füge folgenden Import hinzu:

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchSettings, patchSetting } from '../../api/settings'
import { fetchCosts } from '../../api/system'
import type { ApiCosts } from '../../types'
```

Füge am Anfang der `MechanicsTab`-Funktion nach den bestehenden Queries ein:

```typescript
const { data: costs } = useQuery<ApiCosts>({
  queryKey: ['api-costs'],
  queryFn: fetchCosts,
  refetchInterval: 60_000,  // alle 60s aktualisieren
})
```

Füge vor dem letzten `</div>` (Ende der return-Anweisung) eine neue Sektion ein:

```tsx
<div className="py-4 border-t mt-2" style={{ borderColor: 'var(--border)' }}>
  <p className="text-sm font-medium mb-1" style={{ color: 'var(--fg)' }}>API-Kosten (Claude)</p>
  <p className="text-xs mb-3" style={{ color: 'var(--muted)' }}>
    Tatsächliche Anthropic-API-Kosten aus Token-Tracking
  </p>
  {costs ? (
    <div className="space-y-2">
      <div className="flex gap-6">
        <div>
          <p className="text-xs" style={{ color: 'var(--muted)' }}>Letzte 24h</p>
          <p className="font-mono text-sm font-semibold" style={{ color: 'var(--fg)' }}>
            ${costs.last_24h.usd.toFixed(4)}
          </p>
          <p className="text-xs" style={{ color: 'var(--muted)' }}>{costs.last_24h.calls} Aufrufe</p>
        </div>
        <div>
          <p className="text-xs" style={{ color: 'var(--muted)' }}>Letzte 7 Tage</p>
          <p className="font-mono text-sm font-semibold" style={{ color: 'var(--fg)' }}>
            ${costs.last_7d.usd.toFixed(4)}
          </p>
          <p className="text-xs" style={{ color: 'var(--muted)' }}>{costs.last_7d.calls} Aufrufe</p>
        </div>
      </div>
      <div className="flex gap-3 flex-wrap">
        {Object.entries(costs.breakdown_24h).map(([purpose, usd]) => (
          <span key={purpose} className="text-xs px-2 py-0.5 rounded" style={{ background: 'var(--border)', color: 'var(--muted)' }}>
            {purpose === 'enrichment' ? 'Scoring' : purpose === 'analyze' ? 'Analyse' : 'Entdecken'}:&nbsp;
            <span className="font-mono" style={{ color: 'var(--fg)' }}>${usd.toFixed(4)}</span>
          </span>
        ))}
      </div>
    </div>
  ) : (
    <p className="text-xs" style={{ color: 'var(--muted)' }}>Lade…</p>
  )}
</div>
```

- [ ] **Step 4: TypeScript-Check**

```bash
cd frontend && npx tsc --noEmit 2>&1
```

Alle Fehler beheben.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types.ts frontend/src/api/system.ts frontend/src/components/settings/MechanicsTab.tsx
git commit -m "feat(ui): API-Kosten-Anzeige in MechanicsTab"
```

---

## Task 6: `search_locations` Setting + Backend

**Files:**
- Modify: `app/settings_service.py`
- Modify: `app/scoring/lage.py`
- Modify: `app/scoring/ai_match.py`

- [ ] **Step 1: Test schreiben**

Datei: `tests/test_search_locations.py`

```python
import os
os.environ.setdefault("DB_PATH", "/tmp/immo_test_loc.db")

import pytest


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db)
    import importlib, app.config, app.db, app.settings_service
    importlib.reload(app.config)
    importlib.reload(app.db)
    importlib.reload(app.settings_service)
    from app.db import init_db
    init_db()
    yield


def test_search_locations_fallback():
    """When not set in DB, should return list from single-location settings."""
    from app.settings_service import get_setting
    locs = get_setting("search_locations")
    assert isinstance(locs, list)
    assert len(locs) >= 1
    first = locs[0]
    assert "lat" in first and "lon" in first and "radius_km" in first


def test_search_locations_roundtrip():
    """set_setting stores as JSON, get_setting returns parsed list."""
    from app.settings_service import get_setting, set_setting
    locs = [
        {"lat": 47.9095, "lon": 11.2783, "radius_km": 5, "label": "Tutzing"},
        {"lat": 47.8651, "lon": 11.3415, "radius_km": 3, "label": "Starnberg"},
    ]
    set_setting("search_locations", locs)
    result = get_setting("search_locations")
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[1]["label"] == "Starnberg"


def test_in_search_area_multi():
    """in_search_area with locations list: True if within ANY circle."""
    from app.scoring.lage import in_search_area
    locations = [
        {"lat": 47.9095, "lon": 11.2783, "radius_km": 5},
        {"lat": 48.1351, "lon": 11.5820, "radius_km": 3},  # München
    ]
    # Tutzing center — in first circle
    assert in_search_area(47.9095, 11.2783, locations) is True
    # Munich center — in second circle
    assert in_search_area(48.1351, 11.5820, locations) is True
    # Hamburg — in neither
    assert in_search_area(53.55, 10.00, locations) is False
    # None coords — always True (don't filter unknown)
    assert in_search_area(None, None, locations) is True
```

- [ ] **Step 2: Test laufen lassen (FAIL erwartet)**

```bash
DB_PATH=/tmp/immo_loc.db PYTHONPATH=. python -m pytest tests/test_search_locations.py -v 2>&1 | tail -15
```

Erwartet: FAIL.

- [ ] **Step 3: `settings_service.py` anpassen**

Lies `app/settings_service.py`. Ergänze/ändere:

```python
from __future__ import annotations

import json as _json
from typing import Any

import app.db as db_module
from app.config import settings as env_settings

_DEFAULTS: dict[str, tuple[str, type]] = {
    "poll_interval_minutes": ("poll_interval_minutes", int),
    "detail_fetch_interval_minutes": ("detail_fetch_interval_minutes", int),
    "search_center_lat": ("search_center_lat", float),
    "search_center_lon": ("search_center_lon", float),
    "search_radius_km": ("search_radius_km", float),
    "price_min": ("price_min", int),
    "price_max": ("price_max", int),
    "qm_min": ("qm_min", int),
    "qm_max": ("qm_max", int),
    "rooms_min": ("rooms_min", float),
    "year_built_min": ("year_built_min", int),
    "property_types": ("property_types", str),
    "score_threshold": ("score_threshold", float),
    "search_locations": ("search_locations", str),  # stored as JSON, special handling below
}

_JSON_KEYS = {"search_locations"}


def get_setting(key: str) -> Any:
    """Return setting value from DB, falling back to env/default."""
    with db_module.SessionLocal() as session:
        row = session.get(db_module.AppSetting, key)
        if row is not None:
            if key in _JSON_KEYS:
                return _json.loads(row.value)
            _, cast = _DEFAULTS.get(key, (None, str))
            return cast(row.value)
    # Fallback for search_locations: derive from individual lat/lon/radius settings
    if key == "search_locations":
        return [{
            "lat": get_setting("search_center_lat"),
            "lon": get_setting("search_center_lon"),
            "radius_km": get_setting("search_radius_km"),
            "label": "Hauptstandort",
        }]
    attr, cast = _DEFAULTS.get(key, (key, str))
    val = getattr(env_settings, attr, None)
    return val


def set_setting(key: str, value: Any) -> None:
    """Persist a setting to DB."""
    str_value = _json.dumps(value, ensure_ascii=False) if key in _JSON_KEYS else str(value)
    with db_module.SessionLocal() as session:
        row = session.get(db_module.AppSetting, key)
        if row is None:
            row = db_module.AppSetting(key=key, value=str_value)
            session.add(row)
        else:
            row.value = str_value
        session.commit()


def get_all_settings() -> dict[str, Any]:
    """Return all known settings with their current values."""
    return {key: get_setting(key) for key in _DEFAULTS}
```

- [ ] **Step 4: `lage.py` — `in_search_area()` updaten**

Lies `app/scoring/lage.py`. Ändere `in_search_area`:

```python
def in_search_area(
    lat: float | None,
    lon: float | None,
    locations: list[dict] | None = None,
) -> bool:
    if lat is None or lon is None:
        return True  # don't filter unknown locations
    if not locations:
        # legacy: use single-location settings
        center = (settings.search_center_lat, settings.search_center_lon)
        return haversine_km(center, (lat, lon)) <= settings.search_radius_km
    return any(
        haversine_km((loc["lat"], loc["lon"]), (lat, lon)) <= loc["radius_km"]
        for loc in locations
    )
```

- [ ] **Step 5: `ai_match.py` — Prompt für Multi-Ort updaten**

Lies `app/scoring/ai_match.py`. Ändere:

1. Den `_PROMPT`-String: Ersetze die `{radius}`-Zeile:

```python
# ALT:
# - Lage: PLZ 82327 + {radius} km Radius (Tutzing, Bernried, Feldafing, Pöcking, Possenhofen, Berg)

# NEU (in _PROMPT):
- Suchgebiete: {locations}
```

2. In `score_listing()`, füge oben den Import ein und baue den `locations`-String:

```python
from app.settings_service import get_setting as _get_setting  # lazy import im Funktionskörper

async def score_listing(...) -> tuple[int, str] | None:
    if not settings.anthropic_api_key:
        ...

    # build locations string
    from app.settings_service import get_setting as _get_setting
    search_locs = _get_setting("search_locations")
    locs_str = "; ".join(
        f"{loc.get('label', 'Standort')} ({loc.get('radius_km', 5):.0f} km Radius)"
        for loc in search_locs
    )

    prompt = _PROMPT.format(
        price_min=settings.price_min,
        price_max=settings.price_max,
        qm_min=settings.qm_min,
        qm_max=settings.qm_max,
        rooms_min=settings.rooms_min,
        types=", ".join(settings.property_type_list),
        year_built_min=settings.year_built_min,
        locations=locs_str,  # NEU — ersetzt {radius}
        title=...,
        # ... rest unverändert
    )
```

Stelle sicher, dass `{radius}` aus dem format()-Aufruf entfernt wird (es gibt kein `radius=` mehr).

- [ ] **Step 6: Tests laufen lassen**

```bash
DB_PATH=/tmp/immo_loc2.db PYTHONPATH=. python -m pytest tests/test_search_locations.py tests/ -q 2>&1 | tail -8
```

Erwartet: alle Tests grün.

- [ ] **Step 7: Ruff-Check**

```bash
ruff check app/settings_service.py app/scoring/lage.py app/scoring/ai_match.py
```

- [ ] **Step 8: Commit**

```bash
git add app/settings_service.py app/scoring/lage.py app/scoring/ai_match.py tests/test_search_locations.py
git commit -m "feat(settings): search_locations Multi-Ort-Setting + lage/ai_match angepasst"
```

---

## Task 7: `MultiLocationPicker`-Komponent

**Files:**
- Create: `frontend/src/components/map/MultiLocationPicker.tsx`

Der Komponent zeigt eine Leaflet-Karte mit mehreren verschiebbaren Markern + Radius-Kreisen. Darunter eine Liste zum Bearbeiten/Löschen/Hinzufügen von Standorten.

- [ ] **Step 1: `MultiLocationPicker.tsx` erstellen**

```tsx
import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import { useDebounce } from '../../hooks/useDebounce'

export interface SearchLocation {
  lat: number
  lon: number
  radius_km: number
  label: string
}

interface Props {
  locations: SearchLocation[]
  onChange: (locations: SearchLocation[]) => void
}

const CIRCLE_COLORS = [
  'var(--accent)',
  '#f59e0b',
  '#10b981',
  '#8b5cf6',
  '#ef4444',
]

export function MultiLocationPicker({ locations, onChange }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const markersRef = useRef<L.Marker[]>([])
  const circlesRef = useRef<L.Circle[]>([])
  const locationsRef = useRef<SearchLocation[]>(locations)

  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounce(search, 1000)

  // Keep ref in sync for drag handlers
  useEffect(() => {
    locationsRef.current = locations
  }, [locations])

  // Init map once
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    // Fix Vite marker icons
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    delete (L.Icon.Default.prototype as any)._getIconUrl
    L.Icon.Default.mergeOptions({
      iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
      iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
      shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
    })

    const initialCenter: L.LatLngExpression = locations.length > 0
      ? [locations[0].lat, locations[0].lon]
      : [47.9095, 11.2783]

    const map = L.map(containerRef.current, {
      center: initialCenter,
      zoom: 10,
      scrollWheelZoom: true,
    })

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>',
    }).addTo(map)

    mapRef.current = map

    return () => {
      map.remove()
      mapRef.current = null
      markersRef.current = []
      circlesRef.current = []
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Sync markers/circles when locations change
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    // Remove old
    markersRef.current.forEach(m => m.remove())
    circlesRef.current.forEach(c => c.remove())
    markersRef.current = []
    circlesRef.current = []

    // Add new
    locations.forEach((loc, i) => {
      const color = CIRCLE_COLORS[i % CIRCLE_COLORS.length]
      const marker = L.marker([loc.lat, loc.lon], { draggable: true }).addTo(map)
      const circle = L.circle([loc.lat, loc.lon], {
        radius: loc.radius_km * 1000,
        color,
        fillColor: color,
        fillOpacity: 0.08,
        weight: 2,
      }).addTo(map)

      marker.on('dragend', () => {
        const pos = marker.getLatLng()
        circle.setLatLng(pos)
        const updated = [...locationsRef.current]
        updated[i] = { ...updated[i], lat: pos.lat, lon: pos.lng }
        onChange(updated)
      })

      markersRef.current.push(marker)
      circlesRef.current.push(circle)
    })
  }, [locations]) // eslint-disable-line react-hooks/exhaustive-deps

  // Geocode search
  useEffect(() => {
    if (!debouncedSearch || debouncedSearch.length < 3 || !mapRef.current) return

    fetch(
      `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(debouncedSearch)}&format=json&limit=1&countrycodes=de`,
      { headers: { 'Accept-Language': 'de', 'User-Agent': 'immo-radar/1.0 philipp.herrlich@googlemail.com' } }
    )
      .then(r => r.json())
      .then((results: Array<{ lat: string; lon: string; display_name: string }>) => {
        if (!results[0]) return
        const lat = parseFloat(results[0].lat)
        const lon = parseFloat(results[0].lon)
        const label = debouncedSearch
        mapRef.current?.setView([lat, lon], 12)
        // Add as new location
        onChange([...locationsRef.current, { lat, lon, radius_km: 5, label }])
        setSearch('')
      })
      .catch(() => {})
  }, [debouncedSearch]) // eslint-disable-line react-hooks/exhaustive-deps

  function addAtCenter() {
    const center = mapRef.current?.getCenter() ?? { lat: 47.9095, lng: 11.2783 }
    onChange([...locations, { lat: center.lat, lon: center.lng, radius_km: 5, label: '' }])
  }

  function remove(i: number) {
    if (locations.length <= 1) return // min 1 location
    onChange(locations.filter((_, idx) => idx !== i))
  }

  function updateLabel(i: number, label: string) {
    const updated = [...locations]
    updated[i] = { ...updated[i], label }
    onChange(updated)
  }

  function updateRadius(i: number, radius_km: number) {
    const updated = [...locations]
    updated[i] = { ...updated[i], radius_km }
    circlesRef.current[i]?.setRadius(radius_km * 1000)
    onChange(updated)
  }

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <input
          type="text"
          placeholder="Ort suchen + hinzufügen (z.B. Starnberg…)"
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="flex-1 px-3 py-2 rounded-lg border text-sm focus:outline-none"
          style={{ borderColor: 'var(--border)', color: 'var(--fg)' }}
          onFocus={e => (e.target.style.borderColor = 'var(--accent)')}
          onBlur={e => (e.target.style.borderColor = 'var(--border)')}
        />
        <button
          onClick={addAtCenter}
          className="px-3 py-2 rounded-lg border text-sm"
          style={{ borderColor: 'var(--border)', color: 'var(--muted)' }}
          title="Kartenmittelpunkt als Standort hinzufügen"
        >
          + Ort
        </button>
      </div>

      <div
        ref={containerRef}
        className="rounded-lg overflow-hidden border"
        style={{ height: '280px', borderColor: 'var(--border)' }}
      />

      <div className="space-y-2">
        {locations.map((loc, i) => (
          <div
            key={i}
            className="flex items-center gap-2 px-3 py-2 rounded-lg border"
            style={{ borderColor: 'var(--border)', borderLeftColor: CIRCLE_COLORS[i % CIRCLE_COLORS.length], borderLeftWidth: '3px' }}
          >
            <input
              type="text"
              placeholder={`Standort ${i + 1}`}
              value={loc.label}
              onChange={e => updateLabel(i, e.target.value)}
              className="flex-1 text-sm px-2 py-1 rounded border focus:outline-none"
              style={{ borderColor: 'var(--border)', color: 'var(--fg)' }}
            />
            <input
              type="range"
              min={1}
              max={25}
              step={1}
              value={loc.radius_km}
              onChange={e => updateRadius(i, Number(e.target.value))}
              className="w-20 accent-[var(--accent)]"
            />
            <span className="font-mono text-xs w-10 text-right" style={{ color: 'var(--muted)' }}>
              {loc.radius_km} km
            </span>
            <button
              onClick={() => remove(i)}
              disabled={locations.length <= 1}
              className="text-xs px-1.5 py-1 rounded disabled:opacity-30"
              style={{ color: 'var(--muted)' }}
              title="Standort entfernen"
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: TypeScript-Check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

Alle Fehler beheben.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/map/MultiLocationPicker.tsx
git commit -m "feat(ui): MultiLocationPicker — mehrere Suchstandorte auf Leaflet-Karte"
```

---

## Task 8: SearchProfileTab — MultiLocationPicker einbinden

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api/settings.ts`
- Modify: `frontend/src/components/settings/SearchProfileTab.tsx`

- [ ] **Step 1: `SearchLocation` + `AppSettings` in `types.ts` ergänzen**

Lies `frontend/src/types.ts`. Füge hinzu:

```typescript
export interface SearchLocation {
  lat: number
  lon: number
  radius_km: number
  label: string
}
```

Und ergänze in `AppSettings`:

```typescript
export interface AppSettings {
  // ...bestehende Felder...
  search_locations: SearchLocation[]  // NEU
}
```

- [ ] **Step 2: `settings.ts` anpassen**

Lies `frontend/src/api/settings.ts`. Das Backend liefert `search_locations` bereits als geparste Liste (JSON). Der `parseSettings`-Helper muss sie nicht anfassen — aber `RawSettings` muss sie kennen:

```typescript
type RawSettings = Omit<AppSettings, 'property_types'> & {
  property_types: string
  // search_locations kommt bereits als Array vom Backend
}
```

Der `parseSettings`-Helper bleibt unverändert (er kopiert `search_locations` unverändert via spread).

`patchSetting` funktioniert bereits (schickt beliebige `value`). Kein weiterer Änderungsbedarf.

- [ ] **Step 3: `SearchProfileTab.tsx` umbauen**

Lies `frontend/src/components/settings/SearchProfileTab.tsx` vollständig. Ersetze den gesamten Suchgebiet-Block (mit LocationPicker) durch den MultiLocationPicker.

Ändere die Imports — ersetze `LocationPicker`-Import durch `MultiLocationPicker`:

```tsx
import { MultiLocationPicker, type SearchLocation } from '../map/MultiLocationPicker'
```

Ersetze die drei einzelnen Mutations für `centerLat`, `centerLon`, `radius`:

```tsx
// ALT:
const centerLatMut = useSetting('search_center_lat')
const centerLonMut = useSetting('search_center_lon')
const radiusMut = useSetting('search_radius_km')

// NEU:
const locationsMut = useMutation({
  mutationFn: (locations: SearchLocation[]) =>
    patchSetting('search_locations', locations),
  onSuccess: (data) => {
    queryClient.setQueryData(['settings'], data)
  },
})
```

Ersetze den Suchgebiet-Block:

```tsx
{/* ALT — LocationPicker-Block */}
<div className="py-4 border-b" style={{ borderColor: 'var(--border)' }}>
  ...
  <LocationPicker ... />
</div>

{/* NEU */}
<div className="py-4 border-b" style={{ borderColor: 'var(--border)' }}>
  <p className="text-sm font-medium mb-1" style={{ color: 'var(--fg)' }}>Suchgebiete</p>
  <p className="text-xs mb-3" style={{ color: 'var(--muted)' }}>
    Mehrere Standorte möglich · Marker verschieben oder Ort suchen · Radius per Slider
  </p>
  <MultiLocationPicker
    locations={s.search_locations ?? [{ lat: s.search_center_lat ?? 47.9095, lon: s.search_center_lon ?? 11.2783, radius_km: s.search_radius_km ?? 5, label: 'Hauptstandort' }]}
    onChange={(locs) => locationsMut.mutate(locs)}
  />
</div>
```

- [ ] **Step 4: TypeScript-Check**

```bash
cd frontend && npx tsc --noEmit 2>&1
```

Alle Fehler beheben.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types.ts frontend/src/api/settings.ts frontend/src/components/settings/SearchProfileTab.tsx
git commit -m "feat(ui): SearchProfileTab nutzt MultiLocationPicker (Multi-Ort)"
```

---

## Task 9: Build + Deploy + Backlog

- [ ] **Step 1: Vollständige Test-Suite**

```bash
DB_PATH=/tmp/immo_final.db PYTHONPATH=. python -m pytest tests/ -q 2>&1 | tail -5
```

Erwartet: alle Tests grün.

- [ ] **Step 2: Frontend-Build**

```bash
cd frontend && npm run build 2>&1 | tail -8
```

Erwartet: `✓ built in X.XXs` ohne Fehler.

- [ ] **Step 3: Deploy**

```bash
bash scripts/deploy.sh
```

Erwartet am Ende: `✓ Deployed.`

- [ ] **Step 4: Backlog aktualisieren**

In `docs/backlog.md`:
- `3.2` (Markt-Trendanalyse): lassen
- Ergänze unter Phase 2:

```markdown
| 2.9 | API-Kosten-Tracking (Token-Logging + Anzeige) | ✅ | M |
| 2.10 | Multi-Ortsauswahl im Suchprofil | ✅ | L |
```

Und unter Phase 1 (1.8):
- Sub-Feature `Baujahr-Slider ab 1850` → ✅

- [ ] **Step 5: Commit**

```bash
git add docs/backlog.md
git commit -m "chore(backlog): Kosten-Tracking + Multi-Ort + Baujahr 1850 als ✅"
```
