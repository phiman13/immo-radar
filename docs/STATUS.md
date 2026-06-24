# Status — immo-radar

> Kuratierter Stand-Snapshot (Kanon: *single fact, single place*). Offene Items →
> **Linear** (Team HER, Projekt `immo-radar`): `linear i list -P immo-radar`.
> Architektur-/Quellen-Detail: `CLAUDE.md`.

## Wo wir stehen

Immobilien-Aggregator für Tutzing (PLZ 82327 + 5 km): scrapt Portale, bewertet Objekte
per Claude (Haiku), sendet Telegram-Alerts. **Live unter immo.herrlich.dev** (Caddy
basicauth, Docker auf VPS, `127.0.0.1:8001`). Python/FastAPI + SQLite (Scraper +
Scoring + APScheduler) · React 18 + Vite Dashboard.

## Nächster Schritt & Backlog

Offene Items → **Linear** (HER-577/578 aus root-`BACKLOG.md` migriert). ⚠️ Der
**Feature-Backlog in `docs/backlog.md`** (Status-Matrix, Stand 2026-05-11, ~17 offene
Posten ☐/⏳) ist **noch nicht nach Linear triagiert** — bis dahin dort nachsehen.

## Branch-Map

- `main` — Deploy via `scripts/deploy.sh` (rsync + docker compose).
