# Domain, Auth, Filter & Maps — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate dashboard to `immo.herrlich.dev` with Caddy auth, complete the Phase 1 filter bar and search profile tab, then add Leaflet maps (detail minimap, listings map toggle, settings picker).

**Architecture:**
- Caddy handles TLS + basicauth at edge; Docker container moves to `127.0.0.1:8001`
- Filter params (`price_min/max`, `qm_min/max`, `rooms_min`, `sort`) added to backend `GET /api/listings`
- Leaflet + react-leaflet installed in frontend; three map surfaces: DetailPanel minimap, ListingsPage map toggle, SearchProfileTab center-pin picker
- No new backend tables needed for maps (coordinates already in DB)

**Tech Stack:** FastAPI · React 18 + Vite · Tailwind CSS v3 · Leaflet + react-leaflet · Caddy · Docker

---

## Task 1: Domain + Auth (Caddy + docker-compose)

**Files:**
- Modify: `docker-compose.yml`
- Modify: `scripts/deploy.sh`
- VPS: `/etc/caddy/Caddyfile` (updated via deploy script)

**What to do:**

- [ ] **Step 1: Update `docker-compose.yml` — bind on localhost only**

Change the `web` service ports binding so only Caddy can reach it (not Tailscale or public internet):

```yaml
services:
  web:
    ports:
      - "127.0.0.1:8001:8000"   # was: "100.115.184.3:8001:8000"
```

- [ ] **Step 2: Update `scripts/deploy.sh` — add Caddy config block**

After the `docker compose up -d --build` step, add a block that idempotently writes the Caddy vhost for `immo.herrlich.dev` if it doesn't exist yet, then reloads Caddy:

```bash
echo "==> Caddy: Eintrag für immo.herrlich.dev sicherstellen"
ssh "$TARGET" bash <<'SSHEOF'
CADDYFILE=/etc/caddy/Caddyfile
if ! grep -q "immo.herrlich.dev" "$CADDYFILE"; then
  cat >> "$CADDYFILE" <<'CADDY'

immo.herrlich.dev {
    basicauth {
        admin $2a$14$.dJIfNvGH1LbWupB02VuLeXBMHDzMA9BSRTbB0ceUn2rmcyv4j5N6
    }
    reverse_proxy localhost:8001
}
CADDY
  systemctl reload caddy
  echo "  ✓ immo.herrlich.dev hinzugefügt und Caddy neu geladen"
else
  echo "  ✓ immo.herrlich.dev bereits konfiguriert"
fi
SSHEOF
```

Note: The bcrypt hash above is for `tutzing2026!` — same hash already used for `h5.herrlich.dev` (admin user, same password). Verify with: `caddy hash-password` on the VPS if needed.

- [ ] **Step 3: Update deploy success message**

```bash
echo "  Dashboard: https://immo.herrlich.dev  (admin / tutzing2026!)"
```

- [ ] **Step 4: Update `CLAUDE.md` deploy section log command** (uses `docker compose` not `docker-compose`)

In CLAUDE.md Key Commands, the logs line should already say `docker compose logs` — verify it's correct.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml scripts/deploy.sh
git commit -m "feat(deploy): immo.herrlich.dev via Caddy basicauth, container auf 127.0.0.1"
```

---

## Task 2: Backend — Filter params für GET /api/listings

**Files:**
- Modify: `app/web/api/listings.py`

The frontend filter bar will send `price_min`, `price_max`, `qm_min`, `qm_max`, `rooms_min`, and `sort` as query parameters. The backend needs to handle them.

- [ ] **Step 1: Write failing test**

Create `tests/test_listings_filter.py`:

```python
import pytest
from fastapi.testclient import TestClient
from app.web.server import app
from app.db import SessionLocal, Listing, init_db
from datetime import datetime

@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    with SessionLocal() as s:
        for i, (price, qm, rooms) in enumerate([(500_000, 80.0, 3.0), (900_000, 140.0, 5.0), (300_000, 60.0, 2.0)]):
            s.add(Listing(
                source_id=f"t{i}", source="test", title=f"T{i}", url=f"http://t{i}",
                price_eur=price, qm=qm, rooms=rooms, status="neu",
                first_seen_at=datetime.utcnow(), last_seen_at=datetime.utcnow(), is_active=True,
            ))
        s.commit()

client = TestClient(app)

def test_price_filter():
    r = client.get("/api/listings/?price_min=400000&price_max=700000")
    assert r.status_code == 200
    prices = [l["price_eur"] for l in r.json()]
    assert all(400_000 <= p <= 700_000 for p in prices)

def test_qm_filter():
    r = client.get("/api/listings/?qm_min=70&qm_max=150")
    assert r.status_code == 200
    for l in r.json():
        assert 70 <= l["qm"] <= 150

def test_rooms_filter():
    r = client.get("/api/listings/?rooms_min=3")
    assert r.status_code == 200
    for l in r.json():
        assert l["rooms"] >= 3

def test_sort_price_asc():
    r = client.get("/api/listings/?sort=price_asc")
    prices = [l["price_eur"] for l in r.json()]
    assert prices == sorted(prices)

def test_sort_price_desc():
    r = client.get("/api/listings/?sort=price_desc")
    prices = [l["price_eur"] for l in r.json()]
    assert prices == sorted(prices, reverse=True)
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
pytest tests/test_listings_filter.py -v
```

Expected: AssertionError (params not supported yet).

- [ ] **Step 3: Implement filter params in `app/web/api/listings.py`**

Replace the `get_listings` function:

```python
from sqlalchemy import asc, desc as sqla_desc

@router.get("/", response_model=list[ListingOut])
def get_listings(
    status: str | None = None,
    portal: str | None = None,
    min_score: float | None = None,
    price_min: int | None = None,
    price_max: int | None = None,
    qm_min: float | None = None,
    qm_max: float | None = None,
    rooms_min: float | None = None,
    sort: str | None = None,  # "date_desc" | "price_asc" | "price_desc" | "score_desc" | "ppm_asc" | "ppm_desc"
):
    with db_module.SessionLocal() as session:
        q = session.query(Listing)
        if status:
            q = q.filter(Listing.status == status)
        if portal:
            q = q.filter(Listing.source == portal)
        if min_score is not None:
            q = q.filter(Listing.lage_score >= min_score)
        if price_min is not None:
            q = q.filter(Listing.price_eur >= price_min)
        if price_max is not None:
            q = q.filter(Listing.price_eur <= price_max)
        if qm_min is not None:
            q = q.filter(Listing.qm >= qm_min)
        if qm_max is not None:
            q = q.filter(Listing.qm <= qm_max)
        if rooms_min is not None:
            q = q.filter(Listing.rooms >= rooms_min)

        _SORT_MAP = {
            "price_asc":  asc(Listing.price_eur),
            "price_desc": sqla_desc(Listing.price_eur),
            "score_desc": sqla_desc(Listing.ai_score),
        }
        order = _SORT_MAP.get(sort or "date_desc", sqla_desc(Listing.last_seen_at))
        q = q.order_by(order)

        results = q.all()
        listings = [ListingOut.model_validate(l) for l in results]

        if sort == "ppm_asc":
            listings.sort(key=lambda l: l.price_per_sqm or float("inf"))
        elif sort == "ppm_desc":
            listings.sort(key=lambda l: l.price_per_sqm or 0, reverse=True)

        return listings
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/test_listings_filter.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add app/web/api/listings.py tests/test_listings_filter.py
git commit -m "feat(api): Preis/m²/Zimmer-Filter + Sortierung in GET /api/listings"
```

---

## Task 3: Frontend — Filterleiste vervollständigen

**Files:**
- Modify: `frontend/src/components/listings/FilterBar.tsx`
- Modify: `frontend/src/store/ui.ts`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api/listings.ts`
- Modify: `frontend/src/pages/ListingsPage.tsx`

The FilterBar currently has only status chips, score select, and portal select. We add price range, m² range, rooms-min stepper, and sort dropdown.

- [ ] **Step 1: Extend `ListingsFilter` type in `frontend/src/types.ts`**

Add to the `ListingsFilter` interface:

```typescript
export interface ListingsFilter {
  status: string;
  portal: string;
  minScore: number;
  // new:
  priceMin: number | null;
  priceMax: number | null;
  qmMin: number | null;
  qmMax: number | null;
  roomsMin: number | null;
  sort: 'date_desc' | 'price_asc' | 'price_desc' | 'score_desc' | 'ppm_asc' | 'ppm_desc';
}
```

- [ ] **Step 2: Update default filter in `frontend/src/store/ui.ts`**

```typescript
filter: {
  status: '',
  portal: '',
  minScore: 0,
  priceMin: null,
  priceMax: null,
  qmMin: null,
  qmMax: null,
  roomsMin: null,
  sort: 'date_desc',
} as ListingsFilter,
```

- [ ] **Step 3: Update `frontend/src/api/listings.ts` — pass new params**

In `fetchListings`, map filter fields to query params:

```typescript
export async function fetchListings(filter: ListingsFilter): Promise<Listing[]> {
  const params = new URLSearchParams();
  if (filter.status) params.set('status', filter.status);
  if (filter.portal) params.set('portal', filter.portal);
  if (filter.minScore) params.set('min_score', String(filter.minScore));
  if (filter.priceMin != null) params.set('price_min', String(filter.priceMin));
  if (filter.priceMax != null) params.set('price_max', String(filter.priceMax));
  if (filter.qmMin != null) params.set('qm_min', String(filter.qmMin));
  if (filter.qmMax != null) params.set('qm_max', String(filter.qmMax));
  if (filter.roomsMin != null) params.set('rooms_min', String(filter.roomsMin));
  if (filter.sort && filter.sort !== 'date_desc') params.set('sort', filter.sort);
  const res = await apiClient.get<Listing[]>(`/listings/?${params}`);
  return res.data;
}
```

- [ ] **Step 4: Rewrite `frontend/src/components/listings/FilterBar.tsx`**

Full replacement — add price inputs, m² inputs, rooms stepper, sort select. Keep existing status chips and score/portal selects. Layout: two rows — top row = status chips + sort; bottom row = price / m² / rooms / score / portal (collapsible on mobile).

```tsx
import { useUIStore } from '../../store/ui'
import { Source } from '../../types'
import { cn } from '../../lib/cn'
import { ArrowsDownUp, Funnel } from '@phosphor-icons/react'

const STATUS_OPTIONS = [
  { value: '', label: 'Alle' },
  { value: 'neu', label: 'Neu' },
  { value: 'interessant', label: 'Interessant' },
  { value: 'vielleicht', label: 'Vielleicht' },
  { value: 'gesehen', label: 'Gesehen' },
  { value: 'abgelehnt', label: 'Abgelehnt' },
]

const SORT_OPTIONS = [
  { value: 'date_desc', label: 'Neueste zuerst' },
  { value: 'price_asc', label: 'Preis ↑' },
  { value: 'price_desc', label: 'Preis ↓' },
  { value: 'score_desc', label: 'Score ↓' },
  { value: 'ppm_asc', label: '€/m² ↑' },
  { value: 'ppm_desc', label: '€/m² ↓' },
]

const SCORE_OPTIONS = [
  { value: 0, label: 'Alle Scores' },
  { value: 50, label: 'Score ≥ 50' },
  { value: 70, label: 'Score ≥ 70' },
  { value: 80, label: 'Score ≥ 80' },
]

const ROOMS_OPTIONS = [
  { value: null, label: 'Zi. egal' },
  { value: 2, label: '2+' },
  { value: 3, label: '3+' },
  { value: 4, label: '4+' },
  { value: 5, label: '5+' },
]

interface Props { sources: Source[] }

export function FilterBar({ sources }: Props) {
  const { filter, setFilter } = useUIStore()

  return (
    <div className="sticky top-0 z-20 bg-[--bg] border-b border-[--border] px-6 py-3 space-y-2">
      {/* Row 1: Status chips + Sort */}
      <div className="flex items-center gap-2 flex-wrap">
        {STATUS_OPTIONS.map(opt => (
          <button
            key={opt.value}
            onClick={() => setFilter({ status: opt.value })}
            className={cn(
              'px-3 py-1 rounded-full text-sm font-medium border transition-colors',
              filter.status === opt.value
                ? 'bg-[--accent] text-white border-[--accent]'
                : 'border-[--border] text-[--muted] hover:border-[--accent] hover:text-[--accent]'
            )}
          >
            {opt.label}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-1.5 text-[--muted]">
          <ArrowsDownUp size={14} weight="bold" />
          <select
            value={filter.sort}
            onChange={e => setFilter({ sort: e.target.value as typeof filter.sort })}
            className="text-sm bg-transparent border-none outline-none text-[--fg] cursor-pointer"
          >
            {SORT_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>
      </div>

      {/* Row 2: Numeric filters */}
      <div className="flex items-center gap-3 flex-wrap text-sm">
        {/* Price range */}
        <div className="flex items-center gap-1">
          <span className="text-[--muted] text-xs">€</span>
          <input
            type="number" placeholder="Min" step={50000}
            value={filter.priceMin ?? ''}
            onChange={e => setFilter({ priceMin: e.target.value ? Number(e.target.value) : null })}
            className="w-24 px-2 py-1 rounded border border-[--border] bg-white font-mono text-xs focus:outline-none focus:border-[--accent]"
          />
          <span className="text-[--muted]">–</span>
          <input
            type="number" placeholder="Max" step={50000}
            value={filter.priceMax ?? ''}
            onChange={e => setFilter({ priceMax: e.target.value ? Number(e.target.value) : null })}
            className="w-24 px-2 py-1 rounded border border-[--border] bg-white font-mono text-xs focus:outline-none focus:border-[--accent]"
          />
        </div>

        <div className="w-px h-4 bg-[--border]" />

        {/* m² range */}
        <div className="flex items-center gap-1">
          <span className="text-[--muted] text-xs">m²</span>
          <input
            type="number" placeholder="Min"
            value={filter.qmMin ?? ''}
            onChange={e => setFilter({ qmMin: e.target.value ? Number(e.target.value) : null })}
            className="w-16 px-2 py-1 rounded border border-[--border] bg-white font-mono text-xs focus:outline-none focus:border-[--accent]"
          />
          <span className="text-[--muted]">–</span>
          <input
            type="number" placeholder="Max"
            value={filter.qmMax ?? ''}
            onChange={e => setFilter({ qmMax: e.target.value ? Number(e.target.value) : null })}
            className="w-16 px-2 py-1 rounded border border-[--border] bg-white font-mono text-xs focus:outline-none focus:border-[--accent]"
          />
        </div>

        <div className="w-px h-4 bg-[--border]" />

        {/* Rooms */}
        <select
          value={filter.roomsMin ?? ''}
          onChange={e => setFilter({ roomsMin: e.target.value ? Number(e.target.value) : null })}
          className="px-2 py-1 rounded border border-[--border] bg-white text-xs focus:outline-none focus:border-[--accent] text-[--fg]"
        >
          {ROOMS_OPTIONS.map(o => <option key={o.value ?? 'null'} value={o.value ?? ''}>{o.label}</option>)}
        </select>

        {/* Score */}
        <select
          value={filter.minScore}
          onChange={e => setFilter({ minScore: Number(e.target.value) })}
          className="px-2 py-1 rounded border border-[--border] bg-white text-xs focus:outline-none focus:border-[--accent] text-[--fg]"
        >
          {SCORE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>

        {/* Portal */}
        {sources.length > 0 && (
          <select
            value={filter.portal}
            onChange={e => setFilter({ portal: e.target.value })}
            className="px-2 py-1 rounded border border-[--border] bg-white text-xs focus:outline-none focus:border-[--accent] text-[--fg]"
          >
            <option value="">Alle Portale</option>
            {sources.map(s => <option key={s.id} value={s.name}>{s.name}</option>)}
          </select>
        )}

        {/* Reset */}
        {(filter.priceMin || filter.priceMax || filter.qmMin || filter.qmMax || filter.roomsMin || filter.status || filter.portal || filter.minScore) && (
          <button
            onClick={() => setFilter({ priceMin: null, priceMax: null, qmMin: null, qmMax: null, roomsMin: null, status: '', portal: '', minScore: 0 })}
            className="ml-auto text-xs text-[--muted] hover:text-[--accent] flex items-center gap-1"
          >
            <Funnel size={12} /> Filter löschen
          </button>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: No errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/listings/FilterBar.tsx frontend/src/store/ui.ts frontend/src/types.ts frontend/src/api/listings.ts
git commit -m "feat(filter): Preis/m²/Zimmer-Filter + Sortierung in FilterBar"
```

---

## Task 4: Frontend — Suchprofil-Tab vervollständigen (ohne Karte)

**Files:**
- Modify: `frontend/src/components/settings/SearchProfileTab.tsx`

Add Baujahr-Slider and Objekttypen-Checkboxen. The Leaflet map picker comes in Task 6 (after leaflet is installed). This task completes the non-map parts.

- [ ] **Step 1: Read the current `SearchProfileTab.tsx`**

Read file to understand existing state/API calls before editing.

- [ ] **Step 2: Add Baujahr slider + Objekttypen checkboxes**

The `AppSettings` type already has `year_built_min` and `property_types` (as string or list). Extend the form:

```tsx
// Baujahr
<div>
  <label className="block text-xs font-medium text-[--muted] mb-1">Baujahr ab</label>
  <div className="flex items-center gap-3">
    <input
      type="range" min={1900} max={2030} step={5}
      value={draft.year_built_min ?? 1980}
      onChange={e => setDraft(d => ({ ...d, year_built_min: Number(e.target.value) }))}
      className="flex-1 accent-[--accent]"
    />
    <span className="font-mono text-sm w-12 text-right">{draft.year_built_min ?? 1980}</span>
  </div>
</div>

// Objekttypen
const PROPERTY_TYPES = ['Wohnung', 'Haus', 'Doppelhaushälfte', 'Reihenhaus', 'Grundstück']
<div>
  <label className="block text-xs font-medium text-[--muted] mb-2">Objekttypen</label>
  <div className="flex flex-wrap gap-2">
    {PROPERTY_TYPES.map(pt => {
      const active = (draft.property_types ?? []).includes(pt)
      return (
        <button
          key={pt}
          type="button"
          onClick={() => setDraft(d => ({
            ...d,
            property_types: active
              ? (d.property_types ?? []).filter(t => t !== pt)
              : [...(d.property_types ?? []), pt],
          }))}
          className={cn(
            'px-3 py-1 rounded-full text-xs border transition-colors',
            active ? 'bg-[--accent] text-white border-[--accent]' : 'border-[--border] text-[--muted] hover:border-[--accent]'
          )}
        >
          {pt}
        </button>
      )
    })}
  </div>
</div>
```

Make sure `AppSettings` type in `types.ts` has:
- `year_built_min: number | null`
- `property_types: string[]`

If missing, add them and extend `app/web/api/settings.py` with the same fields (both in the GET response and PATCH handler).

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/settings/SearchProfileTab.tsx frontend/src/types.ts
git commit -m "feat(settings): Baujahr-Slider + Objekttypen-Checkboxen im Suchprofil"
```

---

## Task 5: Leaflet installieren + Minimap im Detailpanel

**Files:**
- New: `frontend/src/components/map/ListingMiniMap.tsx`
- Modify: `frontend/src/components/listings/DetailPanel.tsx`
- Modify: `frontend/package.json` (leaflet + react-leaflet + types)

**Important notes about Leaflet in React:**
- Leaflet requires `import 'leaflet/dist/leaflet.css'` — add to `frontend/src/index.css` via `@import`
- Default marker icons break in Vite — must fix with: `import L from 'leaflet'; delete (L.Icon.Default.prototype as any)._getIconUrl; L.Icon.Default.mergeOptions({ iconRetinaUrl, iconUrl, shadowUrl })`
- The `MapContainer` and all Leaflet components must be in a `'use client'`-equivalent — they're only safe in browser context. Wrap with a `useEffect`/`useState(false)` mount guard or use dynamic import.
- `MapContainer` must have explicit height (not `h-full` without a parent height).

- [ ] **Step 1: Install leaflet + react-leaflet**

```bash
cd frontend && npm install leaflet react-leaflet
npm install -D @types/leaflet
```

- [ ] **Step 2: Add Leaflet CSS to `frontend/src/index.css`**

```css
@import 'leaflet/dist/leaflet.css';
```

Add this BEFORE the Tailwind directives to ensure specificity is correct.

- [ ] **Step 3: Create `frontend/src/components/map/ListingMiniMap.tsx`**

```tsx
import { useEffect, useState } from 'react'

interface Props {
  lat: number
  lon: number
  zoom?: number
  className?: string
}

export function ListingMiniMap({ lat, lon, zoom = 14, className }: Props) {
  const [mounted, setMounted] = useState(false)
  useEffect(() => { setMounted(true) }, [])

  if (!mounted) return <div className={className} style={{ background: 'oklch(95% 0.006 120)' }} />

  // Dynamic import to avoid SSR issues and ensure Leaflet only runs in browser
  return <LeafletMap lat={lat} lon={lon} zoom={zoom} className={className} />
}

function LeafletMap({ lat, lon, zoom, className }: Required<Props>) {
  const { MapContainer, TileLayer, Marker } = require('react-leaflet')
  const L = require('leaflet')

  // Fix default marker icons in Vite
  useEffect(() => {
    delete (L.Icon.Default.prototype as any)._getIconUrl
    L.Icon.Default.mergeOptions({
      iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
      iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
      shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
    })
  }, [])

  return (
    <MapContainer
      center={[lat, lon]}
      zoom={zoom}
      scrollWheelZoom={false}
      dragging={false}
      zoomControl={false}
      className={className}
      style={{ height: '100%', width: '100%' }}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <Marker position={[lat, lon]} />
    </MapContainer>
  )
}
```

Note: The `require()` inside the component is intentional to avoid Leaflet loading before the browser check. An alternative is `React.lazy` + `Suspense`, but the mount guard + require pattern is simpler for this use case.

Actually, a cleaner approach without require():

```tsx
import { useEffect, useRef } from 'react'
import L from 'leaflet'

interface Props {
  lat: number
  lon: number
  zoom?: number
  height?: string
}

export function ListingMiniMap({ lat, lon, zoom = 14, height = '160px' }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    // Fix default icons
    delete (L.Icon.Default.prototype as any)._getIconUrl
    L.Icon.Default.mergeOptions({
      iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
      iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
      shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
    })

    const map = L.map(containerRef.current, {
      center: [lat, lon],
      zoom,
      scrollWheelZoom: false,
      dragging: false,
      zoomControl: false,
    })

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>',
    }).addTo(map)

    L.marker([lat, lon]).addTo(map)
    mapRef.current = map

    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [lat, lon, zoom])

  return (
    <div
      ref={containerRef}
      className="rounded-lg overflow-hidden border border-[--border]"
      style={{ height }}
    />
  )
}
```

Use the imperative L.map() approach — it's the most reliable with Vite and avoids all react-leaflet provider issues.

- [ ] **Step 4: Add minimap to `DetailPanel.tsx`**

After the address line, add:

```tsx
{listing.lat && listing.lon && (
  <ListingMiniMap lat={listing.lat} lon={listing.lon} height="160px" />
)}
```

Import: `import { ListingMiniMap } from '../map/ListingMiniMap'`

- [ ] **Step 5: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 6: Check browser — open a listing with coordinates, minimap should show**

```bash
cd frontend && npm run dev
```

Open http://localhost:5173, click a listing that has lat/lon — minimap should appear in the detail panel.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/map/ frontend/src/components/listings/DetailPanel.tsx frontend/src/index.css frontend/package.json frontend/package-lock.json
git commit -m "feat(map): Leaflet-Minimap im Detailpanel für Listings mit Koordinaten"
```

---

## Task 6: Karten-Toggle in der Listings-Ansicht

**Files:**
- New: `frontend/src/components/map/ListingsMap.tsx`
- Modify: `frontend/src/pages/ListingsPage.tsx`
- Modify: `frontend/src/store/ui.ts`

Toggle between grid view and full map view. All filtered listings appear as color-coded pins (status-based). Clicking a pin opens the DetailPanel.

- [ ] **Step 1: Add `viewMode` to UI store**

In `frontend/src/store/ui.ts`, add:

```typescript
viewMode: 'grid' | 'map'
setViewMode: (mode: 'grid' | 'map') => void
```

Default: `'grid'`.

- [ ] **Step 2: Create `frontend/src/components/map/ListingsMap.tsx`**

Status-color mapping:
```typescript
const STATUS_COLORS: Record<string, string> = {
  neu: '#22c55e',          // green
  interessant: '#22c55e',
  vielleicht: '#f59e0b',   // amber
  gesehen: '#94a3b8',      // slate
  abgelehnt: '#ef4444',    // red
}
```

Use custom circle markers (L.circleMarker) instead of default icons — cleaner at high density:

```typescript
L.circleMarker([lat, lon], {
  radius: 8,
  fillColor: STATUS_COLORS[listing.status] ?? '#94a3b8',
  color: '#fff',
  weight: 2,
  fillOpacity: 0.9,
}).bindPopup(`<b>${listing.title}</b><br>${formatPrice(listing.price_eur)}`)
 .on('click', () => onListingClick(listing.id))
 .addTo(map)
```

Center on Tutzing (lat: 47.905, lon: 11.285) by default. If listings have coordinates, fit bounds to them.

Full component:

```tsx
import { useEffect, useRef } from 'react'
import L from 'leaflet'
import { Listing } from '../../types'
import { formatPrice } from '../../lib/formatters'

const STATUS_COLORS: Record<string, string> = {
  neu: '#22c55e',
  interessant: '#22c55e',
  vielleicht: '#f59e0b',
  gesehen: '#94a3b8',
  abgelehnt: '#ef4444',
}

interface Props {
  listings: Listing[]
  selectedId: number | null
  onListingClick: (id: number) => void
}

export function ListingsMap({ listings, selectedId, onListingClick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const markersRef = useRef<L.CircleMarker[]>([])

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const map = L.map(containerRef.current, {
      center: [47.905, 11.285],
      zoom: 12,
      zoomControl: true,
    })
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>',
    }).addTo(map)
    mapRef.current = map
    return () => { map.remove(); mapRef.current = null }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    markersRef.current.forEach(m => m.remove())
    markersRef.current = []
    const withCoords = listings.filter(l => l.lat && l.lon)
    withCoords.forEach(l => {
      const marker = L.circleMarker([l.lat!, l.lon!], {
        radius: selectedId === l.id ? 12 : 8,
        fillColor: STATUS_COLORS[l.status] ?? '#94a3b8',
        color: '#fff',
        weight: 2,
        fillOpacity: 0.9,
      })
        .bindPopup(`<b style="font-family:sans-serif;font-size:13px">${l.title}</b><br><span style="font-family:monospace">${formatPrice(l.price_eur)}</span>`)
        .on('click', () => onListingClick(l.id))
      marker.addTo(map)
      markersRef.current.push(marker)
    })
    if (withCoords.length > 0) {
      const bounds = L.latLngBounds(withCoords.map(l => [l.lat!, l.lon!]))
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 })
    }
  }, [listings, selectedId, onListingClick])

  return <div ref={containerRef} className="w-full h-full" />
}
```

- [ ] **Step 3: Add toggle button + map view to `ListingsPage.tsx`**

Import `ListingsMap` and `viewMode` from store. Add a toggle button (SquaresFour / MapPin icons) in the page header next to the count.

When `viewMode === 'map'`:
- Render `<div className="flex-1 relative"><ListingsMap .../></div>` instead of the card grid
- DetailPanel still works — clicking a pin sets `selectedListingId`

When `viewMode === 'grid'`: existing grid + AnimatePresence behavior.

Listings without coordinates (when in map view): show a small sidebar list below the toggle area with a "X Objekte ohne Koordinaten" note.

- [ ] **Step 4: Verify TypeScript + browser**

```bash
cd frontend && npx tsc --noEmit && npm run dev
```

Test: toggle to map, click a pin, verify DetailPanel opens.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/map/ListingsMap.tsx frontend/src/pages/ListingsPage.tsx frontend/src/store/ui.ts
git commit -m "feat(map): Karten-Toggle in Listings-Ansicht mit Status-Pins"
```

---

## Task 7: Leaflet-Karte + Nominatim im Suchprofil-Tab

**Files:**
- New: `frontend/src/components/map/LocationPicker.tsx`
- Modify: `frontend/src/components/settings/SearchProfileTab.tsx`

Replace the numerical radius-slider-only view with an interactive map: draggable center pin + radius circle overlay. Nominatim search with 1s debounce.

- [ ] **Step 1: Create `frontend/src/components/map/LocationPicker.tsx`**

```tsx
import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import { useDebounce } from '../../hooks/useDebounce'

interface Props {
  lat: number
  lon: number
  radiusKm: number
  onChange: (lat: number, lon: number, radiusKm: number) => void
}

export function LocationPicker({ lat, lon, radiusKm, onChange }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const markerRef = useRef<L.Marker | null>(null)
  const circleRef = useRef<L.Circle | null>(null)
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounce(search, 1000)

  // Initialize map
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const map = L.map(containerRef.current, { center: [lat, lon], zoom: 11 })
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OSM',
    }).addTo(map)

    // Fix icons
    delete (L.Icon.Default.prototype as any)._getIconUrl
    L.Icon.Default.mergeOptions({
      iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
      iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
      shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
    })

    const marker = L.marker([lat, lon], { draggable: true }).addTo(map)
    const circle = L.circle([lat, lon], { radius: radiusKm * 1000, color: 'oklch(45% 0.13 150)', fillOpacity: 0.08, weight: 2 }).addTo(map)

    marker.on('dragend', () => {
      const pos = marker.getLatLng()
      circle.setLatLng(pos)
      onChange(pos.lat, pos.lng, radiusKm)
    })

    mapRef.current = map
    markerRef.current = marker
    circleRef.current = circle

    return () => { map.remove(); mapRef.current = null }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Update circle radius when prop changes
  useEffect(() => {
    circleRef.current?.setRadius(radiusKm * 1000)
  }, [radiusKm])

  // Nominatim search (1s debounce to respect rate limit)
  useEffect(() => {
    if (!debouncedSearch || debouncedSearch.length < 3) return
    fetch(`https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(debouncedSearch)}&format=json&limit=1`, {
      headers: { 'Accept-Language': 'de', 'User-Agent': 'immo-radar/1.0 philipp.herrlich@googlemail.com' },
    })
      .then(r => r.json())
      .then(results => {
        if (!results[0]) return
        const newLat = parseFloat(results[0].lat)
        const newLon = parseFloat(results[0].lon)
        const pos: L.LatLngExpression = [newLat, newLon]
        mapRef.current?.setView(pos, 12)
        markerRef.current?.setLatLng(pos)
        circleRef.current?.setLatLng(pos)
        onChange(newLat, newLon, radiusKm)
      })
      .catch(() => {}) // Nominatim failures are silent — user can retry
  }, [debouncedSearch]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-2">
      <input
        type="text"
        placeholder="Ort suchen (z.B. Tutzing, Starnberg…)"
        value={search}
        onChange={e => setSearch(e.target.value)}
        className="w-full px-3 py-2 rounded-lg border border-[--border] text-sm focus:outline-none focus:border-[--accent]"
      />
      <div ref={containerRef} className="rounded-lg overflow-hidden border border-[--border]" style={{ height: '280px' }} />
    </div>
  )
}
```

- [ ] **Step 2: Create `frontend/src/hooks/useDebounce.ts`** (if it doesn't exist)

```typescript
import { useState, useEffect } from 'react'

export function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}
```

- [ ] **Step 3: Integrate LocationPicker into `SearchProfileTab.tsx`**

Replace the radius-slider-only block with:

```tsx
<LocationPicker
  lat={draft.center_lat ?? 47.905}
  lon={draft.center_lon ?? 11.285}
  radiusKm={draft.radius_km ?? 5}
  onChange={(lat, lon, radiusKm) => setDraft(d => ({ ...d, center_lat: lat, center_lon: lon, radius_km: radiusKm }))}
/>
{/* Radius slider below the map as a fine-tune control */}
<div className="flex items-center gap-3 mt-2">
  <span className="text-xs text-[--muted]">Radius:</span>
  <input
    type="range" min={1} max={25} step={1}
    value={draft.radius_km ?? 5}
    onChange={e => {
      const km = Number(e.target.value)
      setDraft(d => ({ ...d, radius_km: km }))
    }}
    className="flex-1 accent-[--accent]"
  />
  <span className="font-mono text-sm w-12">{draft.radius_km ?? 5} km</span>
</div>
```

Make sure `AppSettings` type has `center_lat: number | null`, `center_lon: number | null` — add if missing.

- [ ] **Step 4: Verify TypeScript + browser**

```bash
cd frontend && npx tsc --noEmit && npm run dev
```

Test: open Settings → Suchprofil tab. Map should show. Drag marker → coordinates update. Type "Starnberg" in search → map moves there after ~1s.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/map/LocationPicker.tsx frontend/src/hooks/useDebounce.ts frontend/src/components/settings/SearchProfileTab.tsx
git commit -m "feat(settings): Leaflet-Karte mit Nominatim-Suche im Suchprofil-Tab"
```

---

## Task 8: Build + Deploy

**Files:**
- No new files — this task deploys everything built so far

- [ ] **Step 1: Run full test suite**

```bash
source .venv/bin/activate && python -m pytest tests/ -q
```

Expected: All pass.

- [ ] **Step 2: Frontend build**

```bash
cd frontend && npm run build
```

Expected: Built in `app/web/static/dist/`. Check for TypeScript errors in build output.

- [ ] **Step 3: Deploy to VPS**

```bash
bash scripts/deploy.sh
```

The deploy script will:
1. rsync all files to VPS
2. `docker compose up -d --build` (rebuilds image with new frontend)
3. Add `immo.herrlich.dev` to Caddy if not present, reload Caddy

- [ ] **Step 4: Verify live**

Open `https://immo.herrlich.dev` — should prompt for basicauth (admin / tutzing2026!), then load the React SPA.

Test:
- Filter: price range, m², rooms, sort
- Detail panel: minimap visible for listings with coordinates
- Map toggle: pins on OSM map, click → detail panel
- Settings → Suchprofil: Leaflet map + Nominatim search + Baujahr + Objekttypen

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: deploy-ready — immo.herrlich.dev, Filter, Leaflet Maps"
```
