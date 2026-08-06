# Status — immo-radar

> Kuratierter Stand-Snapshot (Kanon: *single fact, single place*). Offene Items →
> **Linear** (Team HER, Projekt `immo-radar`): `linear i list -P immo-radar`.
> Architektur-/Quellen-Detail: `CLAUDE.md`.

## Status: Aktiv (reaktiviert 2026-08-06)

Immobilien-Aggregator für Tutzing (PLZ 82327 + 5 km): scrapt Portale, bewertet Objekte
per Claude (Haiku), sendet Telegram-Alerts. Python/FastAPI + SQLite (Scraper +
Scoring + APScheduler) · React 18 + Vite Dashboard.

**Wiederbelebt.** War 2026-06-29 archiviert, lokale Weiterarbeit lief seither durch
(Probe/Scraper-Feature-Arbeit bis 2026-08-05). 2026-08-06 zurück in `targets.txt` +
Linear-Projekt entarchiviert, HER-577/578 zurück auf Todo. **VPS-Deployment weiterhin
abgeräumt** (Stand 2026-06-29, noch nicht neu aufgesetzt):
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

**Makler-Vollabdeckung** (`docs/superpowers/specs/2026-08-04-makler-vollabdeckung-design.md`):
Phase 0 (Vermessung), Phase 1 (Fundament) und Phase 2a (Site-Onboarding —
Kaskaden-Klassifikation aus Phase 0 nach `app/agent_cascade_detect.py` +
`app/agent_probe.py` promoted, `app/agent_onboarding.py` schreibt Ergebnis
auf die `Agent`-Zeile, `scripts/onboard_agents.py` als manueller CLI-Trigger)
sind abgeschlossen. Phase 2 ist in vier Teilpläne aufgeteilt. Nächster
Schritt: Implementierungsplan für Phase 2b (geteilter Feld-Extraktor +
Cascade-Handler in `EXTRACTION_METHODS` — macht `AgentSiteSource.fetch()`
erstmals echte Listings liefern). Bekannte Vorbedingungen für spätere
Phasen: HER-725 (Domain-Validierung vor Phase 3/Discovery), HER-726
(feed_adapter braucht `listing_url`-Ausnahme im Coverage-Gate, für Phase 2b).

## Branch-Map

- `main` — Deploy via `scripts/deploy.sh` (rsync + docker compose).
