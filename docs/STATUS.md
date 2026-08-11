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
Phase 0 (Vermessung), Phase 1 (Fundament), Phase 2a (Site-Onboarding —
Kaskaden-Klassifikation aus Phase 0 nach `app/agent_cascade_detect.py` +
`app/agent_probe.py` promoted, `app/agent_onboarding.py` schreibt Ergebnis
auf die `Agent`-Zeile, `scripts/onboard_agents.py` als manueller CLI-Trigger)
und Phase 2b (geteilter Feld-Extraktor in `app/agent_field_extract.py` +
Cascade-Handler in `app/sources/agent_handlers.py`, registriert in
`EXTRACTION_METHODS` (`app/sources/agents_adapter.py`) — `AgentSiteSource.fetch()`
liefert damit erstmals echte Listings statt einer leeren Registry; dazu
zweistufiger Selbsttest (Spec §7) und struktureller Crawl-Frequenz-Guard
`MIN_RECRAWL_INTERVAL`, der Makler-Sites unabhängig vom gewählten
Poll-Intervall auf max. ~1×/Tag begrenzt) sind abgeschlossen. HER-726
(feed_adapter-`listing_url`-Ausnahme im Coverage-Gate) ist mit Phase 2b
gefixt. Phase 2 ist in vier Teilpläne aufgeteilt. Nächster Schritt: Phase 2c
(Change-Gate-Fingerprint für „nur neue Objekte", Zwei-Läufe-Zähler für echte
Rezept-Bruch-Erkennung, Playwright-Rendering für JS-Shells/403-Sites — alle
drei in Phase 2b bewusst zurückgestellt, siehe Self-Review-Notizen im
Phase-2b-Plan). Bekannte Vorbedingung vor Phase 3/Discovery bleibt HER-725
(Domain-Validierung/SSRF-Guard auf `verified_domain`).

## Branch-Map

- `main` — Deploy via `scripts/deploy.sh` (rsync + docker compose).
