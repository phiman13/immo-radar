# Status-Archiv — immo-radar

> Detailhistorie des kuratierten Stand-Snapshots (`docs/STATUS.md`). Reiner
> Nachschlag-Ort — der aktuelle Stand steht ausschließlich in `STATUS.md`.

## Stand bis zur Stilllegung (2026-08-18)

Immobilien-Aggregator für Tutzing (PLZ 82327 + 5 km): scrapt Portale, bewertet Objekte
per Claude (Haiku), sendet Telegram-Alerts. Python/FastAPI + SQLite (Scraper +
Scoring + APScheduler) · React 18 + Vite Dashboard.

**Wiederbelebt.** War 2026-06-29 archiviert, lokale Weiterarbeit lief seither durch
(Probe/Scraper-Feature-Arbeit bis 2026-08-05). 2026-08-06 zurück in `targets.txt` +
Linear-Projekt entarchiviert, HER-577/578 zurück auf Todo. **VPS-Deployment wieder live**
(neu aufgesetzt und deployed 2026-08-12, Fix-Redeploys seither via `scripts/deploy.sh`):
Container `web`/`worker` liefen, Caddy-Vhost `immo.herrlich.dev` aktiv. `poll_enabled`
war seit 2026-08-14 aktiv (12-Std.-Intervall) — Scheduler crawlte automatisch,
`enrich_enabled` lief bereits durchgehend.

## Offener Backlog (Stand vor Stilllegung)

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

**UI-Funktionsprüfung abgeschlossen (2026-08-14/16, HER-804 + 15 Sub-Issues,
alle Done):** vollständige funktionale Prüfung des Dashboards (Code-Lektüre
aller Frontend-Dateien + Backend-Module, echter Klick-Durchlauf gegen
Produktion) fand 4 Blocker (u.a. Quellen-„Aktiv"-Schalter ohne Wirkung,
Objekttyp-Filter-Bug, hartkodierter Regionsfilter überstimmte die
Suchgebiet-UI), 5 Major- und 6 Minor/Kosmetik-Befunde. Alle gefixt, per
Regressionstest abgesichert und live auf Produktion verifiziert — Details
und Belege je Ticket in Linear (HER-805 bis HER-818, HER-820). Dabei auch
die in Phase 2b zurückgestellten Extraktions-Präzisionslücken (HTML-Entity-
Decoding, gierige city-Erkennung, Makler-Büroadresse statt Objektadresse)
mit erledigt.

**HER-725 (SSRF-Guard auf `verified_domain`) gefixt (2026-08-16):** die
bekannte Vorbedingung vor Phase 3/Discovery ist erfüllt — `app.agent_probe`
validiert jede Domain (strikte Hostname-Whitelist, keine IP-Literale, keine
reservierten/internen TLDs) vor jedem Netzwerk-Call.

**Phase 2c (Change-Gate, Zwei-Läufe-Zähler, Playwright) abgeschlossen
(2026-08-17):** Change-Gate-Fingerprint (`_urls_to_fetch()` in
`app/sources/agent_handlers.py`) überspringt bekannte, frische
Detailseiten (7-Tage-Refresh-Fenster) in `crawl_and_extract`,
`sitemap_objekte_handler` und `structured_data_handler` — mit
Canary-Regel (3 älteste bekannte URLs statt aller, damit der Selbsttest
nie fälschlich einen Rezept-Bruch erkennt, wenn nur das Gate gegriffen
hat). `feed_adapter_handler` bekommt bewusst KEIN Change-Gate (spart dort
keine Netzwerk-Requests, da der Feed ohnehin komplett geholt wird —
würde nur die Selbsttest-Stichprobe verkleinern). Zwei-Läufe-Zähler
(`Agent.consecutive_empty_runs`) ersetzt den bisherigen
Ein-Lauf-Toleranz-Zweig: Downgrade auf `needs-manual-watch` erst nach
zwei aufeinanderfolgenden Läufen ohne Selbsttest-Erfolg (Spec §7), mit
Fall-Unterscheidung im Log (0 Objekte vs. Objekte ohne Sachattribut).
`browser_session()` (`app/sources/browser.py`) erlaubt Playwright-Fetches
mit einem wiederverwendeten Browser statt Neustart pro Seite; ein
`render:"browser"`-Flag verzweigt `crawl_and_extract` entsprechend.

**Go/No-Go-Probe der 4 ursprünglich anvisierten JS-Shell-/Bot-Sites
(Aigner Immobilien, Dahler & Company, Locate Immobilien, Imothek) ergab
0/4 Go** — aber keinen Fehlschlag ohne Erkenntnis: Aigner ist ein echter
WAF-Block, der auch Headless-Chromium erkennt (`render:"browser"` hilft
dort nicht). Dahler braucht nur eine korrigierte `listing_url` (die
aktuelle zeigt auf eine Marketing-Seite ohne Objekte), kein Playwright.
Locate und Imothek laden echten Content ohne Bot-Block, brauchen aber
strukturell andere Extraktionsansätze (Modal-basierte UI bzw.
JSON-Payload in einem Livewire-Attribut statt `<a href>`-Detail-Links) —
Kandidaten für eine künftige, eigene Handler-Klasse, kein Dead End.
`render:"browser"` bleibt als wiederverwendbare Infrastruktur für
künftige, tatsächlich passende Sites bestehen.

**Kritischer Fund im finalen Branch-Review, vor Merge gefixt:** eine
einzelne Canary-URL (Größe 1) konnte bei einem Selbsttest-Fehlschlag
genau dieser einen Seite zu einem TERMINALEN Downgrade führen (der
Agent wird danach nie wieder automatisch gecrawlt, da `fetch()` nur
`auto-harvested`-Agents selektiert) — end-to-end reproduziert, mit
Canary-Stichprobe 3 statt 1 behoben. Zusätzlich: Reaktivierung über
`scripts/onboard_agents.py` setzte den Zähler nicht zurück (der
dokumentierte Reparaturweg war dadurch wirkungslos) — mitgefixt.

## Stilllegungs-Analyse (2026-08-18)

Zwei Tage nach Abschluss von Phase 2c und Live-Deploy meldete der Nutzer eine
klar irrelevante Telegram-Benachrichtigung (Objekt 90 km außerhalb des
Suchgebiets, Score 15/100). Root-Cause-Untersuchung (systematic-debugging)
ergab zwei unabhängige Befunde:

1. Geocoding-Fail-Open (`pipeline.py` + `scoring/lage.py::in_search_area()`,
   beide bewusst „lieber ein Ausreißer als eine gute Immobilie verpasst")
   lässt Objekte ohne erfolgreiche Geocodierung ungefiltert durch.
2. `Listing.lage_score` — die vom Telegram-Notify-Schwellwert geprüfte Spalte
   und ein im Dashboard konfigurierbares Setting — wird im gesamten Backend
   **nie geschrieben** (verifiziert per vollständiger Git-Historie von
   `app/enrich.py`: kein Commit setzt dieses Feld je). Der Schwellwert-Gate
   in `notify_new_listing()` war seit dem allerersten Commit ein No-op.

Die anschließende Inhaltsprüfung der 13 Listings aus der Makler-Kaskade (dem
eigentlichen Alleinstellungsmerkmal des Projekts: Objekte, die ausschließlich
bei einzelnen Maklern stehen, nie auf ImmoScout/Kleinanzeigen) ergab:

- 6 von 13 (46 %) bereits verkauft (von der KI im Fließtext erkannt, vom
  System nicht — keine Delisting-Erkennung existiert, in mehreren Phasen
  bewusst zurückgestellt, nie gebaut).
- 11 von 13 (85 %) ohne extrahierten Preis.
- Mehrere außerhalb des 5-km-Suchgebiets (Andechs, Weilheim, Tegernsee,
  Murnau am Staffelsee), trotz bestandenem Regionsfilter.
- Höchster Score (72/100) für eine Mietwohnung, nicht Kauf.
- Kein einziges Listing aus der gesamten Makler-Kaskade: unverkauft,
  korrekt lokalisiert, vollständig erfasst UND mit brauchbarem Score.
- Ob die verbleibenden Objekte überhaupt exklusiv sind (nicht zusätzlich auf
  ImmoScout/Immowelt gelistet), blieb ungeklärt — die Datenqualität ließ das
  nicht sinnvoll prüfen.

Zusatzbefund: seit Wiederinbetriebnahme (12.08., Neuaufsetzen der VPS) und
vier Tagen Echtbetrieb kein einziges Listing durch den Nutzer bearbeitet
(Status überall „new", keine Notiz gesetzt) — kein Engagement-Signal.

**Schlussfolgerung, vom Nutzer geteilt:** das Kernversprechen (exklusive,
sonst nicht auffindbare Makler-Objekte finden) trägt aktuell nicht — nicht
wegen einzelner Bugs, sondern weil trotz erheblicher Ingenieursarbeit über
mehrere Phasen (Extraktions-Kaskade, Selbsttest, Change-Gate, Playwright-
Infrastruktur) die Basisqualität (Preis, Verkauft-Status, Ortsangabe) nie
zuverlässig wurde. Entscheidung: Stilllegung statt Fortsetzung des
bisherigen Musters „mehr Abdeckung bauen, ohne bestehende Qualität zu
sichern". Details zur Stilllegung selbst → `docs/STATUS.md`.
