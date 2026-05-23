# Entwicklung — immo-radar (immo.herrlich.dev)

> Projekt-spezifischer Workflow (mittel — Eigenbedarf, deployed Scraping-Pipeline + Dashboard).
> On-demand gelesen — Pointer in `CLAUDE.md`. Universelle Baseline → `.claude/CONVENTIONS.md`.
> Basis-Commands + Struktur stehen in `CLAUDE.md` §Key Commands; diese Datei ergänzt
> Workflow-Disziplin + belegte Anti-Patterns.

## Workflow

**Backend (Python — Scraper, Pipeline, FastAPI):**

1. Bei Scraper-Änderung: **erst** `python -m scripts.verify_source <name>` — testet Selektoren ohne DB-Schreibzugriff. Niemals direkt deployen ohne diesen Schritt.
2. `ruff check .` grün (Konfig in `pyproject.toml`: Line-Length 110, Selects E/F/I/B/UP).
3. Optional: `pytest` aus `tests/` (asyncio_mode=auto).
4. Dashboard lokal: `python -m scripts.run_web` (Port 8000, kein Auth).

**Frontend (React/Vite/TS — Dashboard-SPA in `frontend/`):**

1. `cd frontend && npm run dev` (Port 5173, Proxy auf Backend :8000).
2. Vor Push: `npm run typecheck` (`tsc --noEmit`) + `npm run build` (`tsc -b && vite build`, baut nach `app/web/static/dist/`).

**Deploy auf VPS:**

- `bash scripts/deploy.sh` — rsync + `docker compose up --build`. Container bindet auf `127.0.0.1:8001`, Caddy proxiert `immo.herrlich.dev` mit Basic-Auth (`admin / tutzing2026!`).

## Review & Verifikation

- Scraper-Änderung: `verify_source` durchlaufen (Selektoren grün) — Pflicht vor Commit.
- Backend: `ruff check .` grün.
- Frontend: `cd frontend && npm run typecheck && npm run build` grün.
- **Monorepo-Caveat:** DoD-Commit-Hook (Sub-A.3) erzwingt `tsc --noEmit` nur, wenn Root-`tsconfig.json` existiert — hier sitzt es in `frontend/`, der Hook ist beim Commit aus dem Repo-Root daher No-Op. Frontend-Änderung darum aktiv typechecken (Schritt 2 oben).
- Nach Deploy: Smoke auf `immo.herrlich.dev` — Listings laden, Scheduler-Status korrekt, Telegram-Test-Alert kommt an.

## Anti-Patterns

- **Scraper-Deploy ohne `verify_source`:** Selektor-Drift fällt erst in Prod auf, wenn Listings leer kommen oder die Pipeline crasht. `python -m scripts.verify_source <name>` ist read-only und bricht früh ab, wenn die Selektoren nicht mehr matchen. Quelle: `CLAUDE.md` §Key Commands („VOR Prod-Lauf!").
- **Blocked-Quellen reaktivieren wollen:** `immoscout24`, `immowelt`, `sparkasse_immo` sind by-design „blocked" (Bot-Schutz). Nicht versuchen, durch Playwright/Custom-Headers zu umgehen — IS24 läuft nur via RSS, wenn `IMMOSCOUT24_SAVE_SEARCH_ID` gesetzt ist. Quelle: `CLAUDE.md` §Quellen-Status.

## Skills

<!-- A.2: Skill-Routing schärfen. AI-Scoring via Claude Haiku — Cost-Tracking in app/usage.py. -->
