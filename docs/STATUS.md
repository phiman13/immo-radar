# Status — immo-radar

> Kuratierter Stand-Snapshot (Kanon: *single fact, single place*). Offene Items →
> **Linear** (Team HER, Projekt `immo-radar`): `linear i list -P immo-radar`.
> Architektur-/Quellen-Detail: `CLAUDE.md`.

## Status: Archiviert (2026-06-29)

Immobilien-Aggregator für Tutzing (PLZ 82327 + 5 km): scrapt Portale, bewertet Objekte
per Claude (Haiku), sendet Telegram-Alerts. Python/FastAPI + SQLite (Scraper +
Scoring + APScheduler) · React 18 + Vite Dashboard.

**Projekt ruht.** VPS-Deployment vollständig abgeräumt (2026-06-29):
- Docker-Container + Image entfernt, `/opt/immo-radar` gelöscht
- Caddy-Vhost `immo.herrlich.dev` entfernt
- DB-Backup: `~/Downloads/immo-radar-db-backup-2026-06-29.sqlite`

## Wiederinbetriebnahme

```bash
# 1. Caddy-Vhost in /etc/caddy/Caddyfile eintragen (immo.herrlich.dev → :8001, basicauth)
# 2. Deploy
bash scripts/deploy.sh
```

## Offener Backlog

Offene Items → **Linear** (HER-577/578). Feature-Backlog: `docs/backlog.md`
(Stand 2026-05-11, ~17 Posten, noch nicht vollständig nach Linear triagiert).

## Branch-Map

- `main` — Deploy via `scripts/deploy.sh` (rsync + docker compose).
