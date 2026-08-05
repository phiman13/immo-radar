# Design-Spec: Makler-Vollabdeckung

**Datum:** 2026-08-04
**Status:** Entwurf zur Freigabe
**Ziel-Repo:** immo-radar

---

## 1. Ziel

Zuverlässige Erfassung aller Kaufobjekte im Raum Tutzing / Starnberger See, die
**ausschließlich auf makler-eigenen Websites** inseriert sind und damit auf
ImmoScout24, Immowelt & Co. nie auftauchen. Zweitziel: nachvollziehbar machen,
welcher Anteil des Maklermarkts automatisiert erfasst ist — und welche Makler
manuell beobachtet werden müssen.

**Nicht-Ziel:** Umgehung von Bot-Schutz, Login-Wällen oder Paywalls. Gesperrte
Quellen werden als solche geführt, nicht technisch eskaliert.

---

## 2. Ausgangslage (empirisch verifiziert am 2026-08-04)

| Befund | Beleg |
|---|---|
| Statische Adapter-Registry; DB-Quellen (`source_type="suggested"`) werden nie gecrawlt | `app/sources/registry.py:11`, `get_all_adapters()` |
| `Source`-Modell hat kein Feld für Selektoren, Rezepte oder Coverage-Status | `app/db.py:114-124` |
| `/discover` fragt Claude aus dem Modellgedächtnis, max. 6 Vorschläge, ohne Websuche | `app/web/api/sources.py:272-295` |
| `/analyze` stellt nur fest, *ob* Inserate vorhanden sind — kein Extraktions-Rezept | `app/web/api/sources.py:180-264` |
| Kein Adapter setzt `lat`/`lon` → `in_search_area()` gibt immer `True` zurück | `app/scoring/lage.py:46-47`; kein `lat=` in `app/sources/*.py` |
| Realer Regionsfilter ist eine hartkodierte Ortsnamen-Regex, entkoppelt vom Suchprofil-UI | `app/pipeline.py:19-33` |
| 2 von 5 aktiven Quellen liefern 0 Objekte; Kleinanzeigen liefert bundesweit; Riedel liefert 260 München-Objekte | Live-`verify_source`-Lauf |
| Nach 2 Monaten Produktivbetrieb: 18 Listings gesamt | DB-Backup vom 2026-06-29 |
| Makler-Verzeichnisse geben die maklereigene Homepage **nicht** heraus — auch nicht auf Profil-Detailseiten | Probe gegen `makler-empfehlung.de` (207 Einträge), `ortsdienst.de`, `stadtbranchenbuch`, `starnbergersee-info.de` |

**Schlussfolgerung:** Der Engpass ist die Beschaffung, nicht das Frontend oder das
Scoring. Discovery-Vorschläge landen heute in einer Liste, die nichts erntet.

---

## 3. Getroffene Entscheidungen

| Frage | Entscheidung |
|---|---|
| Makler-Kreis | **Weit** (~200-250 Sites, inkl. Münchner Makler mit Seeobjekten); Regionsfilter erst auf Objektebene |
| Aufnahme neuer Makler | **Hybrid mit Selbsttest** — automatisch aktiv bei nachweislich plausiblen Objekten; Review-Queue nur für Zweifelsfälle |
| Crawl-Frequenz | **Täglich** (1 Lauf/Tag) |
| Transparenz | Nicht automatisierbare Makler müssen im Dashboard sichtbar sein, mit Grund und Link |
| Extraktions-Strategie | **Kaskade** — Standards zuerst, gelerntes Rezept als letzte Stufe |
| Höflichkeit | `robots.txt` respektieren, erkennbarer Bot-User-Agent, Crawl-Budget pro Host |

---

## 4. Architektur

### 4.1 Die Extractor-Kaskade

Kernentscheidung: Ein LLM-gelerntes Selektor-Rezept ist die **teuerste und
brüchigste** Stufe und kommt deshalb zuletzt. Vorher werden Mechanismen versucht,
die viele Makler-Sites teilen, weil sie dieselbe Immobiliensoftware oder dieselben
Web-Standards einsetzen.

> **Durch Phase 0 empirisch bestätigt und neu gewichtet (2026-08-05).**
> Messgrundlage: 28 Makler-Sites, siehe `docs/superpowers/phase0-messbericht.md`.

```
site_probe (einmalig pro Makler, wiederholbar)
   │
   ├─ 1. feed_adapter          Objekt-Feed / OpenImmo-XML          →  gemessen:  4 %
   ├─ 2. vendor_adapter        Fingerprint der Immobiliensoftware  →  gemessen: 50 %  ◀ Hauptstufe
   ├─ 3. structured_data       JSON-LD RealEstateListing           →  gemessen: 12 %
   ├─ 4. sitemap/detail_links  Objekt-URLs aus Sitemap oder Liste  →  gemessen: ~30 % (Fallback)
   ├─ 5. learned_recipe        LLM lernt Selektoren                →  Rest, ~25 %
   └─ 6. none                  → coverage_status = needs-manual-watch

   quer zu allen Stufen: browser_rendering (Playwright) statt httpx,
   wenn die Site JS-gerendert ist oder httpx mit 403 abgewiesen wird
```

Jede Stufe liefert entweder `RawListing`-Objekte oder gibt an die nächste ab. Die
erfolgreiche Stufe wird als `extraction_method` im Makler-Profil festgehalten und
bei Folgeläufen direkt angesprungen — die Kaskade läuft nur bei Erstkontakt und
bei Bruch erneut.

**Was die Messung an der ursprünglichen Annahme korrigiert hat:**

- **Stufe 2 ist die tragende Stufe, nicht Stufe 1.** 50 % der erreichbaren Sites
  tragen einen Vendor-Fingerprint, und **fünf Systeme decken sie vollständig ab**:
  immonex Kickstart, onOffice, OpenImmo2WP, Propstack, WP-ImmoMakler. Fünf
  Adapter ersetzen die Hälfte aller sonst nötigen Einzelrezepte, und sie brechen
  nicht beim Relaunch einer einzelnen Maklerseite.
- **OpenImmo-XML ist nicht abrufbar.** Null von 24 Sites liefern die Datei
  öffentlich, obwohl mehrere sie nachweislich importieren. Die Hoffnung auf
  strukturierte Volldaten als Hauptkanal ist widerlegt; OpenImmo bleibt nur als
  Fingerprint wertvoll.
- **Objekt-Feeds sind Einzelfälle, aber gratis.** Genau eine Site liefert Objekte
  über den WordPress-Feed. Stufe 1 bleibt trotzdem drin — ein `/feed/`-Abruf
  kostet nichts, und der Kanal ist der stabilste von allen.
- **Browser-Rendering wird Querschnittsfunktion, keine eigene Stufe.** Drei Sites
  weisen `httpx` mit HTTP 403 ab — auch mit Chrome-User-Agent, der Block sitzt
  tiefer (TLS-/HTTP-Fingerprint). Playwright ist im Projekt vorhanden und löst
  das ohne Verschleierungstechnik.
- **Die Angebotsseite zu finden ist unkritisch.** 23 von 24 Übersichtsseiten
  wurden allein per Pfad- und Linktext-Heuristik lokalisiert — kein LLM nötig.

### 4.2 Change-Gate (Kostenbremse)

Ein Fingerprint verhindert, dass täglich 200 Sites voll extrahiert werden.

**Der Fingerprint wird über das kanonische Objekt-Set gebildet**, nicht über das
Roh-HTML: sortierte Detail-URLs plus Preis/Fläche je Objekt, gehasht. Roh-HTML
wäre unbrauchbar — Tracking-IDs und Build-Hashes würden den Gate täglich
fälschlich auslösen, während eine JS-Shell ihn fälschlich stumm hielte.

Unverändert → kein Ingest, kein Enrichment. Verändert → Delta verarbeiten.

### 4.3 Objekt-Regionsfilter (Reparatur)

Der heutige Filter ist eine statische Regex, vom Suchprofil-UI entkoppelt. Da wir
den Makler-Kreis bewusst weit fassen, trägt dieser Filter ab jetzt die gesamte
Last der Regionsabgrenzung und muss echt funktionieren:

1. **Geocoding beim Ingest** — Adresse/PLZ → Koordinaten via Nominatim, mit
   persistentem Cache (Adress-Hash → lat/lon), damit Wiederholungen kostenlos sind.
2. `in_search_area()` greift damit real gegen das Suchprofil (Multi-Ort + Radien).
3. Die Ortsnamen-Regex bleibt als **Vorfilter** vor dem Geocoding (spart Requests)
   und als Fallback bei fehlgeschlagenem Geocoding — nicht mehr als Hauptfilter.
4. `geocode_confidence` und `region_match_reason` werden am Listing gespeichert,
   damit nachvollziehbar ist, warum ein Objekt drin oder draußen ist.

---

## 5. Datenmodell

### 5.1 Neue Tabelle `agents` (Makler-Entität + Coverage-Register)

Bewusst schlank gehalten — ein privates Tool, kein CRM.

| Feld | Zweck |
|---|---|
| `id`, `name`, `city` | Identität |
| `discovery_sources` (JSON) | Woher der Makler stammt (Verzeichnis, Websuche, aus Listing abgeleitet) — mehrere Belege erhöhen Vertrauen |
| `verified_domain` | Aufgelöste, verifizierte Homepage (`NULL` = noch nicht aufgelöst) |
| `domain_candidates` (JSON) | Kandidaten aus der Websuche, falls Verifikation scheitert |
| `imprint_match` (bool) | Impressum bestätigt Name/Ort |
| `listing_url` | Angebotsseite (Ergebnis des Probes) |
| `extraction` (JSON) | `{method, vendor, feed_url, sitemap_url, selectors, needs_browser}` |
| `recipe_verified_at` | Wann das Rezept zuletzt nachweislich Objekte lieferte |
| `coverage_status` | `unknown` \| `auto-harvested` \| `needs-manual-watch` \| `unreachable` \| `bot-blocked` \| `login-required` \| `robots-disallowed` |
| `coverage_reason` | Klartext, im Dashboard sichtbar |
| `robots_status` | Was `robots.txt` erlaubt |
| `last_checked`, `last_nonempty_at`, `last_listing_count` | Staleness-Erkennung |
| `next_review_due` | Wann der Status neu zu prüfen ist |

**`unknown` ist der Default und zählt nie als abgedeckt.** Ein Status gilt nur mit
frischem Beleg (`last_checked` innerhalb des Staleness-Fensters).

### 5.2 Abdeckungsquote — ehrlich statt schmeichelhaft

Der Nenner ist **nicht** eine einzelne Verzeichnisliste (207 Einträge sind nicht
„alle Makler"), sondern die **Vereinigung aller Discovery-Kanäle**. Angezeigt wird:

```
Bekannte Makler:        243
├─ automatisch erfasst: 168  (69 %)
├─ manuell beobachten:   31  (13 %)  ← klickbare Liste mit Grund + Link
├─ nicht erreichbar:      9
└─ ungeprüft/veraltet:   35  (14 %)  ← zählt NICHT als abgedeckt
```

Die Prozentzahl beantwortet damit „wie viel weiß ich sicher", nicht „wie gut sieht
es aus".

### 5.3 Bestehende Tabellen

`sources` bleibt für die vorhandenen Portal-Adapter (kleinanzeigen etc.) bestehen.
Makler-Sites laufen über `agents`. Kein Big-Bang-Umbau: der generische
Makler-Adapter tritt **neben** die Registry, nicht an ihre Stelle.

---

## 6. Discovery-Pipeline

Zweistufig, weil Verzeichnisse die Homepage nicht herausgeben (Befund oben):

1. **Seeds sammeln** aus mehreren Kanälen, damit kein Kanal zum blinden Fleck wird:
   - Makler-Verzeichnisse (`makler-empfehlung.de`, `ortsdienst.de`, Stadtbranchenbuch, `starnbergersee-info.de`)
   - Websuche nach Ortsnamen + „Immobilienmakler"
   - Makler, die in bereits erfassten Listings als Anbieter auftauchen
   - Bank-/Sparkassen-/Franchise-Netze (Von Poll, Engel & Völkers, Dahler …)
2. **Domain auflösen** — pro Maklername eine Websuche, Kandidaten sammeln.
3. **Verifizieren** — Impressum abrufen, Name + Ort abgleichen. Nur bei Treffer
   wird `verified_domain` gesetzt; sonst bleibt der Makler mit
   `coverage_status = unknown` und seinen `domain_candidates` stehen.

Discovery läuft **nicht** täglich, sondern wöchentlich (der Maklermarkt ändert
sich langsam) und ist manuell im Dashboard auslösbar.

---

## 7. Fehlerbehandlung & Bruch-Erkennung

- **Isolation:** Ein fehlschlagender Makler bricht nie den Gesamtlauf ab. Fehler
  → `coverage_status` + `coverage_reason`, Lauf geht weiter.
- **Bruch-Erkennung:** Lieferte ein Makler zuvor Objekte und jetzt an **zwei
  aufeinanderfolgenden Läufen** null, gilt das Rezept als gebrochen → Kaskade
  läuft erneut. Bleibt sie erfolglos → `needs-manual-watch` mit Grund.
- **Selbsttest vor Aktivierung:** Ein Rezept wird aktiv, wenn es ≥ 1 Objekt mit
  Titel **und** Detail-Link **und** mindestens einem Sachattribut (Preis *oder*
  Fläche) liefert, ohne absurde Duplikatquote.
  **Fehlende Preise sind kein Fehlschlag.** Viele Makler schreiben bei Seeobjekten
  grundsätzlich „Preis auf Anfrage" — der Live-Lauf gegen `bs_immo` lieferte zwei
  echte Objekte mit 0 % Preisabdeckung. Ein Preis-Schwellwert würde funktionierende
  Adapter aussortieren. Die Preisquote wird stattdessen als `field_completeness`
  am Makler festgehalten und im Dashboard angezeigt.
- **Kein stiller Verlust:** Jede Abbruchursache landet im Coverage-Register und
  ist im Dashboard sichtbar.

---

## 8. Recht & Betrieb

Bei ~200 fremden Websites ist das kein Beiwerk:

- **Erkennbarer User-Agent** mit Kontakt-URL. Der heutige Chrome-Fake in
  `app/sources/base.py:30` widerspricht der Höflichkeits-Zusage und wird ersetzt.
- **`robots.txt`** wird pro Lauf gelesen und respektiert; Disallow →
  `coverage_status = robots-disallowed`, kein Abruf. Relevant auch als
  maschinenlesbarer Nutzungsvorbehalt i. S. v. § 44b UrhG.
- **Keine Umgehung** von Bot-Schutz, Captchas oder Logins.
- **Sparsame Speicherung:** Fakten, URLs, kurze Beschreibungs-Auszüge. Keine
  dauerhafte Speicherung von Bildern oder Exposé-PDFs — das reduziert die
  Angriffsfläche gegenüber dem Datenbankherstellerrecht (§ 87b UrhG).
- **Crawl-Budget:** ein Abruf pro Host und Lauf für die Angebotsseite; Detailseiten
  gedrosselt und nur für neue Objekte.
- **Opt-out-Liste:** Ein Makler, der Kontakt aufnimmt, wird dauerhaft ausgeschlossen.
- **Privater Gebrauch:** Das Tool dient ausschließlich der privaten
  Immobiliensuche. Maklernamen sind teils personenbezogene Daten — sie werden nur
  gespeichert, soweit für die Zuordnung nötig, und nicht veröffentlicht.

---

## 9. Kosten & Modellwahl

Preise Stand 2026-06 (Anthropic First-Party):

| Modell | Input $/MTok | Output $/MTok |
|---|---|---|
| Claude Haiku 4.5 | 1,00 | 5,00 |
| Claude Sonnet 5 | 3,00 | 15,00 |

**Rezept-Lernen (Stufe 5): Claude Sonnet 5.** HTML-Struktur analysieren und
robuste Selektoren ableiten ist deutlich anspruchsvoller als Klassifikation, und
es fällt pro Makler nur **einmal** an. Bei ~200 Sites × ca. 10k Input- und 1k
Output-Token: **rund 9 $ einmalig**. Mit Haiku wären es ~3 $ — die Ersparnis
rechtfertigt kein brüchigeres Rezept, das dauerhaft Wartung erzeugt.

**AI-Match-Scoring: bleibt Haiku 4.5** (Bestand, Massengeschäft auf wenigen
Objekten pro Tag).

**Laufende Kosten:** Durch Kaskade und Change-Gate fällt im Normalbetrieb *kein*
LLM-Call fürs Crawling an — nur bei Rezeptbruch (geschätzt wenige pro Monat) und
für das Enrichment tatsächlich neuer Objekte im Suchgebiet. Erwartung: **deutlich
unter 5 $/Monat.** Das Crawling ist damit nicht der Kostentreiber.

---

## 10. Umsetzungsphasen

### Phase 0 — Vermessung ✅ abgeschlossen (2026-08-05)

**Ergebnis: `docs/superpowers/phase0-messbericht.md`**, Rohdaten in
`phase0-probe.json`, Werkzeug in `scripts/probe_agent_sites.py`. Die
Kaskaden-Gewichte in Abschnitt 4.1 beruhen auf diesen Messwerten. Der Bau
beginnt mit den fünf Vendor-Adaptern statt mit dem LLM-Rezept.

<details>
<summary>Ursprüngliche Planung der Phase</summary>


**Woher die Stichprobe kommt:** Die Domain-Auflösung (Phase 3) existiert noch
nicht, und Verzeichnisse geben keine Homepages heraus — die Stichprobe wird
deshalb durch einen **manuellen Websuche-Durchgang** gewonnen (eine Handvoll
Abfragen der Form „Immobilienmakler <Ort>" über die Orte des Suchgebiets). Der
Probelauf dieser Session hat das bereits bestätigt: eine einzelne Suche lieferte
direkt verwertbare Makler-Domains (u. a. `loeger-immobilien.de`, `graef-immo.de`,
`aigner-immobilien.de`, `locate-immobilien.com`, `kpcimmobilien.de`,
`see-residenz.de`, `torres-immobilien.de`). Websuche **ist** der Domain-Resolver —
Phase 3 automatisiert nur, was hier von Hand geschieht.

Stichprobe von 25-30 echten Makler-Sites der Region. Gemessen wird pro Site:
Vendor-Fingerprint, JSON-LD/Microdata vorhanden, OpenImmo-/RSS-Feed erreichbar,
Sitemap vorhanden, JS-Abhängigkeit, `robots.txt`-Status.

**Ergebnis entscheidet, welche Kaskadenstufen überhaupt gebaut werden.** Zünden
Stufen 1-3 bei kaum einer Site, sparen wir uns ihren Bau; decken sie die Mehrheit
ab, wird Stufe 5 zur Randerscheinung. Der Prober ist kein Wegwerf-Code — er wird
zum `site_probe`-Modul, das später bei jedem Makler-Onboarding läuft.

</details>

### Phase 1 — Fundament
`agents`-Tabelle, generischer DB-getriebener Adapter, Geocoding beim Ingest,
höflicher User-Agent + `robots.txt`.

### Phase 2 — Kaskade
Reihenfolge nach gemessenem Ertrag: **zuerst die fünf Vendor-Adapter**
(immonex, onOffice, OpenImmo2WP, Propstack, WP-ImmoMakler — zusammen 50 %),
dann JSON-LD und Feed als billige Zusatzstufen, dann Sitemap/Detail-Links,
zuletzt das LLM-Rezept für den verbleibenden Rest. Dazu Selbsttest und
Change-Gate über den kanonischen Objekt-Fingerprint sowie die
Playwright-Querschnittsfunktion für JS-Sites und die drei 403-Fälle.

### Phase 3 — Discovery
Seed-Sammlung aus mehreren Kanälen, Domain-Auflösung, Impressum-Verifikation.

### Phase 4 — Transparenz
Coverage-Tab im Dashboard: Abdeckungsquote, manuelle Watchlist mit Grund und
Link, Review-Queue für Zweifelsfälle.

### Phase 5 — Altlasten
Bestehende kaputte Quellen in das neue System überführen: `starnberg_bader`
(Domainwechsel), `tutzing24` (tote Selektoren), `riedel` (ungefilterter
München-Index). `kleinanzeigen` bleibt Sonderfall mit eigener URL-Logik — die
korrekte URL-Form mit Orts-ID und Radius muss neu ermittelt werden.

---

## 11. Testing

- **Kaskadenstufen:** je Stufe Unit-Tests gegen eingefrorene HTML-Fixtures
  (in `.claudeignore` aufnehmen — fremdes HTML kann Prompt-Injection tragen).
- **Selbsttest-Logik:** Grenzfälle — 0 Objekte, Objekte ohne Preis, Duplikate.
- **Change-Gate:** identisches Objekt-Set bei verändertem Roh-HTML muss stumm
  bleiben; geändertes Objekt-Set muss auslösen.
- **Geocoding:** Cache-Treffer, Fehlschlag-Fallback, Radius-Grenzfälle.
- **Coverage-Berechnung:** `unknown` darf nie als abgedeckt zählen; veraltete
  Belege müssen zurück auf `unknown` fallen.
- **Regression:** Die bestehenden 55 Tests müssen grün bleiben.

---

## 12. Offene Punkte

- ~~Die tatsächliche Verbreitung von Vendor-Systemen, JSON-LD und Feeds ist
  unbekannt~~ → **durch Phase 0 geklärt**, siehe Abschnitt 4.1 und den
  Messbericht. Offen bleibt die Verbreitung im *Long Tail* kleiner Makler: die
  Stichprobe kam per Websuche zustande und überrepräsentiert SEO-aktive Anbieter.
- Die Kostenschätzung in Abschnitt 9 ist nach Phase 0 **zu hoch angesetzt**: Wenn
  nur rund ein Viertel der Sites ein LLM-Rezept braucht statt aller, sinken die
  einmaligen Lernkosten von ~9 $ auf ~2-3 $.
- Der Betrieb setzt eine wieder aktive Deployment-Umgebung voraus (VPS wurde am
  2026-06-29 abgeräumt); ein täglicher Lauf braucht eine durchlaufende Maschine.
- Die korrekte Kleinanzeigen-URL-Grammatik mit Orts-ID und Radius muss empirisch
  ermittelt werden (Phase 5).
