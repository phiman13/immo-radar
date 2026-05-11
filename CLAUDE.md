# immo-radar

Immobilien-Aggregator für Tutzing (PLZ 82327 + 5 km). Scrapt Portale, bewertet Objekte per Claude, sendet Alerts via Telegram.

**VPS:** `root@89.167.67.26` | **Dashboard:** `https://immo.herrlich.dev` | Login: admin / tutzing2026!

Auth: Caddy basicauth (kein Tailscale-Direktzugriff mehr). Docker-Container bindet auf `127.0.0.1:8001`.

---

## Struktur

```
app/
  sources/        Scraper: immoscout24.py, immowelt.py, kleinanzeigen.py, makler_*.py
  scoring/        ai_match.py (Claude Haiku), lage.py (regelbasiert), risk.py
  notify/         telegram.py
  pipeline.py     Haupt-Pipeline (run_all, run_profile)
  scheduler.py    APScheduler — Interval aus DB, ändert sich ohne Container-Restart
  db.py           SQLAlchemy + SQLite
  config.py       Pydantic Settings (aus .env)
  web/
    server.py     FastAPI — SPA servieren + API-Routing
    api/          listings.py, settings.py, sources.py, system.py, telegram.py
    auth.py       HTTP-Basic (intern, Caddy ist primäre Auth-Schicht)
frontend/
  src/            React 18 + Vite + TypeScript + Tailwind CSS v3
  dist/           → app/web/static/dist/ (via npm run build)
scripts/
  verify_source.py   Selektoren testen ohne DB-Schreibzugriff
  run_once.py        Einzelner Crawl-Durchlauf (schreibt in DB)
  run_web.py         Dashboard lokal starten
  deploy.sh          rsync + docker compose up --build + Caddy-Config update
docs/
  backlog.md              Feature-Backlog (priorisiert)
  superpowers/specs/      Design-Specs
  superpowers/plans/      Implementierungs-Pläne
```

## Key Commands

```bash
# Lokales Setup
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium

# Selektoren prüfen (read-only, kein DB-Write) — VOR Prod-Lauf!
python -m scripts.verify_source immoscout24
python -m scripts.verify_source kleinanzeigen

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

## Stack

Python 3.11 · FastAPI · Playwright (Chromium) · SQLite/SQLAlchemy · APScheduler · anthropic SDK · Telegram Bot API · Docker · Caddy (Reverse Proxy + TLS + Auth)

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
