# Design-Spec: Makler-Vollabdeckung Phase 2c — Change-Gate, Rezept-Bruch-Erkennung, Playwright

**Datum:** 2026-08-16
**Status:** Freigegeben (User-Review 2026-08-16)
**Ziel-Repo:** immo-radar

---

## 1. Ziel

Phase 2b (`app/agent_field_extract.py` + `app/sources/agent_handlers.py`) macht
`AgentSiteSource.fetch()` erstmals echte Listings liefern. Drei Lücken blieben
dabei bewusst zurückgestellt (siehe Self-Review-Notizen in
`docs/superpowers/plans/2026-08-11-makler-vollabdeckung-phase2b-feld-extraktor-cascade-handler.md`):

1. **Change-Gate-Fingerprint** — jeder Harvest-Lauf holt bis zu
   `MAX_DETAIL_PAGES_PER_AGENT` (40) Detailseiten neu ab, unabhängig davon, ob
   das Objekt schon bekannt ist. Spec §8 verlangt "nur neue Objekte" — bisher
   gibt es nur DB-seitiges Dedup (`dedup_hash`), das Netzwerk-Requests nicht
   spart.
2. **Zwei-Läufe-Zähler für echte Rezept-Bruch-Erkennung** — Spec §7 verlangt
   eine Rückstufung auf `needs-manual-watch` erst nach **zwei** aufeinander-
   folgenden leeren/selbsttest-untauglichen Läufen. Aktuell toleriert
   `app/sources/agents_adapter.py` jeden einzelnen leeren Lauf unbegrenzt oft,
   ohne Zähler.
3. **Playwright-Rendering für JS-Shells/403-Sites** — vier Makler
   (Aigner Immobilien, Dahler & Company, Locate Immobilien, Imothek) stehen auf
   `needs-manual-watch`, vermutlich weil ihre Angebotslisten clientseitig
   gerendert werden oder eine WAF httpx-Requests blockt.

**Nicht-Ziel:** Delisting-Erkennung (`Listing.is_active` wird im gesamten
Code nirgends auf `False` gesetzt — bleibt so, ist kein Teil dieser Phase).
Kein Umgehen von Bot-Schutz, der auch echte Browser erkennt (siehe §4,
Go/No-Go-Probe).

---

## 2. Reihenfolge

Change-Gate → Zwei-Läufe-Zähler → Playwright — niedrigstes Risiko zuerst
(reine Effizienz, keine Verhaltensänderung nach außen), dann die
State-Machine-Verfeinerung (baut auf Change-Gates Persistenz-Idee auf),
Playwright zuletzt als komplexestes Stück mit echtem Recherche-Bedarf.

Alle drei Bausteine landen in **einem** Plan/einer Ausführung (User-Ent-
scheidung 2026-08-16) — sie sind architektonisch unabhängig, aber alle drei
patchen dieselbe Kernschleife (`AgentSiteSource.fetch()` +
`ExtractionMethod`-Handler), ein gemeinsamer Plan vermeidet drei separate
Merge-Konflikte auf denselben Dateien.

---

## 3. Change-Gate-Fingerprint

### 3.1 Kein neues Schema

Jede Agent-Listing landet bereits heute in `Listing` mit `url` und
`last_seen_at`; `source_id` kodiert die Agent-ID
(`f"agent-{agent_id}-{digest}"`, `app/sources/agent_handlers.py::_source_id`).
Daraus lässt sich pro Agent ableiten, welche URLs bekannt sind und wie
frisch — keine zweite Wahrheitsquelle, kein neues DB-Feld nötig.

### 3.2 Ablauf pro Agent-Lauf

1. `AgentSiteSource.fetch()` liest — in der ohnehin offenen Session — für
   den aktuellen Agenten alle bestehenden `{url: last_seen_at}` aus
   `Listing` (Filter: `source == "agents"` und
   `source_id.startswith(f"agent-{agent.id}-")`). Der literale Bindestrich
   direkt nach der ID verhindert Präfix-Kollisionen zwischen z.B. Agent 1
   und Agent 12/100 (`"agent-1-".startswith`-Vergleich matcht
   `"agent-12-..."` nicht, da an Position 8 `'-'` vs. `'2'` steht) — kein
   zusätzlicher Trennlogik-Aufwand nötig, nur bei der SQL-`LIKE`-Pattern-
   Konstruktion (`f"agent-{agent.id}-%"`) auf den Bindestrich achten.
2. Dieses Dict geht als neuer Parameter an den Handler. Die
   `ExtractionMethod`-Signatur erweitert sich von
   `Callable[[Agent, httpx.AsyncClient], AsyncIterator[RawListing]]` zu
   `Callable[[Agent, httpx.AsyncClient, dict[str, datetime]], AsyncIterator[RawListing]]`.
   Alle vier bestehenden Handler (`crawl_and_extract`,
   `sitemap_objekte_handler`, `structured_data_handler`,
   `feed_adapter_handler`) übernehmen den neuen Parameter.
3. Jeder Handler entdeckt wie bisher **alle** Objekt-URLs über die
   Listing-/Sitemap-/Feed-Seite (ein einzelner Request — unverändert, das ist
   nötig, um neue Objekte zu finden). Beim Detail-Fetch pro URL wird
   übersprungen, wenn die URL im `known_urls`-Dict steht **und**
   `now - known_urls[url] < REFRESH_WINDOW`. Gefetcht wird: alles Neue (nicht
   im Dict) + alles Überfällige (im Dict, aber älter als das Fenster).
4. **Canary-Regel:** Würde ein Lauf 0 Detail-Fetches auslösen (alle
   gefundenen URLs sind frisch), wird trotzdem die URL mit dem ältesten
   `last_seen_at` zwangsweise gefetcht. Ohne diese Regel liefert der Handler
   in einem "alles frisch"-Lauf 0 `RawListing`s, und der Selbsttest (§4)
   würde einen Rezept-Bruch vortäuschen, obwohl nur das Change-Gate gegriffen
   hat. Kostet höchstens 1 Extra-Request pro Agent pro Lauf.

### 3.3 Refresh-Fenster

`REFRESH_WINDOW = timedelta(days=7)` — Konstante neben
`MAX_DETAIL_PAGES_PER_AGENT` in `app/sources/agent_handlers.py`. Bei
täglichem Crawl heißt das: neue Objekte werden weiterhin sofort erfasst,
Preis-/Status-Refresh bestehender Objekte läuft wöchentlich statt täglich.
Das spart bei den meisten Maklern (wenige neue Objekte pro Tag, viele
bekannte) den Großteil der Detail-Requests, ohne die bestehende
Preisänderungs-Historie (`ListingHistory`, geschrieben in
`pipeline._upsert()`) zu verwässern — ein Objekt wird spätestens nach 7
Tagen erneut verifiziert, nie "eingefroren".

### 3.4 Auswirkung auf bestehenden Code

- `pipeline._upsert()` bleibt unverändert — eine übersprungene URL erzeugt
  schlicht keinen `RawListing` in diesem Lauf, es gibt nichts upzuserten.
- `Listing.is_active` bleibt `True` für übersprungene, weiterhin gültige
  Objekte (es wird ohnehin nie auf `False` gesetzt, siehe §1) —
  keine Verhaltensänderung.
- `Listing.last_seen_at` eines übersprungenen Objekts bleibt auf dem Stand
  des letzten echten Fetches stehen, bis es wieder an der Reihe ist. Das ist
  das korrekte Signal ("zuletzt verifiziert am"), keine Regression.

---

## 4. Zwei-Läufe-Zähler für echte Rezept-Bruch-Erkennung

### 4.1 Neues Feld

`Agent.consecutive_empty_runs: int` (Migration: neue Spalte, `default=0,
server_default="0"`, analog zu `last_listing_count`).

### 4.2 Logik in `AgentSiteSource.fetch()`

Ersetzt den bisherigen Zweig (Modul-Docstring-Abschnitt "Zweistufiger
Selbsttest", Zeilen 196–221 in `app/sources/agents_adapter.py`):

- **Selbsttest bestanden** (`_passes_self_test(harvested)` ist `True`):
  `consecutive_empty_runs` wird auf `0` zurückgesetzt. Bestehender
  Erfolgspfad (`last_checked`/`last_nonempty_at`/`last_listing_count`)
  unverändert.
- **Selbsttest fehlgeschlagen, `agent.last_nonempty_at is None`:**
  unverändert — sofortiger Downgrade auf `needs-manual-watch`
  (Erstaktivierungs-Selbsttest aus Phase 2a braucht keinen Streak, siehe
  bestehende Begründung im Docstring).
- **Selbsttest fehlgeschlagen, zuvor mindestens einmal erfolgreich:**
  `consecutive_empty_runs += 1`.
  - **Zähler nach Inkrement = 1:** bleibt `auto-harvested`, nur
    `last_checked` und der Zähler werden geschrieben — wie heute im
    Toleranz-Zweig, aber mit **Fall-Unterscheidung im Log** (siehe 4.3).
  - **Zähler nach Inkrement ≥ 2:** Downgrade auf `needs-manual-watch`,
    `coverage_reason` benennt explizit den Fall (a/b, siehe 4.3) und dass
    zwei aufeinanderfolgende Läufe betroffen waren.

### 4.3 Fall-Unterscheidung (a) vs. (b)

Bekannte Lücke aus den Phase-2b-Self-Review-Notizen: der bisherige
Toleranz-Zweig unterscheidet nicht zwischen

- **Fall (a):** Handler liefert 0 `RawListing`s (z.B. Listing-Seite nicht
  erreichbar, 0 Detail-Links gefunden) — vermutlich transienter
  Netzwerkfehler oder temporäre Blockade.
- **Fall (b):** Handler liefert N > 0 `RawListing`s, aber keins besteht
  `_passes_self_test` (Titel + Detail-Link + mind. ein Sachattribut) — z.B.
  nach einem Website-Relaunch, der Preis/Fläche aus dem Markup entfernt hat.
  Das ist ein echtes Rezept-Problem, kein Netzwerk-Flackern.

`_passes_self_test()` behält seine Signatur (`list[RawListing] -> bool`).
Die Fall-Unterscheidung passiert direkt am Aufrufer über
`len(harvested) == 0` (Fall a) vs. `len(harvested) > 0` (Fall b) — keine
Änderung an `_passes_self_test()` nötig.

Logging: Fall (a) bleibt `log.info` (heutiges Verhalten, vermutlich
transient). Fall (b) wird `log.warning` mit der Objektzahl — genau die im
Phase-2b-Plan vorgezeichnete Maßnahme ("mind. `log.warning` mit Objektzahl,
als Grundlage für den künftigen Zähler"). Der `coverage_reason` beim
finalen Downgrade (Zähler = 2) nennt den Fall des **letzten** Laufs.

---

## 5. Playwright-Rendering

### 5.1 Browser-Session statt Browser-pro-Request

`app/sources/browser.py::fetch_html()` startet pro Aufruf einen kompletten
Chromium-Prozess (production-erprobt via `app/sources/kleinanzeigen.py`).
Für bis zu 40 Detailseiten pro Agent wären das 40 Browser-Starts pro
Harvest-Lauf — zu teuer. Neuer Baustein in `app/sources/browser.py`:

```python
@asynccontextmanager
async def browser_session() -> AsyncIterator[Callable[[str, str | None], Awaitable[str]]]:
    """Öffnet EINEN Browser/Context für die gesamte Dauer des Context-Managers
    und liefert eine fetch(url, wait_selector=None)-Funktion, die alle Aufrufe
    darin teilt — vermeidet einen Browser-Neustart pro Detailseite
    (fetch_html() macht das pro Aufruf, tragbar für kleinanzeigen.py mit 2
    Suchseiten/Lauf, nicht für bis zu 40 Detailseiten/Agent)."""
```

Intern nutzt sie denselben `_browser()`-Context-Manager wie `fetch_html()`
(gleiche `launch()`-Argumente, gleicher User-Agent/Locale/Viewport) — öffnet
ihn aber einmal statt pro Aufruf, und öffnet/schließt nur je eine `page` pro
URL innerhalb dieser einen Session. Ein `page.goto()`-Timeout oder -Fehler
für eine einzelne URL wird abgefangen (wie `_fetch_detail_listing()` das
heute für `httpx` tut) und bricht die restliche Session nicht ab.

### 5.2 Anbindung an die Handler

`Agent.extraction["render"] = "browser"` — neuer, optionaler Sparse-Key
(analog zu `vendor`/`feed_url`/`sitemap_url`). Handler, die dieses Flag
sehen, nutzen `browser_session()` statt `httpx` für **sowohl** die
Listing-/Sitemap-Seite **als auch** jede Detailseite desselben Agenten in
einer gemeinsamen Session — WAF-Blocks greifen typischerweise auf beiden
Ebenen, ein gemischter Modus (Listing per httpx, Details per Playwright)
würde beim ersten Schritt schon scheitern.

Betroffen: `crawl_and_extract` (der Handler hinter allen `vendor:<x>`- und
`detail_links`-Method-Keys — die vier Ziel-Sites laufen aktuell alle über
diesen Pfad oder würden bei erfolgreicher Neu-Klassifikation dort landen).
`sitemap_objekte_handler`/`structured_data_handler`/`feed_adapter_handler`
bekommen den Flag-Check aus Konsistenzgründen ebenfalls, auch wenn keiner
der vier Ziel-Sites aktuell auf diesen Pfaden klassifiziert ist.

### 5.3 Go/No-Go-Probe vor der Handler-Integration

Risiko: "bot-blocked" (Aigner Immobilien) kann eine WAF sein, die auch
Headless-Chromium fingerprinted und weiterhin blockt — Playwright behebt
das dann **nicht**, und die gesamte Handler-Integration wäre für diesen
Fall nutzlos gebaute Infrastruktur.

Deshalb ist der **erste Task** dieses Abschnitts ein reiner Probe-Schritt
(kein Produktionscode): alle vier Ziel-Sites einmal über `browser_session()`
anfragen (Listing-Seite reicht), prüfen ob echter Objekt-Content
durchkommt (Detail-Links per `find_detail_links()` erkennbar, kein
Block-/Challenge-Seiten-Marker). Ergebnis pro Site wird dokumentiert
(Kommentar im Plan-Ledger oder Commit-Message reicht, kein eigenes Doku-
Artefakt nötig). Nur Sites, bei denen die Probe echten Content liefert,
werden in Task 2+ auf `render: "browser"` umgestellt und (nach manueller
Prüfung der Kaskadenstufe wie bei jedem Onboarding) auf `auto-harvested`
gesetzt. Für den Rest bleibt `needs-manual-watch`, mit einem
`coverage_reason`, der das Probe-Ergebnis nennt statt stillschweigend eine
Nichtlösung anzunehmen.

### 5.4 Kosten/Timeouts

`timeout_ms=30000` (wie `fetch_html()`-Default) pro Seite,
`MAX_DETAIL_PAGES_PER_AGENT=40` bleibt unverändert (durch das Change-Gate
aus §3 ohnehin meist deutlich niedriger als 40 tatsächliche Fetches pro
Lauf). Playwright-Agents laufen wie alle Agents unter
`MIN_RECRAWL_INTERVAL` (~1×/Tag) — ein einzelner Lauf, der pro Agent im
Worst Case einige Minuten dauert, ist für einen Hintergrund-Job in dieser
Frequenz akzeptabel.

---

## 6. Fehlerbehandlung

Unverändert gegenüber Phase 2b: jeder Agent wird isoliert verarbeitet
(`try/except` pro Agent-Iteration in `fetch()`), ein fehlschlagender Makler
bricht nie den Gesamtlauf ab. Das Change-Gate und der Zwei-Läufe-Zähler
ändern nichts an dieser Isolation — sie greifen innerhalb desselben
try-Blocks. Playwright-Fehler (Browser-Start, Seiten-Timeout) werden wie
`httpx`-Fehler behandelt: pro-URL abgefangen, geloggt, übersprungen; ein
kompletter Browser-Session-Fehlschlag (z.B. Chromium-Start schlägt fehl)
propagiert bis zum bestehenden Agent-Try/Except und zählt als regulärer
Lauf-Fehlschlag (aktualisiert `last_checked`, `coverage_status`
unverändert — identisch zum bestehenden `except Exception`-Zweig in
`fetch()`).

---

## 7. Tests

`app/sources/browser.py` und `app/sources/kleinanzeigen.py` haben aktuell
**keine** Tests — kein Playwright-Mocking-Vorbild im Projekt. Neues Muster:
Modul-Level-Monkeypatch von `browser_session` (bzw. der internen
`_browser()`-Funktion) auf ein Fake, das vordefinierte HTML-Strings pro URL
zurückgibt — kein echter Chromium-Start in Unit-Tests.

Change-Gate und Zwei-Läufe-Zähler folgen dem etablierten Testmuster dieses
Projekts: SQLite-`tmp_path`-Fixture, `AsyncMock`-URL-Routing für `httpx`
(wie `tests/test_agent_probe.py`, `tests/test_agents_adapter.py`),
`EXTRACTION_METHODS.clear()`-Autouse-Fixture wo zutreffend.

Mindestabdeckung pro Baustein:
- Change-Gate: bekannte+frische URL wird übersprungen; bekannte+überfällige
  URL wird gefetcht; neue URL wird immer gefetcht; Canary-Regel greift bei
  "alles frisch".
- Zähler: Reset bei Erfolg; Zähler=1 bleibt `auto-harvested`; Zähler=2 löst
  Downgrade aus; Fall (a) vs. (b) landet im richtigen Log-Level und im
  `coverage_reason`.
- Playwright: `browser_session()` liefert HTML für gemockte URLs; ein
  Seiten-Fehler unterbricht nicht die restliche Session; das
  `render`-Flag steuert den Dispatch in `crawl_and_extract` korrekt.

---

## 8. Explizit außerhalb dieser Phase

- **Delisting-Erkennung** (`is_active` auf `False` setzen, wenn ein Objekt
  nicht mehr im Quell-Crawl erscheint) — separates Feature, nicht Teil des
  Change-Gates.
- **LLM-Rezept für die `learned_recipe`-Stufe** — Phase 2d.
- **Refactor der vier bestehenden Portal-Adapter** auf den geteilten
  Extraktor — weiterhin bewusst zurückgestellt (Phase-2b-Scope-Entscheidung,
  gilt unverändert).
- **Discovery (Phase 3)** — Vorbedingung (HER-725) ist erfüllt, aber diese
  Phase befasst sich ausschließlich mit der Härtung bestehender Makler.
