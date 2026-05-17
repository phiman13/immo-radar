# Sources — Analyse & Entdecken — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the "Neue Quelle hinzufügen" section in SourcesTab — URL-Analyse via Claude + Region-Entdeckung via Claude + Speichern in DB.

**Architecture:**
- Existing sources are hardcoded Python modules; dynamic adapter generation is out of scope
- New sources are saved with `source_type="suggested"` and `url` field — visible in the UI as "Vorschlag" until an adapter is implemented
- `POST /api/sources/analyze`: fetches URL with httpx, sends HTML to Claude Haiku, returns field detection + example listing
- `POST /api/sources/discover`: asks Claude to suggest known Immobilien portals/Makler for Tutzing/Starnberger See
- `POST /api/sources/`: saves a new suggested source to DB
- Frontend: multi-step UI in SourcesTab (URL → Loading → Result → Name → Save)

**Tech Stack:** FastAPI · httpx · anthropic SDK · React 18 + TypeScript + Tailwind CSS v3

---

## Task 1: DB Migration — url + source_type Spalten

**Files:**
- Modify: `app/db.py`

The `Source` model needs two new columns: `url` (where the source is found) and `source_type` (`"builtin"` or `"suggested"`). Since the DB already exists on the VPS, `create_all` won't add them — we need an inline migration in `init_db()`.

- [ ] **Step 1: Add columns to Source model in `app/db.py`**

Read `app/db.py` first. Then add to the `Source` class:

```python
url: Mapped[str | None] = mapped_column(String, nullable=True)
source_type: Mapped[str] = mapped_column(String, default="builtin", server_default="builtin")
```

- [ ] **Step 2: Add migration to `init_db()`**

After `Base.metadata.create_all(engine)`, add:

```python
from sqlalchemy import text
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
```

- [ ] **Step 3: Update `SourceOut` in `app/web/api/sources.py`**

Add to `SourceOut`:
```python
url: str | None
source_type: str
```

- [ ] **Step 4: Verify ruff + existing tests still pass**

```bash
source .venv/bin/activate && ruff check app/db.py app/web/api/sources.py && PYTHONPATH=. python -m pytest tests/test_api_sources.py -q
```

- [ ] **Step 5: Commit**

```bash
git add app/db.py app/web/api/sources.py
git commit -m "feat(db): Source-Tabelle um url + source_type erweitert"
```

---

## Task 2: Backend — POST /api/sources/analyze

**Files:**
- Modify: `app/web/api/sources.py`

Fetches a URL with httpx, extracts text from HTML, sends to Claude Haiku to detect listings and fields.

- [ ] **Step 1: Add the endpoint**

```python
import httpx
from anthropic import Anthropic

class AnalyzeRequest(BaseModel):
    url: str

class FieldDetection(BaseModel):
    price: bool
    qm: bool
    rooms: bool
    address: bool
    images: bool

class AnalyzeResult(BaseModel):
    url: str
    listing_count: int          # estimated count on the page
    example_title: str | None   # first example listing title
    example_price: str | None   # first example price as string
    fields: FieldDetection
    error: str | None           # set if fetch/parse failed

@router.post("/analyze", response_model=AnalyzeResult)
async def analyze_source(body: AnalyzeRequest) -> AnalyzeResult:
    # 1. Fetch the URL
    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            headers={"User-Agent": "Mozilla/5.0 (compatible; immo-radar/1.0)"},
            follow_redirects=True,
        ) as client:
            resp = await client.get(body.url)
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        return AnalyzeResult(
            url=body.url, listing_count=0, example_title=None,
            example_price=None, fields=FieldDetection(price=False, qm=False, rooms=False, address=False, images=False),
            error=f"Seite nicht erreichbar: {e}"
        )

    # 2. Truncate HTML to avoid token overflow (keep first 12k chars)
    html_excerpt = html[:12_000]

    # 3. Ask Claude Haiku
    from app.config import settings as _settings
    client = Anthropic(api_key=_settings.anthropic_api_key)
    prompt = f"""Du analysierst eine deutsche Immobilien-Website.

HTML-Ausschnitt:
<html>
{html_excerpt}
</html>

Antworte NUR mit einem JSON-Objekt (kein Markdown, kein Text drumherum):
{{
  "listing_count": <Schätzung wie viele Inserate auf der Seite zu sehen sind, 0 wenn keine>,
  "example_title": <Titel des ersten Inserats oder null>,
  "example_price": <Preis des ersten Inserats als String z.B. "450.000 €" oder null>,
  "fields": {{
    "price": <true wenn Preise erkennbar>,
    "qm": <true wenn m² erkennbar>,
    "rooms": <true wenn Zimmeranzahl erkennbar>,
    "address": <true wenn Adresse/Ort erkennbar>,
    "images": <true wenn Bilder vorhanden>
  }}
}}"""

    try:
        msg = client.messages.create(
            model=_settings.ai_model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        import json
        data = json.loads(msg.content[0].text.strip())
        return AnalyzeResult(
            url=body.url,
            listing_count=data.get("listing_count", 0),
            example_title=data.get("example_title"),
            example_price=data.get("example_price"),
            fields=FieldDetection(**data.get("fields", {})),
            error=None,
        )
    except Exception as e:
        return AnalyzeResult(
            url=body.url, listing_count=0, example_title=None, example_price=None,
            fields=FieldDetection(price=False, qm=False, rooms=False, address=False, images=False),
            error=f"Claude-Analyse fehlgeschlagen: {e}"
        )
```

- [ ] **Step 2: Verify ruff**

```bash
ruff check app/web/api/sources.py
```

- [ ] **Step 3: Commit**

```bash
git add app/web/api/sources.py
git commit -m "feat(api): POST /api/sources/analyze — URL-Analyse via Claude"
```

---

## Task 3: Backend — POST /api/sources/discover + POST /api/sources/

**Files:**
- Modify: `app/web/api/sources.py`

Two more endpoints: one that asks Claude for source suggestions, one that saves a new suggested source.

- [ ] **Step 1: Add POST /api/sources/discover**

```python
class DiscoverResult(BaseModel):
    suggestions: list[dict]  # [{name, url, description}]
    error: str | None

@router.post("/discover", response_model=DiscoverResult)
async def discover_sources() -> DiscoverResult:
    from app.config import settings as _settings
    from anthropic import Anthropic
    import json

    client = Anthropic(api_key=_settings.anthropic_api_key)
    prompt = """Schlage Immobilien-Portale und Makler-Websites für die Region Tutzing / Starnberger See (Bayern, Deutschland) vor, die noch NICHT in dieser Liste sind:
- ImmoScout24 (immoscout24.de)
- Immowelt (immowelt.de)
- Kleinanzeigen (kleinanzeigen.de)
- BS Immo (bsimmo.de)
- Riedel Immobilien
- Starnberg Immo
- Sparkasse Immobilien
- Tutzing24

Antworte NUR mit einem JSON-Array (kein Markdown):
[
  {"name": "<Anzeigename>", "url": "<Startseite der Immobilien-Sektion>", "description": "<1 Satz warum relevant>"},
  ...
]
Maximal 6 Vorschläge. Nur echte, existierende Websites."""

    try:
        msg = client.messages.create(
            model=_settings.ai_model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        suggestions = json.loads(msg.content[0].text.strip())
        return DiscoverResult(suggestions=suggestions, error=None)
    except Exception as e:
        return DiscoverResult(suggestions=[], error=str(e))
```

- [ ] **Step 2: Add POST /api/sources/ (create new source)**

```python
class SourceCreate(BaseModel):
    name: str        # internal identifier (slug)
    display_name: str
    url: str | None = None
    source_type: str = "suggested"

@router.post("/", response_model=SourceOut, status_code=201)
def create_source(body: SourceCreate):
    with db_module.SessionLocal() as session:
        # Check duplicate
        existing = session.query(db_module.Source).filter(db_module.Source.name == body.name).first()
        if existing:
            raise HTTPException(status_code=409, detail="Quelle bereits vorhanden")
        source = db_module.Source(
            name=body.name,
            display_name=body.display_name,
            url=body.url,
            source_type=body.source_type,
            enabled=False,  # suggested sources start disabled
        )
        session.add(source)
        session.commit()
        session.refresh(source)
        return SourceOut.model_validate(source)
```

- [ ] **Step 3: Verify ruff + tests**

```bash
ruff check app/web/api/sources.py && PYTHONPATH=. python -m pytest tests/test_api_sources.py -q
```

- [ ] **Step 4: Commit**

```bash
git add app/web/api/sources.py
git commit -m "feat(api): POST /api/sources/discover + POST /api/sources/ (neue Quelle)"
```

---

## Task 4: Frontend API client + types

**Files:**
- Modify: `frontend/src/api/sources.ts`
- Modify: `frontend/src/types.ts`

- [ ] **Step 1: Read `frontend/src/types.ts` and `frontend/src/api/sources.ts`**

- [ ] **Step 2: Extend `Source` type in `types.ts`**

Add to the `Source` interface:
```typescript
url: string | null;
source_type: string;  // "builtin" | "suggested"
```

- [ ] **Step 3: Add API functions in `sources.ts`**

```typescript
export interface AnalyzeResult {
  url: string;
  listing_count: number;
  example_title: string | null;
  example_price: string | null;
  fields: { price: boolean; qm: boolean; rooms: boolean; address: boolean; images: boolean };
  error: string | null;
}

export interface DiscoverSuggestion {
  name: string;
  url: string;
  description: string;
}

export async function analyzeSource(url: string): Promise<AnalyzeResult> {
  const res = await api.post<AnalyzeResult>('/sources/analyze', { url });
  return res.data;
}

export async function discoverSources(): Promise<DiscoverSuggestion[]> {
  const res = await api.post<{ suggestions: DiscoverSuggestion[]; error: string | null }>('/sources/discover');
  if (res.data.error) throw new Error(res.data.error);
  return res.data.suggestions;
}

export async function createSource(body: {
  name: string;
  display_name: string;
  url?: string;
  source_type?: string;
}): Promise<Source> {
  const res = await api.post<Source>('/sources/', body);
  return res.data;
}
```

- [ ] **Step 4: TypeScript check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types.ts frontend/src/api/sources.ts
git commit -m "feat(types): Source url/source_type, analyzeSource/discoverSources/createSource API"
```

---

## Task 5: Frontend — SourcesTab UI

**Files:**
- Modify: `frontend/src/components/settings/SourcesTab.tsx`

Add the "Neue Quelle hinzufügen" section below the existing sources table. Two flows in one component: URL-Analyse and Quellen-Entdecken.

- [ ] **Step 1: Read the current `SourcesTab.tsx`**

- [ ] **Step 2: Rewrite `SourcesTab.tsx` with the new section**

The component has two parts:
1. **Existing sources table** (keep as-is, add `source_type` badge for "suggested" sources)
2. **New section: "Neue Quelle hinzufügen"** with two sub-flows

Full new section structure:

```tsx
{/* --- Neue Quelle hinzufügen --- */}
<div className="mt-8 border-t border-[--border] pt-6">
  <h3 className="text-sm font-semibold text-[--fg] mb-4">Neue Quelle hinzufügen</h3>

  {/* Flow 1: URL analysieren */}
  <AnalyzeFlow onAdded={() => queryClient.invalidateQueries({ queryKey: ['sources'] })} />

  {/* Divider */}
  <div className="flex items-center gap-3 my-5">
    <div className="flex-1 h-px bg-[--border]" />
    <span className="text-xs text-[--muted]">oder</span>
    <div className="flex-1 h-px bg-[--border]" />
  </div>

  {/* Flow 2: Region entdecken */}
  <DiscoverFlow onAdded={() => queryClient.invalidateQueries({ queryKey: ['sources'] })} />
</div>
```

**AnalyzeFlow component (inline, same file):**

States: `idle` → `loading` → `result` → `naming` → `saved`

```tsx
function AnalyzeFlow({ onAdded }: { onAdded: () => void }) {
  const [url, setUrl] = useState('')
  const [state, setState] = useState<'idle' | 'loading' | 'result' | 'naming' | 'saved'>('idle')
  const [result, setResult] = useState<AnalyzeResult | null>(null)
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function handleAnalyze() {
    if (!url.trim()) return
    setState('loading')
    setError(null)
    try {
      const r = await analyzeSource(url)
      setResult(r)
      setState(r.error ? 'idle' : 'result')
      if (r.error) setError(r.error)
      else setName(new URL(r.url).hostname.replace('www.', ''))
    } catch (e) {
      setError(String(e))
      setState('idle')
    }
  }

  async function handleSave() {
    if (!result || !name.trim()) return
    setState('naming')
    try {
      await createSource({
        name: name.toLowerCase().replace(/[^a-z0-9]/g, '_'),
        display_name: name,
        url: result.url,
        source_type: 'suggested',
      })
      setState('saved')
      onAdded()
    } catch (e) {
      setError(String(e))
      setState('result')
    }
  }

  if (state === 'saved') return (
    <div className="text-sm text-[--accent] flex items-center gap-2">
      <CheckCircle size={16} weight="fill" /> Quelle gespeichert als Vorschlag.
      <button onClick={() => { setState('idle'); setUrl(''); setResult(null); setName('') }}
        className="ml-2 text-[--muted] underline">Weitere hinzufügen</button>
    </div>
  )

  return (
    <div className="space-y-3">
      <label className="block text-xs text-[--muted]">URL der Immobilien-Seite</label>
      <div className="flex gap-2">
        <input
          type="url"
          placeholder="https://makler-xyz.de/immobilien"
          value={url}
          onChange={e => setUrl(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleAnalyze()}
          disabled={state === 'loading'}
          className="flex-1 px-3 py-2 rounded-lg border border-[--border] text-sm focus:outline-none focus:border-[--accent] bg-white"
        />
        <button
          onClick={handleAnalyze}
          disabled={state === 'loading' || !url.trim()}
          className="px-4 py-2 rounded-lg bg-[--accent] text-white text-sm font-medium disabled:opacity-50 flex items-center gap-2"
        >
          {state === 'loading' ? <><Spinner size={14} className="animate-spin" /> Analysiere…</> : 'Analysieren'}
        </button>
      </div>

      {error && <p className="text-xs text-red-500">{error}</p>}

      {state === 'result' && result && (
        <div className="rounded-lg border border-[--border] p-4 space-y-3 bg-white">
          {result.listing_count > 0 ? (
            <>
              <p className="text-sm font-medium text-[--fg]">
                ~{result.listing_count} Inserate gefunden
                {result.example_title && <span className="font-normal text-[--muted]"> · Beispiel: "{result.example_title}{result.example_price ? `, ${result.example_price}` : ''}"</span>}
              </p>
              <div className="flex gap-2 flex-wrap">
                {(['price', 'qm', 'rooms', 'address', 'images'] as const).map(field => (
                  <span key={field} className={cn(
                    'px-2 py-0.5 rounded text-xs',
                    result.fields[field]
                      ? 'bg-[--accent-muted] text-[--accent]'
                      : 'bg-[--border] text-[--muted] line-through'
                  )}>
                    {field === 'price' ? 'Preis' : field === 'qm' ? 'm²' : field === 'rooms' ? 'Zimmer' : field === 'address' ? 'Adresse' : 'Bilder'}
                  </span>
                ))}
              </div>
            </>
          ) : (
            <p className="text-sm text-[--muted]">Keine Inserate erkannt — möglicherweise kein Immobilien-Portal oder Seite erfordert JavaScript.</p>
          )}

          {result.listing_count > 0 && (
            <div className="flex gap-2 items-center pt-1">
              <input
                type="text"
                placeholder="Name der Quelle"
                value={name}
                onChange={e => setName(e.target.value)}
                className="flex-1 px-3 py-1.5 rounded border border-[--border] text-sm focus:outline-none focus:border-[--accent] bg-white"
              />
              <button
                onClick={handleSave}
                disabled={!name.trim()}
                className="px-4 py-1.5 rounded bg-[--accent] text-white text-sm font-medium disabled:opacity-50"
              >
                Aufnehmen
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
```

**DiscoverFlow component (inline, same file):**

```tsx
function DiscoverFlow({ onAdded }: { onAdded: () => void }) {
  const [state, setState] = useState<'idle' | 'loading' | 'result'>('idle')
  const [suggestions, setSuggestions] = useState<DiscoverSuggestion[]>([])
  const [saved, setSaved] = useState<Set<string>>(new Set())
  const [error, setError] = useState<string | null>(null)

  async function handleDiscover() {
    setState('loading')
    setError(null)
    try {
      const results = await discoverSources()
      setSuggestions(results)
      setState('result')
    } catch (e) {
      setError(String(e))
      setState('idle')
    }
  }

  async function handleAdd(s: DiscoverSuggestion) {
    try {
      await createSource({
        name: s.name.toLowerCase().replace(/[^a-z0-9]/g, '_'),
        display_name: s.name,
        url: s.url,
        source_type: 'suggested',
      })
      setSaved(prev => new Set(prev).add(s.name))
      onAdded()
    } catch {
      // 409 = already exists, silently mark as saved
      setSaved(prev => new Set(prev).add(s.name))
    }
  }

  return (
    <div className="space-y-3">
      <button
        onClick={handleDiscover}
        disabled={state === 'loading'}
        className="w-full px-4 py-2.5 rounded-lg border border-[--border] text-sm text-[--fg] hover:border-[--accent] hover:text-[--accent] transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
      >
        {state === 'loading'
          ? <><Spinner size={14} className="animate-spin" /> Claude sucht nach Quellen…</>
          : <><MagnifyingGlass size={16} /> Neue Quellen für meine Region entdecken</>
        }
      </button>

      {error && <p className="text-xs text-red-500">{error}</p>}

      {state === 'result' && suggestions.length > 0 && (
        <div className="rounded-lg border border-[--border] divide-y divide-[--border] bg-white">
          {suggestions.map(s => (
            <div key={s.name} className="flex items-center gap-3 px-4 py-3">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-[--fg]">{s.name}</p>
                <p className="text-xs text-[--muted] truncate">{s.description}</p>
              </div>
              {saved.has(s.name) ? (
                <span className="text-xs text-[--accent] flex items-center gap-1">
                  <CheckCircle size={14} weight="fill" /> Gespeichert
                </span>
              ) : (
                <button
                  onClick={() => handleAdd(s)}
                  className="text-xs px-3 py-1 rounded border border-[--accent] text-[--accent] hover:bg-[--accent-muted] transition-colors"
                >
                  Aufnehmen
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

**Imports needed:**
```tsx
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchSources, patchSource, analyzeSource, discoverSources, createSource, AnalyzeResult, DiscoverSuggestion } from '../../api/sources'
import { CheckCircle, MagnifyingGlass, CircleNotch } from '@phosphor-icons/react'
import { cn } from '../../lib/cn'
import { formatTimeAgo } from '../../lib/formatters'
```

Note: Use `CircleNotch` as the spinner (it's in Phosphor Icons and has the `animate-spin` class applied).

Also update the sources table rows to show a `source_type` badge:
```tsx
{source.source_type === 'suggested' && (
  <span className="ml-2 px-1.5 py-0.5 rounded text-xs bg-[--border] text-[--muted]">Vorschlag</span>
)}
```

- [ ] **Step 3: TypeScript check**

```bash
cd frontend && npx tsc --noEmit 2>&1
```

Fix all errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/settings/SourcesTab.tsx
git commit -m "feat(ui): Neue-Quelle-UI — URL-Analyse + Region-Entdecken in SourcesTab"
```

---

## Task 6: Build + Deploy

- [ ] **Step 1: Full test suite**

```bash
source .venv/bin/activate && PYTHONPATH=. python -m pytest tests/ -q 2>&1 | tail -5
```

- [ ] **Step 2: Frontend build**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

- [ ] **Step 3: Deploy**

```bash
bash scripts/deploy.sh
```

- [ ] **Step 4: Smoke test auf immo.herrlich.dev**

Open Settings → Quellen → "Neue Quelle hinzufügen" section visible.
Enter a URL → "Analysieren" → result shown.
Click "Neue Quellen entdecken" → suggestions appear.

- [ ] **Step 5: Update backlog**

In `docs/backlog.md`, mark **2.8** as ✅.
