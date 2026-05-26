# immo-radar Frontend SPA — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** React 18 + Vite SPA that replaces the Jinja2 dashboard with a proper UI — listings with filter bar + detail panel, settings management, and system status screen.

**Architecture:** React SPA served as static files from FastAPI (`app/web/static/dist/`). TanStack Query for server state, Zustand for UI state. All API calls go to `/api/*` on the same origin (Vite proxy in dev). The existing Jinja2 templates are superseded by the SPA build but left intact as fallback.

**Tech Stack:** React 18, Vite 5, TypeScript 5, Tailwind CSS v3, TanStack Query v5, Zustand v4, @phosphor-icons/react v2, Framer Motion v11, clsx, tailwind-merge

---

## File Structure

```
frontend/                          ← React project root
  package.json
  vite.config.ts
  tsconfig.json
  tsconfig.node.json
  tailwind.config.ts
  postcss.config.js
  index.html
  src/
    main.tsx
    App.tsx
    types.ts                       ← All TS interfaces (Listing, Source, Settings, SystemStatus)
    api/
      client.ts                    ← Base fetch wrapper with error handling
      listings.ts
      settings.ts
      sources.ts
      system.ts
      telegram.ts
    lib/
      cn.ts                        ← clsx + tailwind-merge helper
      formatters.ts                ← formatPrice, formatSqm, formatDays, formatTimeAgo
    hooks/
      useLastVisit.ts              ← localStorage timestamp → "new since last visit" set
    store/
      ui.ts                        ← Zustand: selectedListingId, filterState
    components/
      layout/
        Sidebar.tsx
        Layout.tsx
      listings/
        StatusChip.tsx
        ScoreBadge.tsx
        ListingCard.tsx
        FilterBar.tsx
        DetailPanel.tsx
      settings/
        SearchProfileTab.tsx
        NotificationsTab.tsx
        MechanicsTab.tsx
        SourcesTab.tsx
      ui/
        Toggle.tsx
    pages/
      ListingsPage.tsx
      SettingsPage.tsx
      SystemPage.tsx

app/web/api/system.py              ← extend: /fetch-runs + /crawl/trigger
app/web/server.py                  ← serve dist/index.html for all non-API routes
Dockerfile                         ← add Node.js + npm run build step
```

---

### Task 1: Backend — Expand ListingOut + FetchRuns + CrawlTrigger

**Files:**
- Modify: `app/web/api/listings.py`
- Modify: `app/web/api/system.py`

The current `ListingOut` is missing fields needed for the detail panel (images, risk_flags, property_type, city, ortsteil, lat, lon, year_built, hausgeld_eur, energie_kwh, energie_class, is_active). Add them.

- [ ] **Step 1: Expand ListingOut in app/web/api/listings.py**

Replace the `ListingOut` class with the full schema:

```python
class ListingOut(BaseModel):
    id: int
    source_id: str
    source: str
    title: str
    price_eur: int | None
    qm: float | None
    rooms: float | None
    year_built: int | None
    property_type: str | None
    address: str | None
    city: str | None
    ortsteil: str | None
    plz: str | None
    lat: float | None
    lon: float | None
    hausgeld_eur: int | None
    energie_kwh: float | None
    energie_class: str | None
    images: list[str]
    url: str
    lage_score: int | None
    ai_score: int | None
    ai_reasoning: str | None
    risk_flags: list[str]
    status: str
    notes: str | None
    first_seen_at: datetime
    last_seen_at: datetime
    is_active: bool
    enrich_attempts: int

    @computed_field
    @property
    def price_per_sqm(self) -> float | None:
        if self.price_eur and self.qm and self.qm > 0:
            return round(self.price_eur / self.qm, 0)
        return None

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Add FetchRun endpoint in app/web/api/system.py**

After the existing `get_status` function, add:

```python
class FetchRunOut(BaseModel):
    id: int
    source: str
    started_at: datetime
    finished_at: Optional[datetime]
    listings_found: int
    listings_new: int
    error: Optional[str]

    model_config = {"from_attributes": True}


@router.get("/fetch-runs", response_model=list[FetchRunOut])
def get_fetch_runs():
    with db_module.SessionLocal() as session:
        from sqlalchemy import desc
        runs = (
            session.query(db_module.FetchRun)
            .order_by(desc(db_module.FetchRun.started_at))
            .limit(50)
            .all()
        )
        return [FetchRunOut.model_validate(r) for r in runs]
```

Add `from typing import Optional` at the top if not present.
Also add `db_module.FetchRun` — verify `FetchRun` is importable from `app.db`.

- [ ] **Step 3: Add crawl trigger endpoint in app/web/api/system.py**

```python
@router.post("/crawl/trigger")
async def trigger_crawl(request: Request):
    """Trigger an immediate poll_and_notify run."""
    from app.scheduler import poll_and_notify
    import asyncio
    asyncio.create_task(poll_and_notify())
    return {"status": "triggered"}
```

- [ ] **Step 4: Run existing tests**

```bash
cd /Users/philippherrlich/Code/immo-radar/.worktrees/frontend-spa
source .venv/bin/activate
python -m pytest tests/ -v
```

All 36 tests must still pass (the expanded ListingOut may cause test_api_listings.py changes — update seed_listing and assertions there if needed).

- [ ] **Step 5: Commit**

```bash
git add app/web/api/listings.py app/web/api/system.py
git commit -m "feat(api): ListingOut erweitert + FetchRuns + CrawlTrigger Endpoints"
```

---

### Task 2: Vite + React + TypeScript Project Setup

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/postcss.config.js`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`

- [ ] **Step 1: Create frontend/package.json**

```json
{
  "name": "immo-radar-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.24.0",
    "@tanstack/react-query": "^5.51.0",
    "zustand": "^4.5.4",
    "@phosphor-icons/react": "^2.1.7",
    "framer-motion": "^11.3.0",
    "clsx": "^2.1.1",
    "tailwind-merge": "^2.4.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "autoprefixer": "^10.4.19",
    "postcss": "^8.4.40",
    "tailwindcss": "^3.4.7",
    "typescript": "^5.5.3",
    "vite": "^5.3.4"
  }
}
```

- [ ] **Step 2: Create frontend/vite.config.ts**

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: '../app/web/static/dist',
    emptyOutDir: true,
  },
})
```

- [ ] **Step 3: Create frontend/tsconfig.json**

```json
{
  "files": [],
  "references": [
    { "path": "./tsconfig.app.json" },
    { "path": "./tsconfig.node.json" }
  ]
}
```

Create `frontend/tsconfig.app.json`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"]
}
```

Create `frontend/tsconfig.node.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2023"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "noEmit": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 4: Create frontend/tailwind.config.ts**

```typescript
import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        display: ['"Bricolage Grotesque"', 'sans-serif'],
        body: ['"Schibsted Grotesk"', 'sans-serif'],
        mono: ['"Azeret Mono"', 'monospace'],
      },
      colors: {
        bg: 'oklch(97% 0.006 120)',
        fg: 'oklch(18% 0.010 240)',
        accent: 'oklch(45% 0.130 150)',
        'accent-muted': 'oklch(90% 0.040 150)',
        border: 'oklch(87% 0.010 120)',
        muted: 'oklch(60% 0.008 240)',
      },
    },
  },
  plugins: [],
} satisfies Config
```

- [ ] **Step 5: Create frontend/postcss.config.js**

```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
```

- [ ] **Step 6: Create frontend/index.html**

```html
<!doctype html>
<html lang="de">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>immo-radar · Tutzing</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,600;12..96,700&family=Schibsted+Grotesk:wght@400;500&family=Azeret+Mono:wght@400;500&display=swap"
      rel="stylesheet"
    />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 7: Create frontend/src/main.tsx**

```typescript
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import App from './App'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
```

- [ ] **Step 8: Create frontend/src/index.css**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --bg: oklch(97% 0.006 120);
  --fg: oklch(18% 0.010 240);
  --accent: oklch(45% 0.130 150);
  --accent-muted: oklch(90% 0.040 150);
  --border: oklch(87% 0.010 120);
  --muted: oklch(60% 0.008 240);
  --status-new: oklch(58% 0.160 145);
  --status-maybe: oklch(72% 0.150 75);
  --status-rejected: oklch(52% 0.180 25);
  --status-seen: oklch(60% 0.008 240);
  --score-high: oklch(55% 0.160 145);
  --score-mid: oklch(70% 0.150 75);
  --score-low: oklch(55% 0.160 25);
}

body {
  background-color: var(--bg);
  color: var(--fg);
  font-family: 'Schibsted Grotesk', sans-serif;
  font-size: 16px;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}

h1, h2, h3 {
  font-family: 'Bricolage Grotesque', sans-serif;
}

.font-price {
  font-family: 'Azeret Mono', monospace;
  font-variant-numeric: tabular-nums;
}
```

- [ ] **Step 9: Create placeholder App.tsx**

```typescript
export default function App() {
  return <div className="p-8 font-display text-4xl">immo-radar</div>
}
```

- [ ] **Step 10: Install dependencies**

```bash
cd /Users/philippherrlich/Code/immo-radar/.worktrees/frontend-spa/frontend
npm install
```

- [ ] **Step 11: Verify TypeScript compiles**

```bash
npm run typecheck
```

Expected: no errors.

- [ ] **Step 12: Verify build works**

```bash
npm run build
```

Expected: creates `../app/web/static/dist/index.html` (relative to frontend/).

- [ ] **Step 13: Commit**

```bash
cd ..  # back to worktree root
git add frontend/
git commit -m "feat(frontend): Vite + React + TS Projektstruktur"
```

---

### Task 3: TypeScript Types + API Client

**Files:**
- Create: `frontend/src/types.ts`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/listings.ts`
- Create: `frontend/src/api/settings.ts`
- Create: `frontend/src/api/sources.ts`
- Create: `frontend/src/api/system.ts`
- Create: `frontend/src/api/telegram.ts`

- [ ] **Step 1: Create frontend/src/types.ts**

```typescript
export interface Listing {
  id: number
  source_id: string
  source: string
  title: string
  price_eur: number | null
  qm: number | null
  rooms: number | null
  year_built: number | null
  property_type: string | null
  address: string | null
  city: string | null
  ortsteil: string | null
  plz: string | null
  lat: number | null
  lon: number | null
  hausgeld_eur: number | null
  energie_kwh: number | null
  energie_class: string | null
  images: string[]
  url: string
  lage_score: number | null
  ai_score: number | null
  ai_reasoning: string | null
  risk_flags: string[]
  status: string
  notes: string | null
  first_seen_at: string
  last_seen_at: string
  is_active: boolean
  enrich_attempts: number
  price_per_sqm: number | null
}

export interface Source {
  id: number
  name: string
  display_name: string
  enabled: boolean
  last_run: string | null
  listing_count: number
}

export interface AppSettings {
  poll_interval_minutes: number
  detail_fetch_interval_minutes: number
  search_radius_km: number
  price_min: number
  price_max: number
  qm_min: number
  qm_max: number
  rooms_min: number
  year_built_min: number
  property_types: string
  score_threshold: number
}

export interface JobInfo {
  id: string
  next_run: string | null
}

export interface SystemStatus {
  scheduler_running: boolean
  jobs: JobInfo[]
  listing_counts: Record<string, number>
}

export interface FetchRun {
  id: number
  source: string
  started_at: string
  finished_at: string | null
  listings_found: number
  listings_new: number
  error: string | null
}

export interface ListingsFilter {
  status: string
  source: string
  min_score: number | null
}

export type ViewMode = 'grid'

export type ListingStatus = 'new' | 'interessant' | 'vielleicht' | 'gesehen' | 'abgelehnt'

export const STATUS_LABELS: Record<string, string> = {
  new: 'Neu',
  interessant: 'Interessant',
  vielleicht: 'Vielleicht',
  gesehen: 'Gesehen',
  abgelehnt: 'Abgelehnt',
}
```

- [ ] **Step 2: Create frontend/src/api/client.ts**

```typescript
async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(path, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`${res.status}: ${text}`)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
}
```

- [ ] **Step 3: Create frontend/src/api/listings.ts**

```typescript
import { api } from './client'
import type { Listing } from '../types'

export interface ListingsQuery {
  status?: string
  portal?: string
  min_score?: number
}

export function fetchListings(query: ListingsQuery = {}): Promise<Listing[]> {
  const params = new URLSearchParams()
  if (query.status) params.set('status', query.status)
  if (query.portal) params.set('portal', query.portal)
  if (query.min_score != null) params.set('min_score', String(query.min_score))
  const qs = params.toString()
  return api.get<Listing[]>(`/api/listings/${qs ? '?' + qs : ''}`)
}

export function fetchListing(id: number): Promise<Listing> {
  return api.get<Listing>(`/api/listings/${id}`)
}

export function patchListing(
  id: number,
  body: { status?: string; notes?: string },
): Promise<Listing> {
  return api.patch<Listing>(`/api/listings/${id}`, body)
}
```

- [ ] **Step 4: Create frontend/src/api/settings.ts**

```typescript
import { api } from './client'
import type { AppSettings } from '../types'

export function fetchSettings(): Promise<{ settings: AppSettings }> {
  return api.get('/api/settings/')
}

export function patchSetting(key: string, value: unknown): Promise<{ settings: AppSettings }> {
  return api.patch('/api/settings/', { key, value })
}
```

- [ ] **Step 5: Create frontend/src/api/sources.ts**

```typescript
import { api } from './client'
import type { Source } from '../types'

export function fetchSources(): Promise<Source[]> {
  return api.get('/api/sources/')
}

export function patchSource(
  id: number,
  body: { enabled?: boolean; display_name?: string },
): Promise<Source> {
  return api.patch(`/api/sources/${id}`, body)
}
```

- [ ] **Step 6: Create frontend/src/api/system.ts**

```typescript
import { api } from './client'
import type { SystemStatus, FetchRun } from '../types'

export function fetchSystemStatus(): Promise<SystemStatus> {
  return api.get('/api/system/status')
}

export function fetchFetchRuns(): Promise<FetchRun[]> {
  return api.get('/api/system/fetch-runs')
}

export function triggerCrawl(): Promise<{ status: string }> {
  return api.post('/api/system/crawl/trigger')
}
```

- [ ] **Step 7: Create frontend/src/api/telegram.ts**

```typescript
import { api } from './client'

export function testTelegram(): Promise<{ success: boolean; message: string }> {
  return api.post('/api/telegram/test')
}
```

- [ ] **Step 8: Typecheck**

```bash
cd /Users/philippherrlich/Code/immo-radar/.worktrees/frontend-spa/frontend
npm run typecheck
```

Expected: no errors.

- [ ] **Step 9: Commit**

```bash
cd ..
git add frontend/src/types.ts frontend/src/api/
git commit -m "feat(frontend): TypeScript Typen + API Client Layer"
```

---

### Task 4: Utilities + Zustand Store

**Files:**
- Create: `frontend/src/lib/cn.ts`
- Create: `frontend/src/lib/formatters.ts`
- Create: `frontend/src/hooks/useLastVisit.ts`
- Create: `frontend/src/store/ui.ts`

- [ ] **Step 1: Create frontend/src/lib/cn.ts**

```typescript
import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
```

- [ ] **Step 2: Create frontend/src/lib/formatters.ts**

```typescript
export function formatPrice(eur: number | null): string {
  if (eur == null) return '–'
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
  }).format(eur)
}

export function formatPricePerSqm(ppsm: number | null): string {
  if (ppsm == null) return '–'
  return new Intl.NumberFormat('de-DE', {
    maximumFractionDigits: 0,
  }).format(ppsm) + ' €/m²'
}

export function formatSqm(qm: number | null): string {
  if (qm == null) return '–'
  return new Intl.NumberFormat('de-DE', { maximumFractionDigits: 0 }).format(qm) + ' m²'
}

export function formatRooms(rooms: number | null): string {
  if (rooms == null) return '–'
  return rooms % 1 === 0 ? `${rooms} Zi.` : `${rooms} Zi.`
}

export function formatDaysOnMarket(firstSeenAt: string): string {
  const days = Math.floor(
    (Date.now() - new Date(firstSeenAt).getTime()) / 86_400_000,
  )
  if (days === 0) return 'heute'
  if (days === 1) return 'seit gestern'
  return `seit ${days} Tagen`
}

export function formatTimeAgo(isoDate: string): string {
  const mins = Math.floor((Date.now() - new Date(isoDate).getTime()) / 60_000)
  if (mins < 1) return 'gerade eben'
  if (mins < 60) return `vor ${mins} Min.`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `vor ${hours} Std.`
  const days = Math.floor(hours / 24)
  return `vor ${days} Tagen`
}
```

- [ ] **Step 3: Create frontend/src/hooks/useLastVisit.ts**

```typescript
import { useEffect, useRef } from 'react'

const KEY = 'immo_radar_last_visit'

export function useLastVisit(): Date {
  const lastVisit = useRef<Date>(
    new Date(localStorage.getItem(KEY) ?? '1970-01-01'),
  )

  useEffect(() => {
    // Update timestamp when user leaves / after 5 seconds (treat as "visited")
    const timer = setTimeout(() => {
      localStorage.setItem(KEY, new Date().toISOString())
    }, 5_000)
    return () => clearTimeout(timer)
  }, [])

  return lastVisit.current
}

export function isNewSinceLastVisit(firstSeenAt: string, lastVisit: Date): boolean {
  return new Date(firstSeenAt) > lastVisit
}
```

- [ ] **Step 4: Create frontend/src/store/ui.ts**

```typescript
import { create } from 'zustand'
import type { ListingsFilter } from '../types'

interface UIState {
  selectedListingId: number | null
  setSelectedListingId: (id: number | null) => void

  filter: ListingsFilter
  setFilter: (patch: Partial<ListingsFilter>) => void
  resetFilter: () => void
}

const DEFAULT_FILTER: ListingsFilter = {
  status: '',
  source: '',
  min_score: null,
}

export const useUIStore = create<UIState>((set) => ({
  selectedListingId: null,
  setSelectedListingId: (id) => set({ selectedListingId: id }),

  filter: DEFAULT_FILTER,
  setFilter: (patch) =>
    set((s) => ({ filter: { ...s.filter, ...patch } })),
  resetFilter: () => set({ filter: DEFAULT_FILTER }),
}))
```

- [ ] **Step 5: Typecheck**

```bash
cd /Users/philippherrlich/Code/immo-radar/.worktrees/frontend-spa/frontend
npm run typecheck
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
cd ..
git add frontend/src/lib/ frontend/src/hooks/ frontend/src/store/
git commit -m "feat(frontend): Utilities, Formatter, useLastVisit, Zustand Store"
```

---

### Task 5: Layout — Sidebar + Router

**Files:**
- Create: `frontend/src/components/layout/Sidebar.tsx`
- Create: `frontend/src/components/layout/Layout.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create frontend/src/components/layout/Sidebar.tsx**

```typescript
import { NavLink } from 'react-router-dom'
import { House, Gear, ChartBar } from '@phosphor-icons/react'
import { cn } from '../../lib/cn'

const NAV = [
  { to: '/', icon: House, label: 'Listings' },
  { to: '/settings', icon: Gear, label: 'Einstellungen' },
  { to: '/system', icon: ChartBar, label: 'System' },
]

export function Sidebar() {
  return (
    <aside className="fixed left-0 top-0 h-full w-[220px] border-r flex flex-col py-8 px-4 z-20"
      style={{ borderColor: 'var(--border)', background: 'var(--bg)' }}>
      <div className="mb-10 px-2">
        <h1 className="font-display text-lg font-bold leading-tight" style={{ color: 'var(--fg)' }}>
          immo-radar
        </h1>
        <p className="text-xs mt-0.5" style={{ color: 'var(--muted)' }}>Tutzing · Starnberger See</p>
      </div>
      <nav className="flex flex-col gap-1">
        {NAV.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
                isActive
                  ? 'text-white'
                  : 'hover:bg-[var(--accent-muted)]',
              )
            }
            style={({ isActive }) =>
              isActive ? { background: 'var(--accent)', color: 'white' } : { color: 'var(--fg)' }
            }
          >
            <Icon size={18} weight="regular" />
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
```

- [ ] **Step 2: Create frontend/src/components/layout/Layout.tsx**

```typescript
import { Sidebar } from './Sidebar'

interface LayoutProps {
  children: React.ReactNode
}

export function Layout({ children }: LayoutProps) {
  return (
    <div className="min-h-[100dvh] flex" style={{ background: 'var(--bg)' }}>
      <Sidebar />
      <main className="ml-[220px] flex-1 min-w-0">
        {children}
      </main>
    </div>
  )
}
```

- [ ] **Step 3: Replace frontend/src/App.tsx with router setup**

```typescript
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Layout } from './components/layout/Layout'
import { ListingsPage } from './pages/ListingsPage'
import { SettingsPage } from './pages/SettingsPage'
import { SystemPage } from './pages/SystemPage'

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<ListingsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/system" element={<SystemPage />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}
```

- [ ] **Step 4: Create placeholder pages**

Create `frontend/src/pages/ListingsPage.tsx`:
```typescript
export function ListingsPage() {
  return <div className="p-8"><h1 className="font-display text-2xl font-bold">Listings</h1></div>
}
```

Create `frontend/src/pages/SettingsPage.tsx`:
```typescript
export function SettingsPage() {
  return <div className="p-8"><h1 className="font-display text-2xl font-bold">Einstellungen</h1></div>
}
```

Create `frontend/src/pages/SystemPage.tsx`:
```typescript
export function SystemPage() {
  return <div className="p-8"><h1 className="font-display text-2xl font-bold">System</h1></div>
}
```

- [ ] **Step 5: Typecheck + build**

```bash
cd /Users/philippherrlich/Code/immo-radar/.worktrees/frontend-spa/frontend
npm run typecheck
npm run build
```

Expected: no errors. Check that `../app/web/static/dist/index.html` was created.

- [ ] **Step 6: Commit**

```bash
cd ..
git add frontend/src/components/layout/ frontend/src/pages/ frontend/src/App.tsx
git commit -m "feat(frontend): Layout Sidebar + Router + Placeholder Pages"
```

---

### Task 6: Listing Atom Components (StatusChip, ScoreBadge, ListingCard)

**Files:**
- Create: `frontend/src/components/listings/StatusChip.tsx`
- Create: `frontend/src/components/listings/ScoreBadge.tsx`
- Create: `frontend/src/components/listings/ListingCard.tsx`

- [ ] **Step 1: Create frontend/src/components/listings/StatusChip.tsx**

```typescript
import { cn } from '../../lib/cn'
import { STATUS_LABELS } from '../../types'

const STATUS_STYLES: Record<string, string> = {
  new: 'bg-[oklch(92%_0.04_145)] text-[oklch(35%_0.13_145)]',
  interessant: 'bg-[oklch(92%_0.04_145)] text-[oklch(35%_0.13_145)]',
  vielleicht: 'bg-[oklch(94%_0.05_75)] text-[oklch(40%_0.12_75)]',
  gesehen: 'bg-[oklch(92%_0.005_240)] text-[oklch(40%_0.008_240)]',
  abgelehnt: 'bg-[oklch(94%_0.04_25)] text-[oklch(38%_0.14_25)]',
}

interface StatusChipProps {
  status: string
  className?: string
}

export function StatusChip({ status, className }: StatusChipProps) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.gesehen
  return (
    <span
      className={cn(
        'inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium',
        style,
        className,
      )}
    >
      {STATUS_LABELS[status] ?? status}
    </span>
  )
}
```

- [ ] **Step 2: Create frontend/src/components/listings/ScoreBadge.tsx**

```typescript
import { cn } from '../../lib/cn'

function scoreColor(score: number | null): string {
  if (score == null) return 'bg-[oklch(92%_0.005_240)] text-[oklch(40%_0.008_240)]'
  if (score >= 70) return 'bg-[oklch(88%_0.06_145)] text-[oklch(35%_0.13_145)]'
  if (score >= 50) return 'bg-[oklch(92%_0.06_75)] text-[oklch(38%_0.12_75)]'
  return 'bg-[oklch(93%_0.04_25)] text-[oklch(38%_0.14_25)]'
}

interface ScoreBadgeProps {
  score: number | null
  label?: string
  className?: string
}

export function ScoreBadge({ score, label = 'Lage', className }: ScoreBadgeProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center w-10 h-10 rounded-full text-xs font-medium font-mono',
        scoreColor(score),
        className,
      )}
    >
      <span className="font-bold text-sm leading-none">{score ?? '–'}</span>
      <span className="text-[9px] leading-none mt-0.5 opacity-70">{label}</span>
    </div>
  )
}
```

- [ ] **Step 3: Create frontend/src/components/listings/ListingCard.tsx**

```typescript
import { ArrowSquareOut, Heart, X } from '@phosphor-icons/react'
import { motion } from 'framer-motion'
import type { Listing } from '../../types'
import { StatusChip } from './StatusChip'
import { ScoreBadge } from './ScoreBadge'
import {
  formatPrice,
  formatPricePerSqm,
  formatSqm,
  formatRooms,
  formatDaysOnMarket,
} from '../../lib/formatters'
import { cn } from '../../lib/cn'

interface ListingCardProps {
  listing: Listing
  isNew: boolean
  isSelected: boolean
  onSelect: () => void
  onStatusChange: (status: string) => void
}

export function ListingCard({
  listing,
  isNew,
  isSelected,
  onSelect,
  onStatusChange,
}: ListingCardProps) {
  const imageUrl = listing.images?.[0] ?? null

  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        'group relative flex gap-0 rounded-xl overflow-hidden cursor-pointer',
        'border transition-all duration-150',
        isSelected
          ? 'border-[var(--accent)] shadow-md'
          : 'border-[var(--border)] hover:border-[oklch(78%_0.01_120)] hover:shadow-sm',
      )}
      style={{ background: 'white' }}
      onClick={onSelect}
    >
      {/* Image */}
      <div className="relative w-44 shrink-0 bg-[var(--accent-muted)]">
        {imageUrl ? (
          <img
            src={imageUrl}
            alt={listing.title}
            loading="lazy"
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <span className="text-xs" style={{ color: 'var(--muted)' }}>kein Bild</span>
          </div>
        )}
        {isNew && (
          <span className="absolute top-2 left-2 w-2 h-2 rounded-full bg-[var(--status-new)]" />
        )}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0 p-4 flex flex-col gap-2">
        {/* Header */}
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="font-display font-semibold text-sm leading-snug line-clamp-2" style={{ color: 'var(--fg)' }}>
              {listing.title}
            </p>
            <p className="text-xs mt-0.5" style={{ color: 'var(--muted)' }}>
              {listing.city ?? listing.address ?? '–'} · {listing.source}
            </p>
          </div>
          <ScoreBadge score={listing.lage_score} />
        </div>

        {/* Price row */}
        <div className="flex items-baseline gap-3">
          <span className="font-mono font-bold text-base" style={{ color: 'var(--accent)' }}>
            {formatPricePerSqm(listing.price_per_sqm)}
          </span>
          <span className="font-mono text-sm" style={{ color: 'var(--fg)' }}>
            {formatPrice(listing.price_eur)}
          </span>
        </div>

        {/* Specs row */}
        <div className="flex items-center gap-3 text-xs" style={{ color: 'var(--muted)' }}>
          <span>{formatSqm(listing.qm)}</span>
          <span>·</span>
          <span>{formatRooms(listing.rooms)}</span>
          {listing.year_built && (
            <>
              <span>·</span>
              <span>Bj. {listing.year_built}</span>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center gap-2 mt-auto">
          <StatusChip status={listing.status} />
          <span className="text-xs ml-auto" style={{ color: 'var(--muted)' }}>
            {formatDaysOnMarket(listing.first_seen_at)}
          </span>
        </div>
      </div>

      {/* Hover quick-actions */}
      <div
        className="absolute bottom-3 right-3 hidden group-hover:flex items-center gap-1"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={() => onStatusChange('interessant')}
          className="p-1.5 rounded-lg bg-white/90 border transition-colors hover:bg-[var(--accent-muted)]"
          style={{ borderColor: 'var(--border)' }}
          title="Interessant"
        >
          <Heart size={14} style={{ color: 'var(--accent)' }} />
        </button>
        <button
          onClick={() => onStatusChange('abgelehnt')}
          className="p-1.5 rounded-lg bg-white/90 border transition-colors hover:bg-[oklch(94%_0.04_25)]"
          style={{ borderColor: 'var(--border)' }}
          title="Ablehnen"
        >
          <X size={14} style={{ color: 'oklch(52% 0.180 25)' }} />
        </button>
        <a
          href={listing.url}
          target="_blank"
          rel="noopener noreferrer"
          className="p-1.5 rounded-lg bg-white/90 border transition-colors hover:bg-[var(--accent-muted)]"
          style={{ borderColor: 'var(--border)' }}
          title="Exposé öffnen"
        >
          <ArrowSquareOut size={14} style={{ color: 'var(--fg)' }} />
        </a>
      </div>
    </motion.article>
  )
}
```

- [ ] **Step 4: Typecheck**

```bash
cd /Users/philippherrlich/Code/immo-radar/.worktrees/frontend-spa/frontend
npm run typecheck
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
cd ..
git add frontend/src/components/listings/StatusChip.tsx frontend/src/components/listings/ScoreBadge.tsx frontend/src/components/listings/ListingCard.tsx
git commit -m "feat(frontend): StatusChip, ScoreBadge, ListingCard Komponenten"
```

---

### Task 7: FilterBar Component

**Files:**
- Create: `frontend/src/components/listings/FilterBar.tsx`

- [ ] **Step 1: Create frontend/src/components/listings/FilterBar.tsx**

```typescript
import { X } from '@phosphor-icons/react'
import { useUIStore } from '../../store/ui'
import { STATUS_LABELS } from '../../types'
import { cn } from '../../lib/cn'

const STATUS_OPTIONS = [
  { value: '', label: 'Alle' },
  { value: 'new', label: STATUS_LABELS.new },
  { value: 'interessant', label: STATUS_LABELS.interessant },
  { value: 'vielleicht', label: STATUS_LABELS.vielleicht },
  { value: 'gesehen', label: STATUS_LABELS.gesehen },
  { value: 'abgelehnt', label: STATUS_LABELS.abgelehnt },
]

const SCORE_OPTIONS = [
  { value: null, label: 'Alle Scores' },
  { value: 50, label: 'Score ≥ 50' },
  { value: 70, label: 'Score ≥ 70' },
  { value: 80, label: 'Score ≥ 80' },
]

interface FilterBarProps {
  sources: string[]
  totalCount: number
}

export function FilterBar({ sources, totalCount }: FilterBarProps) {
  const { filter, setFilter, resetFilter } = useUIStore()
  const hasActiveFilter = filter.status !== '' || filter.source !== '' || filter.min_score != null

  return (
    <div
      className="sticky top-0 z-10 border-b px-6 py-3 flex items-center gap-3 flex-wrap"
      style={{ background: 'var(--bg)', borderColor: 'var(--border)' }}
    >
      {/* Status chips */}
      <div className="flex items-center gap-1">
        {STATUS_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => setFilter({ status: opt.value })}
            className={cn(
              'px-3 py-1 rounded-full text-xs font-medium transition-colors',
              filter.status === opt.value
                ? 'text-white'
                : 'hover:bg-[var(--accent-muted)]',
            )}
            style={
              filter.status === opt.value
                ? { background: 'var(--accent)', color: 'white' }
                : { color: 'var(--fg)' }
            }
          >
            {opt.label}
          </button>
        ))}
      </div>

      <div className="h-4 w-px" style={{ background: 'var(--border)' }} />

      {/* Score filter */}
      <select
        value={filter.min_score ?? ''}
        onChange={(e) =>
          setFilter({ min_score: e.target.value === '' ? null : Number(e.target.value) })
        }
        className="text-xs px-2 py-1 rounded-lg border bg-white"
        style={{ borderColor: 'var(--border)', color: 'var(--fg)' }}
      >
        {SCORE_OPTIONS.map((opt) => (
          <option key={String(opt.value)} value={opt.value ?? ''}>
            {opt.label}
          </option>
        ))}
      </select>

      {/* Source filter */}
      {sources.length > 1 && (
        <select
          value={filter.source}
          onChange={(e) => setFilter({ source: e.target.value })}
          className="text-xs px-2 py-1 rounded-lg border bg-white"
          style={{ borderColor: 'var(--border)', color: 'var(--fg)' }}
        >
          <option value="">Alle Quellen</option>
          {sources.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      )}

      {/* Reset */}
      {hasActiveFilter && (
        <button
          onClick={resetFilter}
          className="flex items-center gap-1 text-xs px-2 py-1 rounded-lg transition-colors hover:bg-[var(--accent-muted)]"
          style={{ color: 'var(--muted)' }}
        >
          <X size={12} />
          Filter zurücksetzen
        </button>
      )}

      {/* Count */}
      <span className="ml-auto text-xs" style={{ color: 'var(--muted)' }}>
        {totalCount} {totalCount === 1 ? 'Objekt' : 'Objekte'}
      </span>
    </div>
  )
}
```

- [ ] **Step 2: Typecheck**

```bash
cd /Users/philippherrlich/Code/immo-radar/.worktrees/frontend-spa/frontend
npm run typecheck
```

- [ ] **Step 3: Commit**

```bash
cd ..
git add frontend/src/components/listings/FilterBar.tsx
git commit -m "feat(frontend): FilterBar Komponente"
```

---

### Task 8: DetailPanel Component

**Files:**
- Create: `frontend/src/components/listings/DetailPanel.tsx`

- [ ] **Step 1: Create frontend/src/components/listings/DetailPanel.tsx**

```typescript
import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { X, ArrowSquareOut, Warning } from '@phosphor-icons/react'
import type { Listing } from '../../types'
import { StatusChip } from './StatusChip'
import { ScoreBadge } from './ScoreBadge'
import {
  formatPrice,
  formatPricePerSqm,
  formatSqm,
  formatRooms,
  formatDaysOnMarket,
} from '../../lib/formatters'
import { patchListing } from '../../api/listings'
import { STATUS_LABELS } from '../../types'

interface DetailPanelProps {
  listing: Listing | null
  onClose: () => void
  onStatusChange: (id: number, status: string) => void
}

export function DetailPanel({ listing, onClose, onStatusChange }: DetailPanelProps) {
  const [notes, setNotes] = useState('')
  const debounceRef = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => {
    if (listing) setNotes(listing.notes ?? '')
  }, [listing?.id])

  function handleNotesChange(value: string) {
    setNotes(value)
    clearTimeout(debounceRef.current)
    if (listing) {
      debounceRef.current = setTimeout(() => {
        patchListing(listing.id, { notes: value })
      }, 1_000)
    }
  }

  function handleStatusChange(status: string) {
    if (!listing) return
    patchListing(listing.id, { status })
    onStatusChange(listing.id, status)
  }

  return (
    <AnimatePresence>
      {listing && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-30"
            style={{ background: 'oklch(18% 0.010 240 / 0.15)' }}
            onClick={onClose}
          />

          {/* Panel */}
          <motion.aside
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 28, stiffness: 300 }}
            className="fixed right-0 top-0 h-full w-[420px] z-40 overflow-y-auto flex flex-col"
            style={{ background: 'white', borderLeft: '1px solid var(--border)' }}
          >
            {/* Header */}
            <div className="sticky top-0 z-10 flex items-start gap-3 p-5 border-b" style={{ background: 'white', borderColor: 'var(--border)' }}>
              <div className="flex-1 min-w-0">
                <p className="font-display font-bold text-lg leading-tight line-clamp-2" style={{ color: 'var(--fg)' }}>
                  {listing.title}
                </p>
                <div className="flex items-baseline gap-2 mt-1">
                  <span className="font-mono font-bold text-xl" style={{ color: 'var(--accent)' }}>
                    {formatPricePerSqm(listing.price_per_sqm)}
                  </span>
                  <span className="font-mono text-sm" style={{ color: 'var(--fg)' }}>
                    {formatPrice(listing.price_eur)}
                  </span>
                </div>
                <p className="text-xs mt-0.5" style={{ color: 'var(--muted)' }}>
                  {formatDaysOnMarket(listing.first_seen_at)} online · {listing.source}
                </p>
              </div>
              <button
                onClick={onClose}
                className="shrink-0 p-1.5 rounded-lg transition-colors hover:bg-[var(--accent-muted)]"
                style={{ color: 'var(--muted)' }}
              >
                <X size={18} />
              </button>
            </div>

            {/* Body */}
            <div className="flex-1 p-5 flex flex-col gap-6">
              {/* Image gallery */}
              {listing.images.length > 0 && (
                <div className="flex gap-2 overflow-x-auto pb-1 -mx-5 px-5">
                  {listing.images.slice(0, 6).map((src, i) => (
                    <img
                      key={i}
                      src={src}
                      alt=""
                      className="h-40 w-auto rounded-lg shrink-0 object-cover"
                    />
                  ))}
                </div>
              )}

              {/* Key data */}
              <div className="grid grid-cols-2 gap-3">
                {[
                  { label: 'Fläche', value: formatSqm(listing.qm) },
                  { label: 'Zimmer', value: formatRooms(listing.rooms) },
                  { label: 'Baujahr', value: listing.year_built ? String(listing.year_built) : '–' },
                  { label: 'Typ', value: listing.property_type ?? '–' },
                  { label: 'Hausgeld', value: listing.hausgeld_eur ? formatPrice(listing.hausgeld_eur) + '/Mo.' : '–' },
                  { label: 'Energie', value: listing.energie_class ? `${listing.energie_class}${listing.energie_kwh ? ` · ${Math.round(listing.energie_kwh)} kWh` : ''}` : '–' },
                ].map(({ label, value }) => (
                  <div key={label}>
                    <p className="text-xs" style={{ color: 'var(--muted)' }}>{label}</p>
                    <p className="font-mono text-sm font-medium" style={{ color: 'var(--fg)' }}>{value}</p>
                  </div>
                ))}
              </div>

              {/* Address */}
              {listing.address && (
                <div>
                  <p className="text-xs mb-1" style={{ color: 'var(--muted)' }}>Adresse</p>
                  <p className="text-sm" style={{ color: 'var(--fg)' }}>{listing.address}</p>
                </div>
              )}

              {/* AI Score + Reasoning */}
              <div className="flex items-start gap-3 p-4 rounded-xl" style={{ background: 'var(--bg)' }}>
                <ScoreBadge score={listing.lage_score} />
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium mb-1" style={{ color: 'var(--fg)' }}>KI-Bewertung</p>
                  <p className="text-xs leading-relaxed" style={{ color: 'var(--muted)' }}>
                    {listing.ai_reasoning ?? 'Noch keine KI-Bewertung.'}
                  </p>
                </div>
              </div>

              {/* Risk flags */}
              {listing.risk_flags.length > 0 && (
                <div>
                  <p className="text-xs mb-2" style={{ color: 'var(--muted)' }}>Risiken</p>
                  <div className="flex flex-wrap gap-1.5">
                    {listing.risk_flags.map((flag) => (
                      <span
                        key={flag}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs"
                        style={{ background: 'oklch(94% 0.04 25)', color: 'oklch(38% 0.14 25)' }}
                      >
                        <Warning size={11} />
                        {flag}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Status selector */}
              <div>
                <p className="text-xs mb-2" style={{ color: 'var(--muted)' }}>Status</p>
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(STATUS_LABELS).map(([value, label]) => (
                    <button
                      key={value}
                      onClick={() => handleStatusChange(value)}
                      className="px-3 py-1 rounded-full text-xs font-medium border transition-all"
                      style={
                        listing.status === value
                          ? { background: 'var(--accent)', color: 'white', borderColor: 'var(--accent)' }
                          : { background: 'white', color: 'var(--fg)', borderColor: 'var(--border)' }
                      }
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Notes */}
              <div>
                <p className="text-xs mb-2" style={{ color: 'var(--muted)' }}>Notizen</p>
                <textarea
                  value={notes}
                  onChange={(e) => handleNotesChange(e.target.value)}
                  placeholder="Persönliche Notizen…"
                  rows={4}
                  className="w-full text-sm p-3 rounded-xl border resize-none focus:outline-none focus:ring-1"
                  style={{
                    borderColor: 'var(--border)',
                    color: 'var(--fg)',
                    background: 'var(--bg)',
                    fontFamily: 'inherit',
                  }}
                />
              </div>
            </div>

            {/* Footer CTA */}
            <div className="sticky bottom-0 p-4 border-t" style={{ background: 'white', borderColor: 'var(--border)' }}>
              <a
                href={listing.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-center gap-2 w-full py-2.5 rounded-xl text-sm font-medium text-white transition-opacity hover:opacity-90"
                style={{ background: 'var(--accent)' }}
              >
                Exposé öffnen
                <ArrowSquareOut size={16} />
              </a>
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}
```

- [ ] **Step 2: Typecheck**

```bash
cd /Users/philippherrlich/Code/immo-radar/.worktrees/frontend-spa/frontend
npm run typecheck
```

- [ ] **Step 3: Commit**

```bash
cd ..
git add frontend/src/components/listings/DetailPanel.tsx
git commit -m "feat(frontend): DetailPanel mit Slide-in Animation + Notizen + Status"
```

---

### Task 9: ListingsPage — Assembles Everything

**Files:**
- Modify: `frontend/src/pages/ListingsPage.tsx`

- [ ] **Step 1: Replace ListingsPage.tsx with full implementation**

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AnimatePresence } from 'framer-motion'
import { fetchListings } from '../api/listings'
import { fetchSources } from '../api/sources'
import { patchListing } from '../api/listings'
import { ListingCard } from '../components/listings/ListingCard'
import { FilterBar } from '../components/listings/FilterBar'
import { DetailPanel } from '../components/listings/DetailPanel'
import { useUIStore } from '../store/ui'
import { useLastVisit, isNewSinceLastVisit } from '../hooks/useLastVisit'
import type { Listing } from '../types'

export function ListingsPage() {
  const { filter, selectedListingId, setSelectedListingId } = useUIStore()
  const lastVisit = useLastVisit()
  const queryClient = useQueryClient()

  const { data: listings = [], isLoading } = useQuery({
    queryKey: ['listings', filter],
    queryFn: () =>
      fetchListings({
        status: filter.status || undefined,
        portal: filter.source || undefined,
        min_score: filter.min_score ?? undefined,
      }),
  })

  const { data: sources = [] } = useQuery({
    queryKey: ['sources'],
    queryFn: fetchSources,
  })

  const patchMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      patchListing(id, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['listings'] })
    },
  })

  const selectedListing: Listing | null =
    listings.find((l) => l.id === selectedListingId) ?? null

  const sourceNames = [...new Set(sources.map((s) => s.name))]

  function handleStatusChange(id: number, status: string) {
    patchMutation.mutate({ id, status })
    queryClient.setQueryData<Listing[]>(['listings', filter], (prev) =>
      prev?.map((l) => (l.id === id ? { ...l, status } : l)),
    )
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 rounded-full border-2 animate-spin"
          style={{ borderColor: 'var(--border)', borderTopColor: 'var(--accent)' }} />
      </div>
    )
  }

  return (
    <div className="flex flex-col min-h-[100dvh]">
      <FilterBar sources={sourceNames} totalCount={listings.length} />

      <div className="flex-1 px-6 py-4">
        {listings.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <p className="font-display text-xl font-semibold mb-2" style={{ color: 'var(--fg)' }}>
              Keine Objekte gefunden
            </p>
            <p className="text-sm" style={{ color: 'var(--muted)' }}>
              Filter anpassen oder warten bis der nächste Crawl läuft.
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <AnimatePresence initial={false}>
              {listings.map((listing) => (
                <ListingCard
                  key={listing.id}
                  listing={listing}
                  isNew={isNewSinceLastVisit(listing.first_seen_at, lastVisit)}
                  isSelected={listing.id === selectedListingId}
                  onSelect={() =>
                    setSelectedListingId(
                      listing.id === selectedListingId ? null : listing.id,
                    )
                  }
                  onStatusChange={(status) => handleStatusChange(listing.id, status)}
                />
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>

      <DetailPanel
        listing={selectedListing}
        onClose={() => setSelectedListingId(null)}
        onStatusChange={handleStatusChange}
      />
    </div>
  )
}
```

- [ ] **Step 2: Typecheck + build**

```bash
cd /Users/philippherrlich/Code/immo-radar/.worktrees/frontend-spa/frontend
npm run typecheck
npm run build
```

Expected: no errors. Verify dist/ is created.

- [ ] **Step 3: Manual browser test**

Start the FastAPI backend locally:
```bash
cd /Users/philippherrlich/Code/immo-radar/.worktrees/frontend-spa
source .venv/bin/activate
python -m scripts.run_web
```

Start Vite dev server in another terminal:
```bash
cd frontend && npm run dev
```

Open http://localhost:5173. Verify:
- Sidebar renders with navigation
- Listings load and display
- Filter bar works
- Clicking a listing opens the detail panel
- Status quick-actions work on hover

- [ ] **Step 4: Commit**

```bash
cd ..
git add frontend/src/pages/ListingsPage.tsx
git commit -m "feat(frontend): ListingsPage — vollständige Listings-Ansicht"
```

---

### Task 10: SettingsPage (4 Tabs)

**Files:**
- Create: `frontend/src/components/settings/SearchProfileTab.tsx`
- Create: `frontend/src/components/settings/NotificationsTab.tsx`
- Create: `frontend/src/components/settings/MechanicsTab.tsx`
- Create: `frontend/src/components/settings/SourcesTab.tsx`
- Modify: `frontend/src/pages/SettingsPage.tsx`

- [ ] **Step 1: Create frontend/src/components/settings/SearchProfileTab.tsx**

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchSettings, patchSetting } from '../../api/settings'
import type { AppSettings } from '../../types'

function useSetting<K extends keyof AppSettings>(key: K) {
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: (value: AppSettings[K]) => patchSetting(key, value),
    onSuccess: (data) => {
      queryClient.setQueryData(['settings'], data)
    },
  })
  return mutation
}

interface RowProps {
  label: string
  hint?: string
  children: React.ReactNode
}

function Row({ label, hint, children }: RowProps) {
  return (
    <div className="flex items-center justify-between py-4 border-b" style={{ borderColor: 'var(--border)' }}>
      <div>
        <p className="text-sm font-medium" style={{ color: 'var(--fg)' }}>{label}</p>
        {hint && <p className="text-xs mt-0.5" style={{ color: 'var(--muted)' }}>{hint}</p>}
      </div>
      <div className="ml-6 shrink-0">{children}</div>
    </div>
  )
}

export function SearchProfileTab() {
  const { data } = useQuery({ queryKey: ['settings'], queryFn: fetchSettings })
  const s = data?.settings

  const radiusMut = useSetting('search_radius_km')
  const priceMinMut = useSetting('price_min')
  const priceMaxMut = useSetting('price_max')
  const roomsMut = useSetting('rooms_min')

  if (!s) return <div className="py-8 text-center text-sm" style={{ color: 'var(--muted)' }}>Lade…</div>

  return (
    <div>
      <Row label="Suchradius" hint={`${s.search_radius_km} km um Tutzing`}>
        <div className="flex items-center gap-3">
          <input
            type="range" min={1} max={20} step={1}
            defaultValue={s.search_radius_km}
            onMouseUp={(e) => radiusMut.mutate(Number((e.target as HTMLInputElement).value))}
            className="w-32 accent-[var(--accent)]"
          />
          <span className="font-mono text-sm w-12 text-right" style={{ color: 'var(--fg)' }}>
            {s.search_radius_km} km
          </span>
        </div>
      </Row>

      <Row label="Preisuntergrenze" hint="Minimum-Kaufpreis">
        <div className="flex items-center gap-2">
          <input
            type="number" step={10000} min={0} max={s.price_max}
            defaultValue={s.price_min}
            onBlur={(e) => priceMinMut.mutate(Number(e.target.value))}
            className="w-32 text-sm font-mono px-2 py-1 rounded-lg border text-right"
            style={{ borderColor: 'var(--border)', color: 'var(--fg)' }}
          />
          <span className="text-xs" style={{ color: 'var(--muted)' }}>€</span>
        </div>
      </Row>

      <Row label="Preisobergrenze" hint="Maximum-Kaufpreis">
        <div className="flex items-center gap-2">
          <input
            type="number" step={10000} min={s.price_min} max={5000000}
            defaultValue={s.price_max}
            onBlur={(e) => priceMaxMut.mutate(Number(e.target.value))}
            className="w-32 text-sm font-mono px-2 py-1 rounded-lg border text-right"
            style={{ borderColor: 'var(--border)', color: 'var(--fg)' }}
          />
          <span className="text-xs" style={{ color: 'var(--muted)' }}>€</span>
        </div>
      </Row>

      <Row label="Mindest-Zimmer" hint="Minimum Zimmeranzahl">
        <select
          defaultValue={s.rooms_min}
          onChange={(e) => roomsMut.mutate(Number(e.target.value))}
          className="text-sm px-2 py-1 rounded-lg border"
          style={{ borderColor: 'var(--border)', color: 'var(--fg)' }}
        >
          {[0, 1, 1.5, 2, 2.5, 3, 3.5, 4, 5].map((r) => (
            <option key={r} value={r}>{r === 0 ? 'Egal' : `≥ ${r} Zi.`}</option>
          ))}
        </select>
      </Row>
    </div>
  )
}
```

- [ ] **Step 2: Create frontend/src/components/settings/NotificationsTab.tsx**

```typescript
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle, XCircle } from '@phosphor-icons/react'
import { fetchSettings, patchSetting } from '../../api/settings'
import { testTelegram } from '../../api/telegram'

export function NotificationsTab() {
  const { data } = useQuery({ queryKey: ['settings'], queryFn: fetchSettings })
  const queryClient = useQueryClient()
  const s = data?.settings
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null)

  const thresholdMut = useMutation({
    mutationFn: (v: number) => patchSetting('score_threshold', v),
    onSuccess: (d) => queryClient.setQueryData(['settings'], d),
  })

  const testMut = useMutation({
    mutationFn: testTelegram,
    onSuccess: (result) => setTestResult(result),
    onError: (e: Error) => setTestResult({ success: false, message: e.message }),
  })

  if (!s) return <div className="py-8 text-center text-sm" style={{ color: 'var(--muted)' }}>Lade…</div>

  return (
    <div>
      <div className="py-4 border-b" style={{ borderColor: 'var(--border)' }}>
        <p className="text-sm font-medium mb-1" style={{ color: 'var(--fg)' }}>Score-Schwelle für Alerts</p>
        <p className="text-xs mb-3" style={{ color: 'var(--muted)' }}>
          Nur Listings mit Lage-Score ≥ Schwelle lösen eine Telegram-Nachricht aus.
          0 = alle Listings benachrichtigen.
        </p>
        <div className="flex items-center gap-3">
          <input
            type="range" min={0} max={100} step={5}
            defaultValue={s.score_threshold}
            onMouseUp={(e) => thresholdMut.mutate(Number((e.target as HTMLInputElement).value))}
            className="w-48 accent-[var(--accent)]"
          />
          <span className="font-mono text-sm" style={{ color: 'var(--fg)' }}>
            {s.score_threshold === 0 ? 'Alle' : `≥ ${s.score_threshold}`}
          </span>
        </div>
      </div>

      <div className="py-4">
        <p className="text-sm font-medium mb-3" style={{ color: 'var(--fg)' }}>Telegram-Verbindung testen</p>
        <button
          onClick={() => testMut.mutate()}
          disabled={testMut.isPending}
          className="px-4 py-2 rounded-lg text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
          style={{ background: 'var(--accent)' }}
        >
          {testMut.isPending ? 'Sende…' : 'Test-Nachricht senden'}
        </button>

        {testResult && (
          <div
            className="flex items-center gap-2 mt-3 p-3 rounded-lg text-sm"
            style={{
              background: testResult.success ? 'oklch(92% 0.04 145)' : 'oklch(94% 0.04 25)',
              color: testResult.success ? 'oklch(35% 0.13 145)' : 'oklch(38% 0.14 25)',
            }}
          >
            {testResult.success
              ? <CheckCircle size={16} />
              : <XCircle size={16} />}
            {testResult.message}
          </div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Create frontend/src/components/settings/MechanicsTab.tsx**

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchSettings, patchSetting } from '../../api/settings'

export function MechanicsTab() {
  const { data } = useQuery({ queryKey: ['settings'], queryFn: fetchSettings })
  const queryClient = useQueryClient()
  const s = data?.settings

  function useMut(key: string) {
    return useMutation({
      mutationFn: (v: number) => patchSetting(key, v),
      onSuccess: (d) => queryClient.setQueryData(['settings'], d),
    })
  }

  const pollMut = useMut('poll_interval_minutes')
  const enrichMut = useMut('detail_fetch_interval_minutes')

  if (!s) return <div className="py-8 text-center text-sm" style={{ color: 'var(--muted)' }}>Lade…</div>

  return (
    <div>
      <div className="py-4 border-b" style={{ borderColor: 'var(--border)' }}>
        <p className="text-sm font-medium mb-1" style={{ color: 'var(--fg)' }}>Poll-Intervall</p>
        <p className="text-xs mb-3" style={{ color: 'var(--muted)' }}>
          Wie oft werden alle Quellen nach neuen Inseraten durchsucht?
        </p>
        <div className="flex items-center gap-3">
          {[5, 10, 15, 30, 60].map((v) => (
            <button
              key={v}
              onClick={() => pollMut.mutate(v)}
              className="px-3 py-1.5 rounded-lg text-sm font-medium border transition-all"
              style={
                s.poll_interval_minutes === v
                  ? { background: 'var(--accent)', color: 'white', borderColor: 'var(--accent)' }
                  : { color: 'var(--fg)', borderColor: 'var(--border)', background: 'white' }
              }
            >
              {v} Min
            </button>
          ))}
        </div>
      </div>

      <div className="py-4">
        <p className="text-sm font-medium mb-1" style={{ color: 'var(--fg)' }}>Enrichment-Intervall</p>
        <p className="text-xs mb-3" style={{ color: 'var(--muted)' }}>
          Wie oft werden Detaildaten (KI-Scoring, Lage) nachgeladen?
        </p>
        <div className="flex items-center gap-3">
          {[30, 60, 120].map((v) => (
            <button
              key={v}
              onClick={() => enrichMut.mutate(v)}
              className="px-3 py-1.5 rounded-lg text-sm font-medium border transition-all"
              style={
                s.detail_fetch_interval_minutes === v
                  ? { background: 'var(--accent)', color: 'white', borderColor: 'var(--accent)' }
                  : { color: 'var(--fg)', borderColor: 'var(--border)', background: 'white' }
              }
            >
              {v} Min
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Create frontend/src/components/settings/SourcesTab.tsx**

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchSources, patchSource } from '../../api/sources'
import { formatTimeAgo } from '../../lib/formatters'

export function SourcesTab() {
  const queryClient = useQueryClient()
  const { data: sources = [] } = useQuery({ queryKey: ['sources'], queryFn: fetchSources })

  const toggleMut = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      patchSource(id, { enabled }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['sources'] }),
  })

  return (
    <div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left" style={{ color: 'var(--muted)' }}>
            <th className="py-3 font-medium text-xs">Quelle</th>
            <th className="py-3 font-medium text-xs">Letzter Crawl</th>
            <th className="py-3 font-medium text-xs text-right">Inserate</th>
            <th className="py-3 font-medium text-xs text-right">Aktiv</th>
          </tr>
        </thead>
        <tbody>
          {sources.map((source) => (
            <tr key={source.id} className="border-t" style={{ borderColor: 'var(--border)' }}>
              <td className="py-3 font-medium" style={{ color: 'var(--fg)' }}>
                {source.display_name}
              </td>
              <td className="py-3" style={{ color: 'var(--muted)' }}>
                {source.last_run ? formatTimeAgo(source.last_run) : '–'}
              </td>
              <td className="py-3 text-right font-mono text-xs" style={{ color: 'var(--fg)' }}>
                {source.listing_count}
              </td>
              <td className="py-3 text-right">
                <button
                  onClick={() => toggleMut.mutate({ id: source.id, enabled: !source.enabled })}
                  className="relative inline-flex h-5 w-9 rounded-full transition-colors"
                  style={{
                    background: source.enabled ? 'var(--accent)' : 'var(--border)',
                  }}
                  aria-label={source.enabled ? 'Deaktivieren' : 'Aktivieren'}
                >
                  <span
                    className="inline-block h-4 w-4 rounded-full bg-white shadow transition-transform my-0.5"
                    style={{ transform: source.enabled ? 'translateX(20px)' : 'translateX(2px)' }}
                  />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
```

- [ ] **Step 5: Modify frontend/src/pages/SettingsPage.tsx**

```typescript
import { useState } from 'react'
import { SearchProfileTab } from '../components/settings/SearchProfileTab'
import { NotificationsTab } from '../components/settings/NotificationsTab'
import { MechanicsTab } from '../components/settings/MechanicsTab'
import { SourcesTab } from '../components/settings/SourcesTab'
import { cn } from '../lib/cn'

const TABS = [
  { id: 'search', label: 'Suchprofil', component: SearchProfileTab },
  { id: 'notifications', label: 'Benachrichtigungen', component: NotificationsTab },
  { id: 'mechanics', label: 'Mechanik', component: MechanicsTab },
  { id: 'sources', label: 'Quellen', component: SourcesTab },
]

export function SettingsPage() {
  const [activeTab, setActiveTab] = useState('search')
  const ActiveComponent = TABS.find((t) => t.id === activeTab)?.component ?? SearchProfileTab

  return (
    <div className="max-w-3xl mx-auto px-6 py-8">
      <h1 className="font-display text-2xl font-bold mb-6" style={{ color: 'var(--fg)' }}>
        Einstellungen
      </h1>

      {/* Tab nav */}
      <div className="flex gap-1 border-b mb-6" style={{ borderColor: 'var(--border)' }}>
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              'px-4 py-2 text-sm font-medium -mb-px border-b-2 transition-colors',
              activeTab === tab.id
                ? 'border-[var(--accent)]'
                : 'border-transparent hover:border-[var(--border)]',
            )}
            style={{ color: activeTab === tab.id ? 'var(--accent)' : 'var(--muted)' }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <ActiveComponent />
    </div>
  )
}
```

- [ ] **Step 6: Typecheck**

```bash
cd /Users/philippherrlich/Code/immo-radar/.worktrees/frontend-spa/frontend
npm run typecheck
```

- [ ] **Step 7: Commit**

```bash
cd ..
git add frontend/src/components/settings/ frontend/src/pages/SettingsPage.tsx
git commit -m "feat(frontend): SettingsPage mit 4 Tabs (Suchprofil, Notifications, Mechanik, Quellen)"
```

---

### Task 11: SystemPage

**Files:**
- Modify: `frontend/src/pages/SystemPage.tsx`

- [ ] **Step 1: Replace SystemPage.tsx**

```typescript
import { useQuery, useMutation } from '@tanstack/react-query'
import { Play, ArrowClockwise } from '@phosphor-icons/react'
import { fetchSystemStatus, fetchFetchRuns, triggerCrawl } from '../api/system'
import { formatTimeAgo } from '../lib/formatters'

export function SystemPage() {
  const { data: status, refetch: refetchStatus } = useQuery({
    queryKey: ['system-status'],
    queryFn: fetchSystemStatus,
    refetchInterval: 30_000,
  })

  const { data: runs = [] } = useQuery({
    queryKey: ['fetch-runs'],
    queryFn: fetchFetchRuns,
    refetchInterval: 30_000,
  })

  const triggerMut = useMutation({
    mutationFn: triggerCrawl,
    onSuccess: () => {
      setTimeout(() => refetchStatus(), 2_000)
    },
  })

  const totalListings = status?.listing_counts.total ?? 0

  return (
    <div className="max-w-3xl mx-auto px-6 py-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="font-display text-2xl font-bold" style={{ color: 'var(--fg)' }}>
          System
        </h1>
        <button
          onClick={() => triggerMut.mutate()}
          disabled={triggerMut.isPending}
          className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium text-white disabled:opacity-50 transition-opacity hover:opacity-90"
          style={{ background: 'var(--accent)' }}
        >
          <Play size={14} />
          {triggerMut.isPending ? 'Läuft…' : 'Jetzt crawlen'}
        </button>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        {[
          { label: 'Gesamt', value: totalListings },
          { label: 'Interessant', value: status?.listing_counts.interessant ?? 0 },
          { label: 'Neu (heute)', value: status?.listing_counts.new ?? 0 },
        ].map(({ label, value }) => (
          <div key={label} className="p-4 rounded-xl border" style={{ borderColor: 'var(--border)', background: 'white' }}>
            <p className="text-xs" style={{ color: 'var(--muted)' }}>{label}</p>
            <p className="font-mono text-2xl font-bold mt-1" style={{ color: 'var(--fg)' }}>{value}</p>
          </div>
        ))}
      </div>

      {/* Scheduler */}
      <div className="p-4 rounded-xl border mb-8" style={{ borderColor: 'var(--border)', background: 'white' }}>
        <div className="flex items-center gap-2 mb-3">
          <span
            className="w-2 h-2 rounded-full"
            style={{ background: status?.scheduler_running ? 'var(--status-new)' : 'var(--status-rejected)' }}
          />
          <p className="text-sm font-medium" style={{ color: 'var(--fg)' }}>
            Scheduler {status?.scheduler_running ? 'aktiv' : 'inaktiv'}
          </p>
        </div>
        {status?.jobs.map((job) => (
          <div key={job.id} className="flex justify-between text-xs" style={{ color: 'var(--muted)' }}>
            <span>{job.id}</span>
            <span>{job.next_run ? `nächster Run: ${formatTimeAgo(job.next_run)}` : '–'}</span>
          </div>
        ))}
      </div>

      {/* FetchRuns table */}
      <h2 className="font-display text-lg font-semibold mb-3" style={{ color: 'var(--fg)' }}>
        Letzte Crawls
      </h2>
      <div className="rounded-xl border overflow-hidden" style={{ borderColor: 'var(--border)' }}>
        <table className="w-full text-sm">
          <thead style={{ background: 'var(--bg)' }}>
            <tr style={{ color: 'var(--muted)' }}>
              <th className="text-left px-4 py-2.5 text-xs font-medium">Quelle</th>
              <th className="text-left px-4 py-2.5 text-xs font-medium">Start</th>
              <th className="text-right px-4 py-2.5 text-xs font-medium">Gefunden</th>
              <th className="text-right px-4 py-2.5 text-xs font-medium">Neu</th>
              <th className="text-right px-4 py-2.5 text-xs font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {runs.slice(0, 20).map((run) => (
              <tr key={run.id} className="border-t" style={{ borderColor: 'var(--border)', background: 'white' }}>
                <td className="px-4 py-2.5 font-medium" style={{ color: 'var(--fg)' }}>{run.source}</td>
                <td className="px-4 py-2.5" style={{ color: 'var(--muted)' }}>
                  {formatTimeAgo(run.started_at)}
                </td>
                <td className="px-4 py-2.5 text-right font-mono text-xs" style={{ color: 'var(--fg)' }}>
                  {run.listings_found}
                </td>
                <td className="px-4 py-2.5 text-right font-mono text-xs" style={{ color: run.listings_new > 0 ? 'var(--status-new)' : 'var(--muted)' }}>
                  {run.listings_new > 0 ? `+${run.listings_new}` : '0'}
                </td>
                <td className="px-4 py-2.5 text-right">
                  {run.error ? (
                    <span className="text-xs px-1.5 py-0.5 rounded" style={{ background: 'oklch(94% 0.04 25)', color: 'oklch(38% 0.14 25)' }}>
                      Fehler
                    </span>
                  ) : (
                    <span className="text-xs px-1.5 py-0.5 rounded" style={{ background: 'oklch(92% 0.04 145)', color: 'oklch(35% 0.13 145)' }}>
                      OK
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {runs.length === 0 && (
          <div className="p-8 text-center text-sm" style={{ color: 'var(--muted)' }}>
            Noch keine Crawls gelaufen.
          </div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Typecheck**

```bash
cd /Users/philippherrlich/Code/immo-radar/.worktrees/frontend-spa/frontend
npm run typecheck
```

- [ ] **Step 3: Commit**

```bash
cd ..
git add frontend/src/pages/SystemPage.tsx
git commit -m "feat(frontend): SystemPage mit Scheduler-Status + FetchRuns Tabelle"
```

---

### Task 12: Build Integration (Dockerfile + server.py + Deploy)

**Files:**
- Modify: `Dockerfile`
- Modify: `app/web/server.py`

- [ ] **Step 1: Modify Dockerfile to build frontend**

Replace the existing Dockerfile with:

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    NODE_VERSION=20

# Install Node.js
RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean

# Install Python dependencies
COPY pyproject.toml /app/
RUN pip install --no-cache-dir \
    fastapi==0.115.6 "uvicorn[standard]==0.32.1" jinja2==3.1.4 httpx==0.28.1 \
    beautifulsoup4==4.12.3 lxml==5.3.0 playwright==1.49.0 sqlalchemy==2.0.36 \
    pydantic==2.10.4 pydantic-settings==2.7.0 apscheduler==3.10.4 \
    python-telegram-bot==21.6 anthropic==0.40.0 feedparser==6.0.11 \
    python-multipart==0.0.20 tenacity==9.0.0 structlog==24.4.0 geopy==2.4.1

# Build frontend
COPY frontend/package.json frontend/package-lock.json /app/frontend/
RUN cd /app/frontend && npm ci --prefer-offline

COPY frontend /app/frontend
RUN cd /app/frontend && npm run build
# Output goes to /app/app/web/static/dist/ (vite.config.ts outDir: '../app/web/static/dist')

# Copy app code
COPY app /app/app
COPY scripts /app/scripts

VOLUME ["/app/data"]
EXPOSE 8000

CMD ["python", "-m", "app.main"]
```

Note: The `npm run build` outputs to `../app/web/static/dist` relative to `frontend/`, which resolves to `/app/app/web/static/dist` inside the container. This matches `app/web/server.py`'s static file serving.

- [ ] **Step 2: Update app/web/server.py to serve SPA for root route**

Modify the `index` route to serve the SPA when it's built, otherwise fall back to Jinja2:

Find the `@app.get("/")` handler and replace it:

```python
@app.get("/", include_in_schema=False)
async def index(
    request: Request,
    status_filter: str = "",
    min_score: int = 0,
):
    # Serve SPA if built
    spa_index = BASE_DIR / "static" / "dist" / "index.html"
    if spa_index.exists():
        return FileResponse(str(spa_index))
    # Fallback: legacy Jinja2 dashboard (requires auth)
    from app.web.auth import require_auth
    from fastapi import Depends
    _ = require_auth  # auth is enforced via Depends in the function signature below
    with SessionLocal() as session:
        q = select(Listing).where(Listing.is_active.is_(True))
        if status_filter:
            q = q.where(Listing.status == status_filter)
        if min_score > 0:
            q = q.where(Listing.ai_score >= min_score)
        q = q.order_by(desc(Listing.first_seen_at)).limit(200)
        listings_data = session.scalars(q).all()
        runs = session.scalars(select(FetchRun).order_by(desc(FetchRun.started_at)).limit(10)).all()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "listings": listings_data,
            "runs": runs,
            "status_filter": status_filter,
            "min_score": min_score,
        },
    )
```

Also update the SPA fallback route to serve `static/dist/index.html`:

```python
@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str):
    if full_path.startswith("api/") or full_path.startswith("static/"):
        raise HTTPException(status_code=404)
    spa_index = BASE_DIR / "static" / "dist" / "index.html"
    if spa_index.exists():
        return FileResponse(str(spa_index))
    return JSONResponse({"status": "API running, SPA not built yet"}, status_code=200)
```

Also mount the dist directory for static assets:

After the existing `app.mount("/static", ...)` line, add:
```python
dist_dir = BASE_DIR / "static" / "dist"
if dist_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(dist_dir / "assets")), name="spa-assets")
```

- [ ] **Step 3: Run a local build test**

```bash
cd /Users/philippherrlich/Code/immo-radar/.worktrees/frontend-spa/frontend
npm run build
```

Expected: `../app/web/static/dist/index.html` created.

Start the backend:
```bash
cd ..
source .venv/bin/activate
python -m scripts.run_web
```

Open http://localhost:8000 — should serve the React SPA (not the old Jinja2 template).

- [ ] **Step 4: Run Python tests**

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

All tests must still pass.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile app/web/server.py
git commit -m "feat(deploy): Dockerfile mit Node.js Frontend-Build + SPA-Serving"
```

- [ ] **Step 6: Deploy to VPS**

```bash
bash scripts/deploy.sh
```

Expected: Docker build includes npm ci + npm run build, both containers restart.

After deploy, open http://100.115.184.3:8001 (via Tailscale) and verify:
- React SPA loads (not Jinja2)
- Listings appear
- Sidebar navigation works
- Detail panel opens
- Settings page loads and shows current values
- System page shows scheduler status
