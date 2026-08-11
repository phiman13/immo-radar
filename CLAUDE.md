# immo-radar

Immobilien-Aggregator für Tutzing (PLZ 82327 + 5 km). Scrapt Portale, bewertet Objekte per Claude, sendet Alerts via Telegram.

**VPS:** `root@89.167.67.26` | **Dashboard:** `https://immo.herrlich.dev` | Login: admin / tutzing2026!

Auth: Caddy basicauth (kein Tailscale-Direktzugriff mehr). Docker-Container bindet auf `127.0.0.1:8001`.

---

## Struktur

```
app/
  sources/        Scraper: kleinanzeigen.py, bs_immo.py, riedel.py, starnberg_bader.py, tutzing24.py
                  immoscout24_rss.py  ← RSS-Adapter (IS24 blockiert ohne Auth — skippt wenn keine ID)
                  agents_adapter.py  ← generischer, DB-getriebener Adapter für die agents-Tabelle (additiv zur REGISTRY)
  agent_cascade_detect.py  Reine Erkennungsfunktionen der Makler-Extraktions-Kaskade (Vendor-Fingerprints, vokabularfreie Detail-Link-Erkennung, JSON-LD) — I/O-frei
  agent_probe.py  Ein-Domain-Netzwerk-Probe + Kaskaden-Klassifikation (robots-first, bricht bei Disallow sofort ab)
  agent_onboarding.py  Bildet die klassifizierte Kaskadenstufe auf agents.extraction ab und schreibt sie zurück
  scoring/        ai_match.py (Claude Haiku), lage.py (regelbasiert), risk.py
  geocoding.py    Nominatim-Geocoding mit persistentem Adress-Hash-Cache
  robots.py       robots.txt-Respekt für den Makler-Crawl
  notify/         telegram.py
  pipeline.py     Haupt-Pipeline (run_all, run_profile)
  scheduler.py    APScheduler — Interval + Enrich-Toggle aus DB, ändert sich ohne Container-Restart
  db.py           SQLAlchemy + SQLite
  config.py       Pydantic Settings (aus .env)
  usage.py        Token-Logging für API-Kostentracking
  settings_service.py  DB-persistente Settings (Suchprofil, Intervals, Präferenzen)
  web/
    server.py     FastAPI — SPA servieren + API-Routing
    api/          listings.py, settings.py, sources.py, system.py, telegram.py
    auth.py       HTTP-Basic (intern, Caddy ist primäre Auth-Schicht)
frontend/
  src/            React 18 + Vite + TypeScript + Tailwind CSS v3
  dist/           → app/web/static/dist/ (via npm run build)
scripts/
  verify_source.py   Selektoren testen ohne DB-Schreibzugriff
  onboard_agents.py  Makler-Site probt + klassifiziert (manueller Trigger, solange Phase 3/4 fehlen)
  run_once.py        Einzelner Crawl-Durchlauf (schreibt in DB)
  run_web.py         Dashboard lokal starten
  deploy.sh          rsync + docker compose up --build
docs/
  backlog.md              Feature-Backlog (priorisiert)
  superpowers/specs/      Design-Specs
  superpowers/plans/      Implementierungs-Pläne
```

## Quellen-Status

| Name | `source_type` | Status |
|---|---|---|
| kleinanzeigen | builtin | ✅ aktiv (Playwright) |
| bs_immo | builtin | ✅ aktiv (httpx + BS4) |
| riedel | builtin | ✅ aktiv (httpx + BS4) |
| starnberg_bader | builtin | ✅ aktiv (httpx + BS4) |
| tutzing24 | builtin | ✅ aktiv (httpx + BS4) |
| immoscout24 | blocked | ⛔ Bot-Schutz — RSS 404, HTML Bot-Detect; RSS-Adapter skippt ohne IMMOSCOUT24_SAVE_SEARCH_ID |
| immowelt | blocked | ⛔ Bot-Schutz |
| sparkasse_immo | blocked | ⛔ Bot-Schutz |

Blocked-Quellen erscheinen im Dashboard (Sources-Tab) als „Gesperrt" ohne Toggle.

## Key Commands

```bash
# Lokales Setup
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium

# Selektoren prüfen (read-only, kein DB-Write) — VOR Prod-Lauf!
# Lokal ggf. DB_PATH=./data/immo.db voranstellen: der Import von app.sources zieht
# app.db mit (Engine-Konstruktion + DB-Verzeichnis anlegen), geschrieben wird nichts.
python -m scripts.verify_source kleinanzeigen
python -m scripts.verify_source bs_immo

# Linting
ruff check .

# Dashboard lokal (ohne Auth)
python -m scripts.run_web   # → http://localhost:8000

# Frontend lokal (mit Vite Dev Server + API-Proxy auf :8000)
cd frontend && npm run dev  # → http://localhost:5173

# Deploy auf VPS
bash scripts/deploy.sh

# Logs auf VPS
ssh root@89.167.67.26 "cd /opt/immo-radar && docker compose logs -f worker"

# Caddy-Config auf VPS editieren
ssh root@89.167.67.26 "nano /etc/caddy/Caddyfile && systemctl reload caddy"
```

Workflow-Disziplin (Pflicht-Reihenfolge, Monorepo-DoD-Caveat, belegte Anti-Patterns): `DEVELOPMENT.md`.

## Stack

Python 3.12 (noble) · FastAPI · Playwright (Chromium) · SQLite/SQLAlchemy · APScheduler · anthropic SDK · Telegram Bot API · Docker (2 Container: `web` + `worker`) · Caddy (Reverse Proxy + TLS + Auth)

Frontend: React 18 · Vite 5 · TypeScript 5 · Tailwind CSS v3 · TanStack Query v5 · Zustand v4 · Framer Motion v11 · Phosphor Icons

## Besonderheiten

- Selektoren sind fragil — bei Änderungen zuerst `verify_source` prüfen, nie blind editieren
- `kleinanzeigen.py` nutzt Playwright (headless Chromium), die anderen sind HTTP-basiert (httpx + BS4)
- Scoring zweistufig: Lage-Score (regelbasiert) → AI-Match (Claude Haiku, nur bei Score ≥ Threshold)
- Docker-Image enthält Chromium → ~1 GB, Build dauert länger
- `.env` nie committen — Telegram-Token + Dashboard-Passwort drin
- `scripts/deploy.sh` nutzt rsync + SSH direkt auf 89.167.67.26
- Auth liegt bei Caddy (basicauth), FastAPI-interne `require_auth` ist nur für Legacy-Routes aktiv
- Frontend-Build (npm run build im Dockerfile) gibt den Build in `app/web/static/dist/` aus — FastAPI serviert ihn als Static Files
- **Zwei Docker-Container**: `web` (FastAPI + SPA) und `worker` (APScheduler + Pipeline) — Scheduler-State nur im `worker` erreichbar
- **DB-persistente Settings**: `settings_service.py` liest/schreibt Suchprofil (Radius, Budget, Zimmer, Objekttypen, Präferenzen, Baujahr, Orte) und Mechanic-Settings (Intervalle, Enrich-Toggle) in SQLite
- **UTC-Timestamps**: Alle Timestamps in DB als UTC gespeichert. Im Frontend `parseUTC()` verwenden (hängt `Z` an ISO-String) — sonst interpretiert Browser als Lokalzeit
- **`source_type`-Feld**: Discriminator für Quellen — `"builtin"` (aktiv), `"blocked"` (Bot-Schutz), `"suggested"` (user-added). Blocked-Quellen haben in DB enabled=false und Lock-Icon statt Toggle
- **Name-Migrations**: Alte DB-Einträge (`makler_bsimmo`, `makler_riedel`, `makler_starnberg_immo`) werden in `_seed_sources()` automatisch auf neue Namen umgeschrieben
- **`last_run` + `listing_count`**: Im Sources-Tab live aus `FetchRun`- und `Listing`-Tabellen abgeleitet (nicht im Source-Record selbst gespeichert)
- **`IMMOSCOUT24_SAVE_SEARCH_ID`**: Nur numerische ID speichern (keine URL — `&` in env vars bricht docker compose env_file Parser). URL wird in Python zusammengesetzt.

---

@docs/STATUS.md
@.claude/CONVENTIONS.md
@.claude/SKILLS.md
@.claude/DESIGN.md
