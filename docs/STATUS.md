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
Linear-Projekt entarchiviert, HER-577/578 zurück auf Todo. **VPS-Deployment wieder live**
(neu aufgesetzt und deployed 2026-08-12, Fix-Redeploys seither via `scripts/deploy.sh`):
Container `web`/`worker` laufen, Caddy-Vhost `immo.herrlich.dev` aktiv. `poll_enabled`
ist seit 2026-08-14 wieder **aktiv** (12-Std.-Intervall) — Scheduler crawlt automatisch,
`enrich_enabled` lief bereits durchgehend.

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
gefixt. Phase 2 ist in vier Teilpläne aufgeteilt.

**Produktiv end-to-end verifiziert (2026-08-12/14):** alle 19 vom Nutzer benannten
Referenz-Makler onboarded (16 `auto-harvested`, 3 korrekt als nicht automatisierbar
geflaggt), echte Listings landen nachweislich im Dashboard. Dabei gefundener und
gefixter Produktionsbug: `pipeline.run_source()` hält für den gesamten Harvest-Lauf
eine offene SQLite-Schreibtransaktion — `AgentSiteSource` schrieb Agent-Status
(`last_checked` etc.) bisher über eine zweite, eigene Session und blockierte
zuverlässig mit „database is locked". Fix: `AgentSiteSource` nutzt jetzt dieselbe,
vom Aufrufer gereichte Session (`SourceAdapter.session`, Commit bleibt beim Aufrufer)
statt einen zweiten Schreiber zu öffnen — exakt das Muster, das `geocode()` für den
Geocoding-Cache bereits etabliert hatte. Regressionstest reproduziert den Lock
deterministisch ohne den Fix.

**Zwei weitere Produktionsbugs derselben Fehlerklasse gefunden und gefixt
(2026-08-14):** `pipeline._matches_profile()` und `scoring/ai_match.py` lasen
Preis-/Flächen-/Zimmer-/Baujahr-/Objektart-Filter aus der statischen
`app.config.settings` (.env-Wert bei Prozessstart) statt aus den
DB-persistenten Dashboard-Settings — eine Preisrahmen-Änderung im Dashboard
hatte dadurch **keinen** Effekt auf die tatsächliche Filterung. Fix: beide
nutzen jetzt `settings_service.get_setting()`/neuen Helper
`get_property_type_list()`. Derselbe Bug fand sich auch in
`scheduler.build_scheduler()` (Poll-/Enrich-Intervall aus `.env` statt DB) —
zusätzlich behoben durch einen `reconcile_intervals()`-Watchdog-Job, der
Intervalländerungen im Dashboard ohne Container-Neustart übernimmt (vorher
entgegen der CLAUDE.md-Doku nötig gewesen). Alle drei Fixes durch
Regressionstests abgesichert, die den Bug live am unveränderten Code
reproduzieren.

Nächster Schritt: Phase 2c (Change-Gate-Fingerprint für „nur neue Objekte",
Zwei-Läufe-Zähler für echte Rezept-Bruch-Erkennung, Playwright-Rendering für
JS-Shells/403-Sites — alle drei in Phase 2b bewusst zurückgestellt, siehe
Self-Review-Notizen im Phase-2b-Plan) sowie kleinere Extraktions-Präzisionslücken
im Feld-Extraktor (unvollständiges HTML-Entity-Decoding, zu gierige
city-Erkennung bei manchen Vendor-Templates). Bekannte Vorbedingung vor
Phase 3/Discovery bleibt HER-725 (Domain-Validierung/SSRF-Guard auf
`verified_domain`).

## Branch-Map

- `main` — Deploy via `scripts/deploy.sh` (rsync + docker compose).
