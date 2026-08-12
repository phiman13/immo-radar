# Makler-Vollabdeckung Phase 2b: Feld-Extraktor + Cascade-Handler — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `EXTRACTION_METHODS` (bisher leer, siehe `app/sources/agents_adapter.py`) mit echten Handlern für alle fünf auto-harvestbaren Kaskadenstufen aus Phase 2a (`vendor:<x>`, `detail_links`, `sitemap_objekte`, `structured_data`, `feed_adapter`) befüllen, sodass `AgentSiteSource.fetch()` zum ersten Mal echte `RawListing`-Objekte von Makler-Sites liefert — inklusive Feld-Extraktion (Titel/Preis/Fläche/Zimmer/PLZ+Ort/Objekttyp) und Selbsttest vor Weitergabe (Spec §7).

**Architecture:** Drei neue/geänderte Module, sauber nach reine-Funktion/I/O-Orchestrierung getrennt (gleiches Muster wie Phase 2a: `agent_cascade_detect.py` = rein, `agent_probe.py` = I/O). `app/agent_field_extract.py` (neu) enthält reine, I/O-freie Feldextraktion — Regex-basiert (Vorbild: die vier bestehenden Portal-Adapter) plus ein JSON-LD-Feld-Mapper und ein Feed-Item-Parser. `app/agent_cascade_detect.py` (geändert) bekommt zwei Ergänzungen: `find_detail_links()` kann jetzt optional die volle URL-Liste statt nur eine 3er-Stichprobe liefern, und eine neue `extract_jsonld_nodes()`-Funktion liefert rohe schema.org-Knoten statt nur Typen. `app/sources/agent_handlers.py` (neu) orchestriert Netzwerk + Feldextraktion zu vier Handler-Funktionen, die die `ExtractionMethod`-Signatur erfüllen. `app/sources/agents_adapter.py` (geändert) registriert diese Handler in `EXTRACTION_METHODS` (ein geteilter Handler für alle `vendor:<x>`-Keys UND `detail_links` — Phase 0 lieferte nur Fingerprints, keine Vendor-Selektoren), fixt HER-726 (das `listing_url`-Gate blockiert bislang `feed_adapter`-Agents fälschlich) und baut den zweistufigen Selbsttest aus Spec §7 ein (Handler-Ergebnis wird pro Agent gepuffert und geprüft, bevor es weitergereicht wird — ein Makler, der noch NIE etwas geliefert hat, wird bei 0 verwertbaren Objekten sofort zurückgestuft; ein zuvor erfolgreicher Makler wird bei einem einzelnen leeren Lauf nur mit aktualisiertem `last_checked` toleriert, nicht zurückgestuft — echte Bruch-Erkennung nach zwei aufeinanderfolgenden leeren Läufen bleibt Phase 2c).

**UX-Entscheidung (nach Nutzer-Rückfrage zur Crawl-Frequenz):** `AgentSiteSource` teilt sich mit den Portal-Adaptern EIN Poll-Intervall (`poll_interval_minutes`, im Dashboard als Presets 6 Std./12 Std./1-3 Tage wählbar) — kein zweites, verwirrendes Intervall-Setting nur für Makler-Sites. Spec §3/§8 verlangen für Makler-Crawls aber max. ~1×/Tag pro Website (Höflichkeit, robots.txt-Geist), was schneller gewählte Poll-Intervalle (z.B. 6 Std.) verletzen würden. Statt einer im UI leicht ignorierbaren Warnung erzwingt `AgentSiteSource.fetch()` das strukturell: ein Agent, dessen `last_checked` jünger als `MIN_RECRAWL_INTERVAL` (20 Std.) ist, wird übersprungen — unabhängig vom gewählten Poll-Intervall. Portal-Quellen folgen weiter exakt dem gewählten Intervall (dort ist häufiges Pollen erwünscht, kein Crawl-Budget-Risiko). Task 8 baut diesen Guard, Task 9 ergänzt eine erklärende Zeile im Dashboard, damit das Verhalten für den Nutzer nachvollziehbar bleibt statt eine stille Diskrepanz zwischen eingestelltem Intervall und tatsächlichem Makler-Crawl-Rhythmus zu sein.

**Wichtige Korrektur gegenüber dem ersten Entwurf (Advisor-Review vor Ausführungsfreigabe):** Feldextraktion liefert `plz`/`city` statt eines kombinierten `address`-Strings. Grund: `RawListing.dedup_hash()` (`app/models.py:57-68`) nutzt `address` als primäres Hash-Feld und fällt nur bei LEERER Adresse auf `source_id` zurück. Ein Regex-Scan über die ganze Detailseite trifft bei fehlendem Preis/Fläche fast immer zuerst die Impressum-/Footer-Adresse — bei mehreren Objekten desselben Maklers ohne Preis/Fläche wäre das für alle dieselbe Adresse, `dedup_hash()` würde sie auf denselben Hash kollabieren und Objekte 2..N verschwänden stillschweigend beim Ingest (genau der „stille Verlust", den Spec §7 verbietet — und den der Selbsttest nicht sieht, weil er vor dem Ingest läuft). `address` bleibt deshalb bei Agent-Listings immer `None`; `plz`/`city` speisen den Pipeline-Regionsfilter (`app/pipeline.py` liest ohnehin `address`, `plz`, `city` gemeinsam) genauso gut, ohne das Dedup-Risiko.

**Tech Stack:** Python 3.12, httpx (async), BeautifulSoup4, SQLAlchemy, pytest-asyncio — alles bereits im Projekt vorhanden, keine neuen Abhängigkeiten.

## Global Constraints

- **DB-Zugriff:** `import app.db as db_module`, `db_module.SessionLocal()` zur Aufrufzeit — nie `from app.db import SessionLocal` auf Modulebene (Tests patchen `db_module.SessionLocal`).
- **User-Agent:** ausschließlich `from app.robots import USER_AGENT` wiederverwenden — kein neuer/zweiter UA-String.
- **Mutable JSON-Defaults:** neue SQLAlchemy-Spalten (falls nötig) mit `default=dict`/`default=list`, nie literale `{}`/`[]`. (Dieser Plan fügt keine neuen Spalten hinzu — `last_checked`/`last_nonempty_at`/`last_listing_count` existieren bereits seit Phase 1, werden hier erstmals beschrieben.)
- **`extraction`-Sparse-Key-Vertrag (Spec §5.1, Phase-2a-Nachtrag):** Konsumenten lesen ausschließlich per `.get()`, nie per Bracket-Zugriff — auch nicht für `method` selbst.
- **`coverage_status` ausschließlich aus `app.db.COVERAGE_STATUSES`** — kein neuer Statuswert. Dieser Plan nutzt nur bereits vorhandene Werte (`auto-harvested`, `needs-manual-watch`, `robots-disallowed`).
- **robots.txt hat Vorrang** (Spec §8). `AgentSiteSource.fetch()` prüft bereits einmal pro Agent vor jedem Handler-Aufruf — die neuen Handler prüfen NICHT pro Detailseite erneut (identische Vereinfachung wie in `app/agent_probe.py`, das ebenfalls nur `robots_allows_root` prüft, nicht jede Detail-URL einzeln).
- **Crawl-Budget (Spec §8):** pro Agent maximal `MAX_DETAIL_PAGES_PER_AGENT = 40` Detailseiten, mit `DETAIL_FETCH_DELAY_SECONDS = 0.5` Pause zwischen Abrufen — beide Konstanten zentral in `app/sources/agent_handlers.py`, von allen Handlern geteilt, nicht pro Handler neu definiert.
- **Adress-Feld-Konvention (Advisor-Fix):** Agent-Listings befüllen `RawListing.plz`/`RawListing.city`, NIEMALS `RawListing.address` — siehe Begründung oben. Gilt für alle vier Handler in `app/sources/agent_handlers.py` ausnahmslos.
- **Selbsttest-Kriterium (Spec §7, wörtlich):** ein Objekt zählt als verwertbar, wenn es Titel UND URL UND (Preis ODER Fläche) trägt. Fehlender Preis allein ist **kein** Fehlschlag. Zimmerzahl zählt NICHT als Sachattribut für dieses Kriterium (Spec nennt explizit nur „Preis oder Fläche").
- **Selbsttest-Eskalation (Advisor-Fix, zweistufig):** Ein Makler ohne jeden bisherigen Erfolg (`last_nonempty_at is None`) wird bei 0 verwertbaren Objekten SOFORT auf `needs-manual-watch` zurückgestuft (Spec §7 „Selbsttest vor Aktivierung"). Ein zuvor erfolgreicher Makler (`last_nonempty_at` gesetzt) wird bei einem einzelnen leeren Lauf NICHT zurückgestuft, nur `last_checked` wird aktualisiert — echte Bruch-Erkennung braucht laut Spec §7 „ZWEI aufeinanderfolgende" leere Läufe; der dafür nötige Lauf-Zähler ist Change-Gate-Arbeit (Phase 2c). Ohne diese Unterscheidung würde ein einzelnes transientes 5xx einen funktionierenden Makler dauerhaft aus dem Crawl werfen, da `fetch()` nur `coverage_status == "auto-harvested"` selektiert.
- **Crawl-Frequenz-Guard (UX-Entscheidung nach Nutzer-Rückfrage):** `AgentSiteSource` nutzt bewusst KEIN eigenes Poll-Intervall-Setting — das würde ein zweites, für den Nutzer schwer einzuordnendes Dashboard-Feld bedeuten. Stattdessen erzwingt `AgentSiteSource.fetch()` strukturell (nicht nur per UI-Warnung), dass ein einzelner Makler höchstens alle `MIN_RECRAWL_INTERVAL = timedelta(hours=20)` neu gecrawlt wird, unabhängig vom gewählten `poll_interval_minutes` (Dashboard-Presets: 6 Std./12 Std./1-3 Tage — die schnellste UI-Option von 6 Std. würde ohne diesen Guard Makler-Sites 4× häufiger crawlen als Spec §3 „Täglich" vorsieht). Portal-Quellen sind von diesem Guard nicht betroffen und folgen weiterhin exakt dem gewählten Intervall.
- **Vendor-Handler-Strategie (Scope-Entscheidung dieses Plans):** `vendor:<x>` und `detail_links` teilen sich EINEN Handler (`agent_handlers.crawl_and_extract`). Phase 0 hat nur Fingerprints geliefert, keine Vendor-spezifischen Selektoren — `vendor:<x>` bleibt reines Herkunfts-Tag im `extraction`-Dict.
- **Extraktor-Reichweite (Scope-Entscheidung dieses Plans):** `app/agent_field_extract.py` wird ausschließlich von den neuen Agent-Cascade-Handlern genutzt. Die vier bestehenden Portal-Adapter (`makler_bsimmo.py`, `makler_riedel.py`, `makler_starnberg_immo.py`, `tutzing24.py`) werden in diesem Plan NICHT angefasst — kein Regressionsrisiko für aktiv laufende Quellen. Sie dienten nur als Vorbild für die Regex-Muster.
- **Ruff-Baseline:** `ruff check .` muss auf allen neuen/geänderten Dateien sauber durchlaufen (line-length 110, Regeln E/F/I/B/UP). Blockt der Pre-Commit-Hook auf vorbestehenden Fehlern einer *angefassten* Datei: mechanisch fixen + im Commit/Report offenlegen — nie `--no-verify`.
- **Lokale Env:** `DB_PATH=./data/immo.db pytest` / `DB_PATH=./data/immo.db ruff check .`.
- **Test-Isolation:** SQLite-Test-DB über `create_engine(f"sqlite:///{tmp_path}/test.db")` + `monkeypatch.setattr(db_module, "engine"/"SessionLocal", ...)`, `httpx`-Aufrufe über `unittest.mock.AsyncMock`/`MagicMock` mit URL-Routing (Muster: `tests/test_agent_probe.py`) — kein `respx`.
- **Explizit außerhalb dieses Plans (siehe Self-Review-Notizen am Ende):** Change-Gate-Fingerprint + „nur neue Objekte" + Zwei-Läufe-Zähler für Bruch-Erkennung (Phase 2c), Playwright-Rendering für JS-Shells/403-Sites (Phase 2c), LLM-Rezept für Stufe `learned_recipe` (Phase 2d), SSRF-Guard auf `verified_domain` (HER-725, vor Phase 3), Refactor der vier bestehenden Portal-Adapter auf den neuen Extraktor.

---

### Task 1: `agent_cascade_detect.py` erweitern — volle Detail-Link-Liste + rohe JSON-LD-Knoten

**Files:**
- Modify: `app/agent_cascade_detect.py`
- Test: `tests/test_agent_cascade_detect.py` (bestehende Datei, 13 Tests aus Phase 2a — wird um 6 Tests ergänzt)

**Interfaces:**
- Consumes: nichts Neues (nutzt bereits vorhandene Imports `json`, `re`, `BeautifulSoup`, `IMMO_LD_TYPES`).
- Produces: `find_detail_links(html: str, base: str, limit: int | None = 3) -> tuple[int, list[str]]` (geänderte Signatur, Default-Verhalten identisch zu vorher), `extract_jsonld_nodes(html: str) -> list[dict]` (neu). Beide werden von Task 4/6 (`app/sources/agent_handlers.py`) importiert.

- [ ] **Step 1: `find_detail_links()` um optionalen `limit`-Parameter erweitern**

`app/agent_cascade_detect.py` — die Funktion endet aktuell (Zeile ~198-210) mit:

```python
    # (2) Flache Root-Slugs, wenn (1) nichts Überzeugendes gefunden hat
    flat = sorted(
        u
        for u in candidates
        if (segs := [s for s in urlparse(u).path.split("/") if s])
        and len(segs) == 1
        and len(segs[0]) >= SLUG_MIN_LEN
        and segs[0].count("-") >= SLUG_MIN_PARTS
    )
    if len(flat) > len(best[1]):
        best = (len(flat), flat)

    return len(best[1]), best[1][:3]
```

Signatur und letzte Zeile ändern:

```python
def find_detail_links(html: str, base: str, limit: int | None = 3) -> tuple[int, list[str]]:
```

```python
    if len(flat) > len(best[1]):
        best = (len(flat), flat)

    sample = best[1][:limit] if limit is not None else best[1]
    return len(best[1]), sample
```

Der Docstring-Absatz der Funktion bekommt einen neuen letzten Satz:

```python
    `limit` begrenzt die zurückgegebene URL-Liste (Default 3, wie bisher —
    für Probing/Logging reicht eine Stichprobe). `limit=None` liefert die
    volle Liste — für den tatsächlichen Harvest in Phase 2b
    (app.sources.agent_handlers), wo jede gefundene Objekt-URL abgerufen
    werden muss, nicht nur eine Stichprobe.
    """
```

- [ ] **Step 2: `extract_jsonld_nodes()` ergänzen**

Direkt unter `detect_structured()` in `app/agent_cascade_detect.py` einfügen:

```python
def extract_jsonld_nodes(html: str) -> list[dict]:
    """Rohe schema.org-Knoten mit immobilienspezifischem @type — Gegenstück zu
    detect_structured(), das nur die Typen zählt. Für die structured_data-
    Kaskadenstufe (Phase 2b), die tatsächliche Feldwerte (Preis, Fläche, Name)
    aus dem Knoten lesen muss, nicht nur wissen, DASS JSON-LD vorhanden ist.
    Kaputtes JSON wird übersprungen statt (wie detect_structured()) per Regex
    nach Typnamen zu durchsuchen — für Feldwerte gibt es dort ohnehin nichts
    Verwertbares zu retten."""
    soup = BeautifulSoup(html, "html.parser")
    nodes: list[dict] = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.get_text() or ""
        try:
            data = json.loads(raw)
        except Exception:
            continue
        for node in data if isinstance(data, list) else [data]:
            if not isinstance(node, dict):
                continue
            t = node.get("@type")
            types = t if isinstance(t, list) else [t] if t else []
            if IMMO_LD_TYPES.intersection(types):
                nodes.append(node)
            for sub in node.get("@graph", []) or []:
                if not isinstance(sub, dict):
                    continue
                st = sub.get("@type")
                stypes = st if isinstance(st, list) else [st] if st else []
                if IMMO_LD_TYPES.intersection(stypes):
                    nodes.append(sub)
    return nodes
```

- [ ] **Step 3: Failing Tests schreiben**

An `tests/test_agent_cascade_detect.py` anhängen:

```python
from app.agent_cascade_detect import extract_jsonld_nodes  # zur bestehenden Import-Zeile hinzufügen


def test_find_detail_links_limit_none_returns_full_set():
    html = """
    <html><body>
      <a href="/immobilien/villa-am-see-tutzing">A</a>
      <a href="/immobilien/wohnung-starnberg-zentral">B</a>
      <a href="/immobilien/haus-poecking-mit-garten">C</a>
      <a href="/immobilien/doppelhaushaelfte-feldafing-ruhig">D</a>
      <a href="/immobilien/grundstueck-bernried-seenah">E</a>
    </body></html>
    """
    n, urls = find_detail_links(html, "https://x.de/immobilien/", limit=None)
    assert n == 5
    assert len(urls) == 5


def test_find_detail_links_default_limit_still_three():
    html = """
    <html><body>
      <a href="/immobilien/villa-am-see-tutzing">A</a>
      <a href="/immobilien/wohnung-starnberg-zentral">B</a>
      <a href="/immobilien/haus-poecking-mit-garten">C</a>
      <a href="/immobilien/doppelhaushaelfte-feldafing-ruhig">D</a>
      <a href="/immobilien/grundstueck-bernried-seenah">E</a>
    </body></html>
    """
    n, urls = find_detail_links(html, "https://x.de/immobilien/")
    assert n == 5
    assert len(urls) == 3


def test_extract_jsonld_nodes_returns_full_node_for_immo_type():
    html = """
    <script type="application/ld+json">
    {"@type": "RealEstateListing", "name": "Villa am See", "offers": {"price": 1200000}}
    </script>
    """
    nodes = extract_jsonld_nodes(html)
    assert len(nodes) == 1
    assert nodes[0]["name"] == "Villa am See"
    assert nodes[0]["offers"]["price"] == 1200000


def test_extract_jsonld_nodes_ignores_generic_webpage_type():
    html = '<script type="application/ld+json">{"@type": "WebPage", "name": "Startseite"}</script>'
    assert extract_jsonld_nodes(html) == []


def test_extract_jsonld_nodes_reads_graph_wrapped_nodes():
    html = """
    <script type="application/ld+json">
    {"@graph": [{"@type": "WebPage"}, {"@type": "Apartment", "name": "ETW Tutzing"}]}
    </script>
    """
    nodes = extract_jsonld_nodes(html)
    assert len(nodes) == 1
    assert nodes[0]["name"] == "ETW Tutzing"


def test_extract_jsonld_nodes_skips_broken_json():
    html = '<script type="application/ld+json">{not valid json</script>'
    assert extract_jsonld_nodes(html) == []
```

- [ ] **Step 4: Tests laufen lassen, sicherstellen dass die neuen fehlschlagen**

Run: `DB_PATH=./data/immo.db pytest tests/test_agent_cascade_detect.py -v`
Expected: die 6 neuen Tests FAIL (`extract_jsonld_nodes` nicht importierbar / `find_detail_links()` kennt `limit` nicht), die 13 bestehenden PASS.

- [ ] **Step 5: Implementierung eintragen, Tests grün bekommen**

Änderungen aus Step 1 und 2 in `app/agent_cascade_detect.py` eintragen.

Run: `DB_PATH=./data/immo.db pytest tests/test_agent_cascade_detect.py -v`
Expected: PASS (19 Tests)

- [ ] **Step 6: Lint + Commit**

```bash
DB_PATH=./data/immo.db ruff check app/agent_cascade_detect.py tests/test_agent_cascade_detect.py
git add app/agent_cascade_detect.py tests/test_agent_cascade_detect.py
git commit -m "feat(agents): find_detail_links() volle Liste + extract_jsonld_nodes() für Phase 2b"
```

---

### Task 2: `app/agent_field_extract.py` — generischer Regex-Feld-Extraktor

**Files:**
- Create: `app/agent_field_extract.py`
- Test: `tests/test_agent_field_extract.py`

**Interfaces:**
- Consumes: `app.models.PropertyType`.
- Produces: `extract_price(text: str) -> int | None`, `extract_qm(text: str) -> float | None`, `extract_rooms(text: str) -> float | None`, `extract_plz_city(text: str) -> tuple[str | None, str | None]`, `extract_property_type(text: str) -> PropertyType`, `extract_title(html: str, fallback_text: str = "") -> str`, `extract_fields(html: str, text: str) -> dict` (Keys: `title`, `price_eur`, `qm`, `rooms`, `plz`, `city`, `property_type` — bewusst KEIN `address`-Key, siehe Modul-Docstring/Global Constraints „Adress-Feld-Konvention"). Werden von Task 4-7 (`app/sources/agent_handlers.py`) importiert.

- [ ] **Step 1: Datei mit Regex-Extraktoren anlegen**

```python
"""Genereischer, I/O-freier Feld-Extraktor für Makler-Detailseiten
(Vollabdeckung-Spec §4.1, Phase 2b). Nach Vorbild der Regex-Muster in den vier
bestehenden Portal-Adaptern (app/sources/makler_bsimmo.py, makler_riedel.py,
makler_starnberg_immo.py, tutzing24.py) — dort 4x fast identisch dupliziert,
hier als geteilte, direkt testbare Funktionen.

Zwei bewusste Abweichungen von den Portal-Adaptern:

1. Bewusst OHNE deren hartkodierte Tutzing-Ortsnamen-Fallback-Liste: der
   Makler-Kreis ist laut Spec §3 bewusst weit gefasst (auch Münchner Makler
   mit Seeobjekten) — der Regionsfilter läuft bereits auf Pipeline-Ebene
   (app/pipeline.py LOCATION_ALLOWLIST_RE); ein zweiter, engerer Filter hier
   würde Objekte außerhalb der hartkodierten Liste schon vor dem
   Pipeline-Filter unsichtbar machen.
2. Liefert PLZ/Ort GETRENNT (extract_plz_city / die "plz"/"city"-Keys in
   extract_fields), NIE einen kombinierten "address"-String. Grund:
   RawListing.dedup_hash() (app/models.py) nutzt "address" als primäres
   Hash-Feld und fällt nur bei LEERER Adresse auf source_id zurück. Ein
   Regex-Scan über eine ganze Detailseite trifft bei fehlendem Preis/Fläche
   (Spec §7: "Preis auf Anfrage" ist kein Fehlschlag) fast immer zuerst die
   Impressum-/Footer-Adresse — bei mehreren Objekten desselben Maklers ohne
   Preis/Fläche wäre das für alle dieselbe Adresse, dedup_hash() würde sie
   kollabieren. plz/city speisen den Pipeline-Regionsfilter genauso gut, ohne
   dieses Risiko — RawListing.address bleibt für Agent-Listings immer None."""

from __future__ import annotations

import re

from app.models import PropertyType

_LABELED_PRICE_RE = re.compile(r"(?:Kaufpreis|Preis)\b[^0-9€]{0,40}([\d.]{4,})\s*(?:€|EUR)", re.I)
_PRICE_RE = re.compile(r"([\d.]{4,})\s*(?:€|EUR)")
_QM_RE = re.compile(r"([\d.,]+)\s*m²")
_ROOMS_RE = re.compile(r"([\d,]+)\s*Zi(?:mmer)?\b", re.I)
_PLZ_ORT_RE = re.compile(r"\b(\d{5})\s+([A-ZÄÖÜ][a-zäöüß\-]+(?:\s+[A-ZÄÖÜ][a-zäöüß\-]+)?)")

_TITLE_TAG_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")
_OG_TITLE_RE = re.compile(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', re.I)


def extract_price(text: str) -> int | None:
    """Preis-Label ("Kaufpreis"/"Preis") wird zuerst gesucht — auf einer
    ganzen Detailseite (statt der kurzen Kartentext-Snippets der
    Portal-Adapter) steht sonst oft eine Hausgeld-/Nebenkosten-Zahl VOR dem
    eigentlichen Kaufpreis im Text, und first-match-wins würde die falsche
    Zahl greifen — mit Folgeschaden: pipeline._matches_profile filtert den
    Preis gegen die konfigurierte Preisspanne, ein falscher Preis lässt das
    Objekt also im schlimmsten Fall komplett verschwinden."""
    m = _LABELED_PRICE_RE.search(text) or _PRICE_RE.search(text)
    if not m:
        return None
    try:
        return int(m.group(1).replace(".", ""))
    except ValueError:
        return None


def extract_qm(text: str) -> float | None:
    m = _QM_RE.search(text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(".", "").replace(",", "."))
    except ValueError:
        return None


def extract_rooms(text: str) -> float | None:
    m = _ROOMS_RE.search(text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return None


def extract_plz_city(text: str) -> tuple[str | None, str | None]:
    m = _PLZ_ORT_RE.search(text)
    if not m:
        return None, None
    return m.group(1), m.group(2)


def extract_property_type(text: str) -> PropertyType:
    s = text.lower()
    if "doppelhaush" in s:
        return PropertyType.DOPPELHAUSHAELFTE
    if "reihenhaus" in s:
        return PropertyType.REIHENHAUS
    if "haus" in s or "villa" in s:
        return PropertyType.HAUS
    if "wohnung" in s or "etw" in s:
        return PropertyType.WOHNUNG
    if "grundst" in s:
        return PropertyType.GRUNDSTUECK
    return PropertyType.UNKNOWN


def extract_title(html: str, fallback_text: str = "") -> str:
    m = _TITLE_TAG_RE.search(html)
    if m:
        candidate = _TAG_STRIP_RE.sub("", m.group(1)).strip()
        if len(candidate) > 4:
            return candidate[:200]
    m = _OG_TITLE_RE.search(html)
    if m and len(m.group(1).strip()) > 4:
        return m.group(1).strip()[:200]
    snippets = [s.strip() for s in re.split(r"[\n.|]", fallback_text) if 15 < len(s.strip()) < 120]
    return (snippets[0] if snippets else "Makler-Objekt")[:200]


def extract_fields(html: str, text: str) -> dict:
    """Bündelt alle generischen Extraktionen für eine Detailseite.

    `text` ist bereits von HTML befreiter Fließtext (z.B. via
    BeautifulSoup(html).get_text(" ", strip=True)) — der Aufrufer liefert ihn,
    damit dieses Modul kein bs4 importieren muss und rein auf Strings testbar
    bleibt. Liefert "plz"/"city", bewusst kein "address" — siehe
    Modul-Docstring."""
    plz, city = extract_plz_city(text)
    return {
        "title": extract_title(html, text),
        "price_eur": extract_price(text),
        "qm": extract_qm(text),
        "rooms": extract_rooms(text),
        "plz": plz,
        "city": city,
        "property_type": extract_property_type(text),
    }
```

- [ ] **Step 2: Failing Tests schreiben**

```python
"""Tests für app.agent_field_extract — genereischer, I/O-freier
Feld-Extraktor für Makler-Detailseiten (Phase 2b)."""

from __future__ import annotations

from app.agent_field_extract import (
    extract_fields,
    extract_plz_city,
    extract_price,
    extract_property_type,
    extract_qm,
    extract_rooms,
    extract_title,
)
from app.models import PropertyType


def test_extract_price_parses_thousands_separator():
    assert extract_price("Kaufpreis: 450.000 €") == 450000


def test_extract_price_returns_none_without_match():
    assert extract_price("Preis auf Anfrage") is None


def test_extract_price_prefers_labeled_kaufpreis_over_earlier_hausgeld():
    text = "Hausgeld: 3.500 € Kaufpreis: 650.000 €"
    assert extract_price(text) == 650000


def test_extract_price_falls_back_to_unlabeled_price_when_no_label_present():
    assert extract_price("Objektbeschreibung: sonnige Wohnung, VB 380.000 €") == 380000


def test_extract_qm_parses_comma_decimal():
    assert extract_qm("Wohnfläche 120,5 m²") == 120.5


def test_extract_rooms_parses_zi_abbreviation():
    assert extract_rooms("3,5 Zi. Wohnung") == 3.5


def test_extract_rooms_parses_zimmer_word():
    assert extract_rooms("4 Zimmer Haus") == 4.0


def test_extract_plz_city_finds_plz_and_ort():
    assert extract_plz_city("Objekt in 82327 Tutzing am See") == ("82327", "Tutzing")


def test_extract_plz_city_returns_none_none_without_plz():
    assert extract_plz_city("Schönes Haus mit Garten") == (None, None)


def test_extract_property_type_detects_doppelhaushaelfte_before_haus():
    assert extract_property_type("Gepflegte Doppelhaushälfte") == PropertyType.DOPPELHAUSHAELFTE


def test_extract_property_type_falls_back_to_unknown():
    assert extract_property_type("Gewerbeobjekt") == PropertyType.UNKNOWN


def test_extract_title_prefers_h1():
    html = "<html><body><h1>Villa am Starnberger See</h1></body></html>"
    assert extract_title(html) == "Villa am Starnberger See"


def test_extract_title_falls_back_to_og_title_without_h1():
    html = '<html><head><meta property="og:title" content="Traumhaus Tutzing"></head></html>'
    assert extract_title(html) == "Traumhaus Tutzing"


def test_extract_title_falls_back_to_text_snippet():
    html = "<html><body><p>Kein Heading hier</p></body></html>"
    text = "Moderne Villa mit Seeblick und grossem Garten in Tutzing direkt am See"
    title = extract_title(html, text)
    assert "Villa" in title


def test_extract_title_returns_placeholder_when_nothing_found():
    assert extract_title("<html><body></body></html>", "") == "Makler-Objekt"


def test_extract_fields_bundles_all_extractions():
    html = "<html><body><h1>Haus in Tutzing</h1></body></html>"
    text = "Haus in Tutzing 82327 Tutzing, Kaufpreis: 450.000 €, 140 m², 5 Zimmer"
    fields = extract_fields(html, text)
    assert fields["title"] == "Haus in Tutzing"
    assert fields["price_eur"] == 450000
    assert fields["qm"] == 140.0
    assert fields["rooms"] == 5.0
    assert fields["plz"] == "82327"
    assert fields["city"] == "Tutzing"
    assert fields["property_type"] == PropertyType.HAUS
    assert "address" not in fields
```

- [ ] **Step 3: Tests laufen lassen, sicherstellen dass sie fehlschlagen**

Run: `DB_PATH=./data/immo.db pytest tests/test_agent_field_extract.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'app.agent_field_extract'`

- [ ] **Step 4: Tests grün bekommen**

Datei aus Step 1 anlegen.

Run: `DB_PATH=./data/immo.db pytest tests/test_agent_field_extract.py -v`
Expected: PASS (16 Tests)

- [ ] **Step 5: Lint + Commit**

```bash
DB_PATH=./data/immo.db ruff check app/agent_field_extract.py tests/test_agent_field_extract.py
git add app/agent_field_extract.py tests/test_agent_field_extract.py
git commit -m "feat(agents): genereischer Regex-Feld-Extraktor für Makler-Detailseiten (plz/city statt address)"
```

---

### Task 3: `app/agent_field_extract.py` erweitern — JSON-LD-Mapper + Feed-Item-Parser

**Files:**
- Modify: `app/agent_field_extract.py`
- Test: `tests/test_agent_field_extract.py` (aus Task 2, wird ergänzt)

**Interfaces:**
- Consumes: `extract_plz_city` (Task 2, dieselbe Datei).
- Produces: `fields_from_jsonld(node: dict) -> dict` (Keys: `title`, `url`, `price_eur`, `qm`, `rooms`, `plz`, `city` — auch hier kein `address`-Key, aus demselben Grund wie `extract_fields`), `merge_fields(primary: dict, fallback: dict) -> dict`, `parse_feed_items(feed_xml: str) -> list[dict]` (Keys je Item: `link`, `title`, `description`). Werden von Task 6/7 (`app/sources/agent_handlers.py`) importiert.

- [ ] **Step 1: JSON-LD-Mapper, Merge-Helfer und Feed-Parser anhängen**

An `app/agent_field_extract.py` anhängen:

```python
_CDATA_RE = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.S)


def _clean_feed_text(raw: str) -> str:
    m = _CDATA_RE.search(raw)
    if m:
        return m.group(1).strip()
    return _TAG_STRIP_RE.sub("", raw).strip()


def fields_from_jsonld(node: dict) -> dict:
    """Liest Preis/Fläche/Zimmer/Titel/URL/PLZ/Ort direkt aus einem
    schema.org-Knoten (app.agent_cascade_detect.extract_jsonld_nodes) —
    reicher als der Text-Regex-Weg, wo die Site das tatsächlich befüllt.
    Fehlende Felder bleiben None; der Aufrufer kombiniert mit dem
    Regex-Extraktor als Fallback (merge_fields). Liefert "plz"/"city" statt
    eines kombinierten "address"-Strings — dieselbe Dedup-Sicherheitsregel
    wie extract_fields (siehe Modul-Docstring), auch wenn das JSON-LD-Adressfeld
    strukturierter ist: ein Freitext-Adressfeld ohne postalCode/
    addressLocality-Trennung wird über extract_plz_city nachgeparst statt
    ungeprüft übernommen zu werden."""
    offers = node.get("offers")
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if not isinstance(offers, dict):
        offers = {}
    price = offers.get("price")
    try:
        price_eur = int(float(price)) if price is not None else None
    except (TypeError, ValueError):
        price_eur = None

    floor_size = node.get("floorSize")
    qm = None
    if isinstance(floor_size, dict):
        val = floor_size.get("value")
        try:
            qm = float(val) if val is not None else None
        except (TypeError, ValueError):
            qm = None
    elif floor_size is not None:
        try:
            qm = float(floor_size)
        except (TypeError, ValueError):
            qm = None

    rooms = node.get("numberOfRooms")
    try:
        rooms = float(rooms) if rooms is not None else None
    except (TypeError, ValueError):
        rooms = None

    address = node.get("address")
    plz = None
    city = None
    if isinstance(address, dict):
        plz = address.get("postalCode") or None
        city = address.get("addressLocality") or None
    elif isinstance(address, str):
        plz, city = extract_plz_city(address)

    return {
        "title": node.get("name"),
        "url": node.get("url"),
        "price_eur": price_eur,
        "qm": qm,
        "rooms": rooms,
        "plz": plz,
        "city": city,
    }


def merge_fields(primary: dict, fallback: dict) -> dict:
    """Kombiniert zwei Feld-Dicts — primary gewinnt, fallback füllt nur
    fehlende (None/leere) Werte. Für die structured_data-Stufe: JSON-LD
    zuerst, Regex-Extraktion aus dem Fließtext nur für Lücken."""
    merged = dict(primary)
    for key, value in fallback.items():
        if merged.get(key) in (None, ""):
            merged[key] = value
    return merged


def parse_feed_items(feed_xml: str) -> list[dict]:
    """Extrahiert Link/Titel/Text je <item>/<entry> aus einem RSS-/Atom-Feed —
    dieselbe Item-Regex wie app.agent_probe.validate_feed(), hier aber für den
    tatsächlichen Objekt-Ertrag statt nur für die Ja/Nein-Prüfung, ob der Feed
    Immobilien enthält."""
    items = re.findall(r"<(?:item|entry)\b.*?</(?:item|entry)>", feed_xml, re.S | re.I)
    result = []
    for it in items:
        link_m = re.search(r"<link[^>]*>([^<]+)</link>|<link[^>]*href=[\"']([^\"']+)[\"']", it, re.I)
        link = (link_m.group(1) or link_m.group(2) or "").strip() if link_m else ""
        title_m = re.search(r"<title[^>]*>(.*?)</title>", it, re.S | re.I)
        title = _clean_feed_text(title_m.group(1)) if title_m else ""
        desc_m = re.search(
            r"<(?:description|content|summary)[^>]*>(.*?)</(?:description|content|summary)>", it, re.S | re.I
        )
        description = _clean_feed_text(desc_m.group(1)) if desc_m else ""
        if link:
            result.append({"link": link, "title": title, "description": description})
    return result
```

- [ ] **Step 2: Failing Tests schreiben**

An `tests/test_agent_field_extract.py` anhängen (Import-Zeile um `fields_from_jsonld`, `merge_fields`, `parse_feed_items` ergänzen):

```python
def test_fields_from_jsonld_reads_offers_price_and_floor_size():
    node = {
        "@type": "RealEstateListing",
        "name": "Villa am See",
        "url": "https://x.de/objekte/villa-am-see",
        "offers": {"price": 1200000},
        "floorSize": {"value": 180},
        "numberOfRooms": 6,
        "address": {"postalCode": "82327", "addressLocality": "Tutzing"},
    }
    fields = fields_from_jsonld(node)
    assert fields["title"] == "Villa am See"
    assert fields["url"] == "https://x.de/objekte/villa-am-see"
    assert fields["price_eur"] == 1200000
    assert fields["qm"] == 180.0
    assert fields["rooms"] == 6.0
    assert fields["plz"] == "82327"
    assert fields["city"] == "Tutzing"


def test_fields_from_jsonld_handles_missing_offers_gracefully():
    node = {"@type": "Apartment", "name": "ETW"}
    fields = fields_from_jsonld(node)
    assert fields["price_eur"] is None
    assert fields["qm"] is None
    assert fields["rooms"] is None
    assert fields["plz"] is None
    assert fields["city"] is None


def test_fields_from_jsonld_parses_freetext_address_string():
    node = {"@type": "House", "name": "Haus", "address": "82327 Tutzing"}
    fields = fields_from_jsonld(node)
    assert fields["plz"] == "82327"
    assert fields["city"] == "Tutzing"


def test_merge_fields_prefers_primary_and_fills_gaps():
    primary = {"title": "Villa am See", "price_eur": None, "qm": 180.0}
    fallback = {"title": "Fallback-Titel", "price_eur": 999000, "qm": 200.0}
    merged = merge_fields(primary, fallback)
    assert merged["title"] == "Villa am See"
    assert merged["price_eur"] == 999000
    assert merged["qm"] == 180.0


def test_parse_feed_items_extracts_link_title_description():
    feed = """
    <rss><channel>
      <item>
        <title>Haus in Tutzing, 450.000 €</title>
        <link>https://x.de/objekte/haus-tutzing</link>
        <description>140 m², 5 Zimmer</description>
      </item>
    </channel></rss>
    """
    items = parse_feed_items(feed)
    assert len(items) == 1
    assert items[0]["link"] == "https://x.de/objekte/haus-tutzing"
    assert items[0]["title"] == "Haus in Tutzing, 450.000 €"
    assert items[0]["description"] == "140 m², 5 Zimmer"


def test_parse_feed_items_unwraps_cdata_title():
    feed = """
    <feed>
      <entry>
        <title><![CDATA[Villa & Seeblick]]></title>
        <link href="https://x.de/objekte/villa-seeblick"/>
      </entry>
    </feed>
    """
    items = parse_feed_items(feed)
    assert items[0]["title"] == "Villa & Seeblick"
    assert items[0]["link"] == "https://x.de/objekte/villa-seeblick"


def test_parse_feed_items_skips_entries_without_link():
    feed = "<rss><channel><item><title>Kein Link</title></item></channel></rss>"
    assert parse_feed_items(feed) == []
```

- [ ] **Step 3: Tests laufen lassen, sicherstellen dass die neuen fehlschlagen**

Run: `DB_PATH=./data/immo.db pytest tests/test_agent_field_extract.py -v`
Expected: die 7 neuen Tests FAIL (`ImportError`), die 16 bestehenden PASS.

- [ ] **Step 4: Tests grün bekommen**

Implementierung aus Step 1 anhängen.

Run: `DB_PATH=./data/immo.db pytest tests/test_agent_field_extract.py -v`
Expected: PASS (23 Tests)

- [ ] **Step 5: Lint + Commit**

```bash
DB_PATH=./data/immo.db ruff check app/agent_field_extract.py tests/test_agent_field_extract.py
git add app/agent_field_extract.py tests/test_agent_field_extract.py
git commit -m "feat(agents): JSON-LD-Feld-Mapper + Feed-Item-Parser (plz/city statt address)"
```

---

### Task 4: `app/sources/agent_handlers.py` — Crawl-Handler (vendor:* + detail_links)

**Files:**
- Create: `app/sources/agent_handlers.py`
- Test: `tests/test_agent_handlers.py`

**Interfaces:**
- Consumes: `app.agent_cascade_detect.find_detail_links` (Task 1), `app.agent_field_extract.extract_fields` (Task 2), `app.db.Agent`, `app.models.RawListing`, `app.logging_setup.log`.
- Produces: `MAX_DETAIL_PAGES_PER_AGENT: int`, `DETAIL_FETCH_DELAY_SECONDS: float`, `_source_id(agent_id: int, url: str) -> str`, `_fetch_detail_listing(agent: Agent, client: httpx.AsyncClient, url: str) -> RawListing | None`, `async def crawl_and_extract(agent: Agent, client: httpx.AsyncClient) -> AsyncIterator[RawListing]`. `crawl_and_extract` erfüllt die `ExtractionMethod`-Signatur aus `app.sources.agents_adapter` und wird dort (Task 8) für `detail_links` und alle `vendor:<x>`-Keys registriert. `_source_id`/`_fetch_detail_listing` werden von Task 5/6 (weitere Handler in derselben Datei) wiederverwendet. `_fetch_detail_listing` befüllt `RawListing.plz`/`.city` aus `extract_fields()`, NIE `.address` (siehe Global Constraints „Adress-Feld-Konvention").

- [ ] **Step 1: Datei mit gemeinsamen Helfern und dem Crawl-Handler anlegen**

```python
"""I/O-Handler der Extraktions-Kaskade (Vollabdeckung-Spec §4.1, Phase 2b) —
Gegenstück zu app.agent_cascade_detect (reine Erkennung) und
app.agent_field_extract (reine Feldextraktion): hier laufen beide zusammen,
gegen echtes Netzwerk. Jeder Handler erfüllt die ExtractionMethod-Signatur aus
app.sources.agents_adapter (Callable[[Agent, httpx.AsyncClient],
AsyncIterator[RawListing]]) und wird dort in EXTRACTION_METHODS registriert.

Crawl-Budget (Spec §8): pro Agent maximal MAX_DETAIL_PAGES_PER_AGENT
Detailseiten, mit DETAIL_FETCH_DELAY_SECONDS Pause dazwischen — bewusst
kürzer als die 1s-Probe-Pause aus app.agent_probe (dort ein Abruf pro Host je
Onboarding-Lauf, hier bis zu 40 Abrufe pro Host je Harvest-Lauf). robots.txt
wird hier NICHT pro Detailseite erneut geprüft — app.sources.agents_adapter
prüft bereits einmal pro Agent vor jedem Handler-Aufruf (identische
Vereinfachung wie app.agent_probe, das nur robots_allows_root auf
Root-Ebene prüft).

Alle Handler befüllen RawListing.plz/.city, NIE RawListing.address — siehe
app.agent_field_extract-Modul-Docstring für die Dedup-Begründung."""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator

import httpx
from bs4 import BeautifulSoup

from app.agent_cascade_detect import find_detail_links
from app.agent_field_extract import extract_fields
from app.db import Agent
from app.logging_setup import log
from app.models import RawListing

MAX_DETAIL_PAGES_PER_AGENT = 40
DETAIL_FETCH_DELAY_SECONDS = 0.5


def _source_id(agent_id: int, url: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", url.lower()).strip("-")[-64:]
    return f"agent-{agent_id}-{slug}"


async def _fetch_detail_listing(agent: Agent, client: httpx.AsyncClient, url: str) -> RawListing | None:
    try:
        r = await client.get(url)
        r.raise_for_status()
    except Exception as e:
        log.warning("agent_handlers.detail_fetch_failed", agent_id=agent.id, url=url, error=str(e))
        return None

    text = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)
    fields = extract_fields(r.text, text)
    return RawListing(
        source="agents",
        source_id=_source_id(agent.id, url),
        url=url,
        title=fields["title"],
        description=text[:2000],
        price_eur=fields["price_eur"],
        qm=fields["qm"],
        rooms=fields["rooms"],
        plz=fields["plz"],
        city=fields["city"],
        property_type=fields["property_type"],
    )


async def crawl_and_extract(agent: Agent, client: httpx.AsyncClient) -> AsyncIterator[RawListing]:
    """Handler für alle `vendor:<x>`-Method-Keys UND `detail_links` (Scope-
    Entscheidung Phase 2b): Phase 0 lieferte nur Vendor-Fingerprints, keine
    Vendor-spezifischen Selektoren — `vendor:<x>` bleibt deshalb nur ein
    Herkunfts-Tag im extraction-Dict, kein eigener Code-Pfad. Findet
    Objekt-URLs strukturell (find_detail_links) auf agent.listing_url, holt
    jede Detailseite, extrahiert Felder generisch."""
    if not agent.listing_url:
        log.warning("agent_handlers.crawl_no_listing_url", agent_id=agent.id)
        return

    try:
        r = await client.get(agent.listing_url)
        r.raise_for_status()
    except Exception as e:
        log.warning("agent_handlers.listing_fetch_failed", agent_id=agent.id, error=str(e))
        return

    _, urls = find_detail_links(r.text, agent.listing_url, limit=None)
    urls = urls[:MAX_DETAIL_PAGES_PER_AGENT]

    for url in urls:
        listing = await _fetch_detail_listing(agent, client, url)
        if listing is not None:
            yield listing
        await asyncio.sleep(DETAIL_FETCH_DELAY_SECONDS)
```

- [ ] **Step 2: Failing Tests schreiben**

```python
"""Tests für app.sources.agent_handlers — I/O-Handler der Extraktions-Kaskade
(Phase 2b). httpx wird über AsyncMock mit URL-Routing gemockt (Projekt-
Konvention, siehe tests/test_agent_probe.py) — kein respx."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db import Agent
from app.sources.agent_handlers import crawl_and_extract


def _resp(status_code=200, text=""):
    r = MagicMock()
    r.status_code = status_code
    r.text = text
    r.raise_for_status = MagicMock()
    if status_code >= 400:
        r.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return r


def _routed_client(routes: dict[str, MagicMock], default=None):
    client = AsyncMock()

    async def _get(url, *a, **kw):
        if url in routes:
            return routes[url]
        return default or _resp(status_code=404)

    client.get = AsyncMock(side_effect=_get)
    return client


def _agent(**overrides) -> Agent:
    defaults = dict(id=1, name="Test Makler", listing_url=None, extraction={})
    defaults.update(overrides)
    return Agent(**defaults)


@pytest.mark.asyncio
async def test_crawl_and_extract_finds_and_extracts_detail_pages():
    listing_html = """
    <html><body>
      <a href="/immobilien/villa-am-see-tutzing">A</a>
      <a href="/immobilien/wohnung-starnberg-zentral">B</a>
      <a href="/immobilien/haus-poecking-mit-garten">C</a>
    </body></html>
    """
    detail_html = (
        "<html><body><h1>Villa am See</h1>"
        "<p>Kaufpreis: 450.000 € 180 m² 6 Zimmer 82327 Tutzing</p></body></html>"
    )
    routes = {
        "https://x.de/immobilien/": _resp(text=listing_html),
        "https://x.de/immobilien/villa-am-see-tutzing": _resp(text=detail_html),
        "https://x.de/immobilien/wohnung-starnberg-zentral": _resp(text=detail_html),
        "https://x.de/immobilien/haus-poecking-mit-garten": _resp(text=detail_html),
    }
    client = _routed_client(routes)
    agent = _agent(listing_url="https://x.de/immobilien/")

    results = [r async for r in crawl_and_extract(agent, client)]

    assert len(results) == 3
    assert results[0].price_eur == 450000
    assert results[0].qm == 180.0
    assert results[0].plz == "82327"
    assert results[0].city == "Tutzing"
    assert results[0].address is None
    assert results[0].source == "agents"
    assert results[0].source_id.startswith("agent-1-")


@pytest.mark.asyncio
async def test_crawl_and_extract_returns_nothing_without_listing_url():
    client = _routed_client({})
    agent = _agent(listing_url=None)

    results = [r async for r in crawl_and_extract(agent, client)]

    assert results == []


@pytest.mark.asyncio
async def test_crawl_and_extract_skips_a_single_failing_detail_page():
    listing_html = """
    <html><body>
      <a href="/immobilien/villa-am-see-tutzing">A</a>
      <a href="/immobilien/wohnung-starnberg-zentral">B</a>
      <a href="/immobilien/haus-poecking-mit-garten">C</a>
    </body></html>
    """
    detail_html = "<html><body><h1>Villa am See</h1><p>450.000 € 180 m² 82327 Tutzing</p></body></html>"
    routes = {
        "https://x.de/immobilien/": _resp(text=listing_html),
        "https://x.de/immobilien/villa-am-see-tutzing": _resp(status_code=500),
        "https://x.de/immobilien/wohnung-starnberg-zentral": _resp(text=detail_html),
        "https://x.de/immobilien/haus-poecking-mit-garten": _resp(text=detail_html),
    }
    client = _routed_client(routes)
    agent = _agent(listing_url="https://x.de/immobilien/")

    results = [r async for r in crawl_and_extract(agent, client)]

    assert len(results) == 2


@pytest.mark.asyncio
async def test_crawl_and_extract_keeps_objects_distinct_despite_shared_footer_address():
    """Regression für den Dedup-Kollaps (Advisor-Fund): teilen sich alle
    Detailseiten dieselbe Impressum-Adresse im Footer und haben KEINE
    Preis-/Flächenangabe (z.B. "Preis auf Anfrage"), darf RawListing.address
    NICHT davon befüllt werden — sonst kollabieren alle Objekte auf denselben
    dedup_hash() (app/models.py: leere address -> Fallback source_id, gesetzte
    address -> address+qm+price als Hash-Basis, und qm/price sind hier auch
    beide None -> ohne den Fix wäre der Hash für alle drei identisch)."""
    listing_html = """
    <html><body>
      <a href="/immobilien/objekt-a">A</a>
      <a href="/immobilien/objekt-b">B</a>
      <a href="/immobilien/objekt-c">C</a>
    </body></html>
    """
    detail_html = "<html><body><h1>Objekt ohne Sachdaten</h1><footer>82327 Tutzing, Impressum</footer></body></html>"
    routes = {
        "https://x.de/immobilien/": _resp(text=listing_html),
        "https://x.de/immobilien/objekt-a": _resp(text=detail_html),
        "https://x.de/immobilien/objekt-b": _resp(text=detail_html),
        "https://x.de/immobilien/objekt-c": _resp(text=detail_html),
    }
    client = _routed_client(routes)
    agent = _agent(listing_url="https://x.de/immobilien/")

    results = [r async for r in crawl_and_extract(agent, client)]

    assert len(results) == 3
    assert all(r.address is None for r in results)
    hashes = {r.dedup_hash() for r in results}
    assert len(hashes) == 3
```

- [ ] **Step 3: Tests laufen lassen, sicherstellen dass sie fehlschlagen**

Run: `DB_PATH=./data/immo.db pytest tests/test_agent_handlers.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'app.sources.agent_handlers'`

- [ ] **Step 4: Tests grün bekommen**

Datei aus Step 1 anlegen.

Run: `DB_PATH=./data/immo.db pytest tests/test_agent_handlers.py -v`
Expected: PASS (4 Tests)

- [ ] **Step 5: Lint + Commit**

```bash
DB_PATH=./data/immo.db ruff check app/sources/agent_handlers.py tests/test_agent_handlers.py
git add app/sources/agent_handlers.py tests/test_agent_handlers.py
git commit -m "feat(agents): Crawl-Handler für vendor:*/detail_links (geteilt, plz/city statt address)"
```

---

### Task 5: `agent_handlers.py` — sitemap_objekte-Handler

**Files:**
- Modify: `app/sources/agent_handlers.py`
- Test: `tests/test_agent_handlers.py` (aus Task 4, wird ergänzt)

**Interfaces:**
- Consumes: `app.agent_cascade_detect.{DETAIL_RE, SITEMAP_OBJECT_RE}` (Task 1, bereits vorhanden), `_fetch_detail_listing` (Task 4, dieselbe Datei).
- Produces: `async def sitemap_objekte_handler(agent: Agent, client: httpx.AsyncClient) -> AsyncIterator[RawListing]`. Wird von Task 8 (`app/sources/agents_adapter.py`) für `sitemap_objekte` registriert.

- [ ] **Step 1: Import ergänzen und Handler anhängen**

Die Import-Zeile in `app/sources/agent_handlers.py`:

```python
from app.agent_cascade_detect import find_detail_links
```

wird zu:

```python
from app.agent_cascade_detect import DETAIL_RE, SITEMAP_OBJECT_RE, find_detail_links
```

Am Ende der Datei anhängen:

```python
async def _discover_sitemap_object_urls(client: httpx.AsyncClient, sitemap_url: str) -> list[str]:
    try:
        r = await client.get(sitemap_url)
        r.raise_for_status()
    except Exception as e:
        log.warning("agent_handlers.sitemap_fetch_failed", url=sitemap_url, error=str(e))
        return []

    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", r.text)
    subs = [u for u in locs if u.endswith(".xml") and SITEMAP_OBJECT_RE.search(u)]
    obj_urls: set[str] = {u for u in locs if DETAIL_RE.search(u)}
    for sub in subs[:3]:
        try:
            sr = await client.get(sub)
            sr.raise_for_status()
        except Exception as e:
            log.warning("agent_handlers.sub_sitemap_fetch_failed", url=sub, error=str(e))
            continue
        obj_urls.update(u for u in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sr.text) if DETAIL_RE.search(u))
    return sorted(obj_urls)


async def sitemap_objekte_handler(agent: Agent, client: httpx.AsyncClient) -> AsyncIterator[RawListing]:
    """Handler für `sitemap_objekte`: die in extraction['sitemap_url']
    festgehaltene Sitemap wird erneut abgerufen (der Onboarding-Probe hat sie
    nur klassifiziert, nicht für den Harvest behalten), Objekt-URLs per
    DETAIL_RE/SITEMAP_OBJECT_RE identifiziert (identisch zur Probe-Logik in
    app.agent_probe.probe_agent), dann wie crawl_and_extract je Detailseite
    extrahiert."""
    sitemap_url = (agent.extraction or {}).get("sitemap_url")
    if not sitemap_url:
        log.warning("agent_handlers.sitemap_no_url", agent_id=agent.id)
        return

    urls = (await _discover_sitemap_object_urls(client, sitemap_url))[:MAX_DETAIL_PAGES_PER_AGENT]
    for url in urls:
        listing = await _fetch_detail_listing(agent, client, url)
        if listing is not None:
            yield listing
        await asyncio.sleep(DETAIL_FETCH_DELAY_SECONDS)
```

- [ ] **Step 2: Failing Tests schreiben**

An `tests/test_agent_handlers.py` anhängen (Import-Zeile um `sitemap_objekte_handler` ergänzen):

```python
@pytest.mark.asyncio
async def test_sitemap_objekte_handler_follows_sub_sitemap_to_object_urls():
    index_xml = """
    <urlset>
      <url><loc>https://x.de/immobilie-sitemap.xml</loc></url>
    </urlset>
    """
    sub_xml = """
    <urlset>
      <url><loc>https://x.de/immobilien/villa-am-see-tutzing</loc></url>
      <url><loc>https://x.de/immobilien/wohnung-starnberg</loc></url>
    </urlset>
    """
    detail_html = "<html><body><h1>Villa</h1><p>600.000 € 200 m² 82327 Tutzing</p></body></html>"
    routes = {
        "https://x.de/sitemap.xml": _resp(text=index_xml),
        "https://x.de/immobilie-sitemap.xml": _resp(text=sub_xml),
        "https://x.de/immobilien/villa-am-see-tutzing": _resp(text=detail_html),
        "https://x.de/immobilien/wohnung-starnberg": _resp(text=detail_html),
    }
    client = _routed_client(routes)
    agent = _agent(extraction={"method": "sitemap_objekte", "sitemap_url": "https://x.de/sitemap.xml"})

    results = [r async for r in sitemap_objekte_handler(agent, client)]

    assert len(results) == 2
    assert all(r.price_eur == 600000 for r in results)


@pytest.mark.asyncio
async def test_sitemap_objekte_handler_returns_nothing_without_sitemap_url():
    client = _routed_client({})
    agent = _agent(extraction={})

    results = [r async for r in sitemap_objekte_handler(agent, client)]

    assert results == []
```

- [ ] **Step 3: Tests laufen lassen, sicherstellen dass die neuen fehlschlagen**

Run: `DB_PATH=./data/immo.db pytest tests/test_agent_handlers.py -v`
Expected: die 2 neuen Tests FAIL (`ImportError`), die 4 bestehenden PASS.

- [ ] **Step 4: Tests grün bekommen**

Implementierung aus Step 1 eintragen.

Run: `DB_PATH=./data/immo.db pytest tests/test_agent_handlers.py -v`
Expected: PASS (6 Tests)

- [ ] **Step 5: Lint + Commit**

```bash
DB_PATH=./data/immo.db ruff check app/sources/agent_handlers.py tests/test_agent_handlers.py
git add app/sources/agent_handlers.py tests/test_agent_handlers.py
git commit -m "feat(agents): sitemap_objekte-Handler"
```

---

### Task 6: `agent_handlers.py` — structured_data-Handler

**Files:**
- Modify: `app/sources/agent_handlers.py`
- Test: `tests/test_agent_handlers.py` (aus Task 4/5, wird ergänzt)

**Interfaces:**
- Consumes: `app.agent_cascade_detect.extract_jsonld_nodes` (Task 1), `app.agent_field_extract.{extract_fields, fields_from_jsonld, merge_fields}` (Task 2/3), `app.models.PropertyType`.
- Produces: `async def structured_data_handler(agent: Agent, client: httpx.AsyncClient) -> AsyncIterator[RawListing]`. Wird von Task 8 für `structured_data` registriert.

- [ ] **Step 1: Imports ergänzen und Handler anhängen**

Die Import-Zeilen in `app/sources/agent_handlers.py`:

```python
from app.agent_cascade_detect import DETAIL_RE, SITEMAP_OBJECT_RE, find_detail_links
from app.agent_field_extract import extract_fields
from app.db import Agent
from app.logging_setup import log
from app.models import RawListing
```

werden zu:

```python
from app.agent_cascade_detect import DETAIL_RE, SITEMAP_OBJECT_RE, extract_jsonld_nodes, find_detail_links
from app.agent_field_extract import extract_fields, fields_from_jsonld, merge_fields
from app.db import Agent
from app.logging_setup import log
from app.models import PropertyType, RawListing
```

Am Ende der Datei anhängen:

```python
_EMPTY_REGEX_FIELDS = {
    "title": None,
    "price_eur": None,
    "qm": None,
    "rooms": None,
    "plz": None,
    "city": None,
    "property_type": None,
}


async def structured_data_handler(agent: Agent, client: httpx.AsyncClient) -> AsyncIterator[RawListing]:
    """Handler für `structured_data`: JSON-LD-Knoten zuerst (reichhaltiger —
    schema.org-Felder statt Freitext-Regex), Regex-Extraktion aus dem
    Fließtext nur als Lückenfüller (merge_fields). Fehlt einem Knoten die
    `url` komplett, ist er nicht zu einer eigenen Detailseite verknüpfbar und
    wird übersprungen (kein sinnvoller RawListing ohne stabile URL)."""
    if not agent.listing_url:
        log.warning("agent_handlers.structured_no_listing_url", agent_id=agent.id)
        return

    try:
        r = await client.get(agent.listing_url)
        r.raise_for_status()
    except Exception as e:
        log.warning("agent_handlers.structured_listing_fetch_failed", agent_id=agent.id, error=str(e))
        return

    nodes = extract_jsonld_nodes(r.text)
    for node in nodes[:MAX_DETAIL_PAGES_PER_AGENT]:
        jsonld_fields = fields_from_jsonld(node)
        url = jsonld_fields.get("url")
        if not url:
            continue

        text = ""
        detail_html = ""
        try:
            dr = await client.get(url)
            dr.raise_for_status()
            detail_html = dr.text
            text = BeautifulSoup(detail_html, "html.parser").get_text(" ", strip=True)
        except Exception as e:
            log.warning("agent_handlers.structured_detail_fetch_failed", agent_id=agent.id, url=url, error=str(e))

        if text:
            regex_fields = extract_fields(detail_html, text)
        else:
            regex_fields = dict(_EMPTY_REGEX_FIELDS)

        merged = merge_fields(jsonld_fields, regex_fields)

        yield RawListing(
            source="agents",
            source_id=_source_id(agent.id, url),
            url=url,
            title=merged.get("title") or "Makler-Objekt",
            description=text[:2000] if text else None,
            price_eur=merged.get("price_eur"),
            qm=merged.get("qm"),
            rooms=merged.get("rooms"),
            plz=merged.get("plz"),
            city=merged.get("city"),
            property_type=merged.get("property_type") or PropertyType.UNKNOWN,
        )
        await asyncio.sleep(DETAIL_FETCH_DELAY_SECONDS)
```

- [ ] **Step 2: Failing Tests schreiben**

An `tests/test_agent_handlers.py` anhängen (Import-Zeile um `structured_data_handler` ergänzen):

```python
@pytest.mark.asyncio
async def test_structured_data_handler_reads_jsonld_and_fills_gaps_from_detail_page():
    listing_html = """
    <script type="application/ld+json">
    {"@type": "RealEstateListing", "name": "Villa am See",
     "url": "https://x.de/objekte/villa-am-see", "offers": {"price": 1200000}}
    </script>
    """
    detail_html = "<html><body><p>180 m² 6 Zimmer 82327 Tutzing</p></body></html>"
    routes = {
        "https://x.de/immobilien/": _resp(text=listing_html),
        "https://x.de/objekte/villa-am-see": _resp(text=detail_html),
    }
    client = _routed_client(routes)
    agent = _agent(listing_url="https://x.de/immobilien/")

    results = [r async for r in structured_data_handler(agent, client)]

    assert len(results) == 1
    assert results[0].title == "Villa am See"
    assert results[0].price_eur == 1200000
    assert results[0].qm == 180.0
    assert results[0].rooms == 6.0
    assert results[0].address is None


@pytest.mark.asyncio
async def test_structured_data_handler_skips_node_without_url():
    listing_html = """
    <script type="application/ld+json">
    {"@type": "Apartment", "name": "ETW ohne URL"}
    </script>
    """
    client = _routed_client({"https://x.de/immobilien/": _resp(text=listing_html)})
    agent = _agent(listing_url="https://x.de/immobilien/")

    results = [r async for r in structured_data_handler(agent, client)]

    assert results == []
```

- [ ] **Step 3: Tests laufen lassen, sicherstellen dass die neuen fehlschlagen**

Run: `DB_PATH=./data/immo.db pytest tests/test_agent_handlers.py -v`
Expected: die 2 neuen Tests FAIL (`ImportError`), die 6 bestehenden PASS.

- [ ] **Step 4: Tests grün bekommen**

Implementierung aus Step 1 eintragen.

Run: `DB_PATH=./data/immo.db pytest tests/test_agent_handlers.py -v`
Expected: PASS (8 Tests)

- [ ] **Step 5: Lint + Commit**

```bash
DB_PATH=./data/immo.db ruff check app/sources/agent_handlers.py tests/test_agent_handlers.py
git add app/sources/agent_handlers.py tests/test_agent_handlers.py
git commit -m "feat(agents): structured_data-Handler mit JSON-LD-Feldern + Regex-Fallback"
```

---

### Task 7: `agent_handlers.py` — feed_adapter-Handler

**Files:**
- Modify: `app/sources/agent_handlers.py`
- Test: `tests/test_agent_handlers.py` (aus Task 4-6, wird ergänzt)

**Interfaces:**
- Consumes: `app.agent_field_extract.{extract_fields, parse_feed_items}` (Task 2/3).
- Produces: `async def feed_adapter_handler(agent: Agent, client: httpx.AsyncClient) -> AsyncIterator[RawListing]`. Wird von Task 8 für `feed_adapter` registriert. Dieser Handler braucht KEINE `agent.listing_url` (nur `extraction['feed_url']`) — das ist die Grundlage für den HER-726-Fix in Task 8.

- [ ] **Step 1: Import ergänzen und Handler anhängen**

Die Import-Zeile in `app/sources/agent_handlers.py`:

```python
from app.agent_field_extract import extract_fields, fields_from_jsonld, merge_fields
```

wird zu:

```python
from app.agent_field_extract import extract_fields, fields_from_jsonld, merge_fields, parse_feed_items
```

Am Ende der Datei anhängen:

```python
async def feed_adapter_handler(agent: Agent, client: httpx.AsyncClient) -> AsyncIterator[RawListing]:
    """Handler für `feed_adapter`: Objekte kommen direkt aus den Feed-Items
    (Titel/Link/Beschreibung), kein zusätzlicher Detailseiten-Abruf nötig —
    der Feed selbst trägt bereits genug Text für die generische
    Feld-Extraktion (identisch zur Prüfung in app.agent_probe.validate_feed,
    hier für den tatsächlichen Ertrag statt nur für die Ja/Nein-Prüfung).
    Braucht bewusst KEINE agent.listing_url — nur extraction['feed_url']."""
    feed_url = (agent.extraction or {}).get("feed_url")
    if not feed_url:
        log.warning("agent_handlers.feed_no_url", agent_id=agent.id)
        return

    try:
        r = await client.get(feed_url)
        r.raise_for_status()
    except Exception as e:
        log.warning("agent_handlers.feed_fetch_failed", agent_id=agent.id, url=feed_url, error=str(e))
        return

    items = parse_feed_items(r.text)[:MAX_DETAIL_PAGES_PER_AGENT]
    for item in items:
        blob = f"{item['title']} {item['description']}"
        fields = extract_fields("", blob)
        yield RawListing(
            source="agents",
            source_id=_source_id(agent.id, item["link"]),
            url=item["link"],
            title=item["title"] or fields["title"],
            description=item["description"][:2000] or None,
            price_eur=fields["price_eur"],
            qm=fields["qm"],
            rooms=fields["rooms"],
            plz=fields["plz"],
            city=fields["city"],
            property_type=fields["property_type"],
        )
```

- [ ] **Step 2: Failing Tests schreiben**

An `tests/test_agent_handlers.py` anhängen (Import-Zeile um `feed_adapter_handler` ergänzen):

```python
@pytest.mark.asyncio
async def test_feed_adapter_handler_extracts_from_feed_items_directly():
    feed_xml = """
    <rss><channel>
      <item>
        <title>Haus in Tutzing, 450.000 €</title>
        <link>https://x.de/objekte/haus-tutzing</link>
        <description>140 m², 5 Zimmer, 82327 Tutzing</description>
      </item>
    </channel></rss>
    """
    client = _routed_client({"https://x.de/feed/": _resp(text=feed_xml)})
    agent = _agent(extraction={"method": "feed_adapter", "feed_url": "https://x.de/feed/"})

    results = [r async for r in feed_adapter_handler(agent, client)]

    assert len(results) == 1
    assert results[0].price_eur == 450000
    assert results[0].qm == 140.0
    assert results[0].url == "https://x.de/objekte/haus-tutzing"
    assert results[0].address is None


@pytest.mark.asyncio
async def test_feed_adapter_handler_returns_nothing_without_feed_url():
    client = _routed_client({})
    agent = _agent(extraction={})

    results = [r async for r in feed_adapter_handler(agent, client)]

    assert results == []
```

- [ ] **Step 3: Tests laufen lassen, sicherstellen dass die neuen fehlschlagen**

Run: `DB_PATH=./data/immo.db pytest tests/test_agent_handlers.py -v`
Expected: die 2 neuen Tests FAIL (`ImportError`), die 8 bestehenden PASS.

- [ ] **Step 4: Tests grün bekommen**

Implementierung aus Step 1 eintragen.

Run: `DB_PATH=./data/immo.db pytest tests/test_agent_handlers.py -v`
Expected: PASS (10 Tests)

- [ ] **Step 5: Lint + Commit**

```bash
DB_PATH=./data/immo.db ruff check app/sources/agent_handlers.py tests/test_agent_handlers.py
git add app/sources/agent_handlers.py tests/test_agent_handlers.py
git commit -m "feat(agents): feed_adapter-Handler (kein Detailseiten-Abruf nötig)"
```

---

### Task 8: `agents_adapter.py` — Registrierung, HER-726-Fix, zweistufiger Selbsttest

**Files:**
- Modify: `app/sources/agents_adapter.py`
- Modify: `tests/test_agents_adapter.py`

**Interfaces:**
- Consumes: `app.sources.agent_handlers.{crawl_and_extract, sitemap_objekte_handler, structured_data_handler, feed_adapter_handler}` (Task 4-7), `app.agent_cascade_detect.VENDORS`.
- Produces: `_default_extraction_methods() -> dict[str, ExtractionMethod]`, `_passes_self_test(listings: list[RawListing]) -> bool`, `MIN_RECRAWL_INTERVAL: timedelta` (Modul-Konstante, 20 Stunden — bewusst kein DB-Setting, siehe Global Constraints „Crawl-Frequenz-Guard"). `EXTRACTION_METHODS` ist ab diesem Task beim Modul-Import befüllt (21 Keys: 17 `vendor:<x>` + `detail_links` + `sitemap_objekte` + `structured_data` + `feed_adapter`) statt leer. Auf dem Erfolgspfad werden `last_checked`/`last_nonempty_at`/`last_listing_count` erstmals beschrieben (Spec §5.1, bisher nur auf den Fehlerpfaden gepflegt). `fetch()` überspringt einen Agent VOR jeder Handler-Auswahl, wenn dessen `last_checked` jünger als `MIN_RECRAWL_INTERVAL` ist.

**TDD-Reihenfolge dieses Tasks (Tests zuerst, dann Implementierung):**

- [ ] **Step 1: Bestehende Tests anpassen, die durch den kommenden Selbsttest fälschlich 0 Objekte liefern würden**

Drei Stellen in `tests/test_agents_adapter.py` liefern Fake-`RawListing`s ohne `price_eur`/`qm` — die würden den neuen Selbsttest nicht mehr bestehen, obwohl sie eigentlich den Weitergabe-Pfad testen sollen. `price_eur=450000` ergänzen:

In `test_fetch_yields_from_registered_method`:

```python
        yield RawListing(
            source="agents",
            source_id=f"agent-{agent.id}-1",
            url="https://example.de/angebote/1",
            title="Testobjekt",
            price_eur=450000,
            property_type=PropertyType.HAUS,
        )
```

In `test_fetch_isolates_a_failing_agent_from_the_rest`:

```python
        yield RawListing(
            source="agents", source_id=f"agent-{agent.id}", url=agent.listing_url, title="OK", price_eur=450000
        )
```

In `test_fetch_isolates_an_is_allowed_exception_from_the_rest`:

```python
        yield RawListing(
            source="agents", source_id=f"agent-{agent.id}", url=agent.listing_url, title="OK", price_eur=450000
        )
```

- [ ] **Step 2: Failing Tests für Registrierung, HER-726-Fix und zweistufigen Selbsttest schreiben**

Import-Block am Kopf von `tests/test_agents_adapter.py` um `from datetime import datetime, timedelta` ergänzen. An die Datei anhängen:

```python
def test_default_extraction_methods_cover_every_vendor_and_stage_key():
    from app.agent_cascade_detect import VENDORS
    from app.sources import agent_handlers
    from app.sources.agents_adapter import _default_extraction_methods

    methods = _default_extraction_methods()

    assert methods["detail_links"] is agent_handlers.crawl_and_extract
    assert methods["sitemap_objekte"] is agent_handlers.sitemap_objekte_handler
    assert methods["structured_data"] is agent_handlers.structured_data_handler
    assert methods["feed_adapter"] is agent_handlers.feed_adapter_handler
    for vendor in VENDORS:
        assert methods[f"vendor:{vendor}"] is agent_handlers.crawl_and_extract


@pytest.mark.asyncio
async def test_fetch_dispatches_feed_adapter_agent_without_listing_url(session, monkeypatch):
    """HER-726: feed_adapter-Agents haben keine listing_url, nur
    extraction['feed_url'] — das Gate darf sie deshalb nicht mehr blind
    überspringen."""
    agent_id = _make_agent(
        session,
        listing_url=None,
        extraction={"method": "fake", "feed_url": "https://example.de/feed/"},
    )

    async def fake_method(agent, client) -> AsyncIterator[RawListing]:
        yield RawListing(
            source="agents",
            source_id=f"agent-{agent.id}",
            url="https://example.de/objekte/1",
            title="Feed-Objekt",
            price_eur=450000,
        )

    EXTRACTION_METHODS["fake"] = fake_method
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=True))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert len(results) == 1
    assert results[0].source_id == f"agent-{agent_id}"


@pytest.mark.asyncio
async def test_fetch_downgrades_agent_on_first_ever_empty_run(session, monkeypatch):
    """Spec §7 Selbsttest vor Aktivierung: ein Makler, der NIE zuvor etwas
    geliefert hat (last_nonempty_at ist der Default None), wird bei 0
    verwertbaren Objekten sofort auf needs-manual-watch zurückgestuft."""
    agent_id = _make_agent(session)

    async def empty_field_method(agent, client) -> AsyncIterator[RawListing]:
        # Titel + URL vorhanden, aber weder Preis noch Fläche -> Selbsttest
        # muss das als "nicht verwertbar" werten.
        yield RawListing(source="agents", source_id="x", url="https://example.de/x", title="Ohne Sachdaten")

    EXTRACTION_METHODS["fake"] = empty_field_method
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=True))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert results == []
    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.coverage_status == "needs-manual-watch"
        assert "Selbsttest" in agent.coverage_reason


@pytest.mark.asyncio
async def test_fetch_passes_self_test_when_area_present_without_price(session, monkeypatch):
    """Spec §7: fehlender Preis allein ist KEIN Fehlschlag (Seeobjekte:
    "Preis auf Anfrage") — Fläche allein reicht als Sachattribut."""
    _make_agent(session)

    async def qm_only_method(agent, client) -> AsyncIterator[RawListing]:
        yield RawListing(
            source="agents", source_id="x", url="https://example.de/x", title="Preis auf Anfrage", qm=180.0
        )

    EXTRACTION_METHODS["fake"] = qm_only_method
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=True))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert len(results) == 1


@pytest.mark.asyncio
async def test_fetch_writes_last_checked_and_last_nonempty_at_on_success(session, monkeypatch):
    """Spec §5.1: 'Ein Status gilt nur mit frischem Beleg' -- last_checked/
    last_nonempty_at/last_listing_count müssen auch auf dem Erfolgspfad
    geschrieben werden, nicht nur bei robots-disallowed/Selbsttest-Downgrade
    (Advisor-Fund: waren bisher tote Spalten für funktionierende Agents)."""
    agent_id = _make_agent(session)

    async def fake_method(agent, client) -> AsyncIterator[RawListing]:
        yield RawListing(source="agents", source_id="x", url="https://example.de/x", title="OK", price_eur=450000)
        yield RawListing(source="agents", source_id="y", url="https://example.de/y", title="OK2", qm=100.0)

    EXTRACTION_METHODS["fake"] = fake_method
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=True))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert len(results) == 2
    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.coverage_status == "auto-harvested"
        assert agent.last_checked is not None
        assert agent.last_nonempty_at is not None
        assert agent.last_listing_count == 2


@pytest.mark.asyncio
async def test_fetch_tolerates_single_empty_run_after_prior_success(session, monkeypatch):
    """Spec §7 Bruch-Erkennung: ein Rezept gilt erst nach ZWEI
    aufeinanderfolgenden leeren Läufen als gebrochen (Zähl-Logik selbst ist
    Change-Gate-Arbeit, Phase 2c) -- ein einzelner transienter Leerlauf
    (z.B. ein 5xx) darf einen zuvor erfolgreichen Agent nicht sofort auf
    needs-manual-watch zurückstufen, sonst fliegt er dauerhaft aus dem Crawl
    (fetch() selektiert nur coverage_status == 'auto-harvested')."""
    agent_id = _make_agent(session, last_nonempty_at=datetime(2026, 8, 1))

    async def empty_method(agent, client) -> AsyncIterator[RawListing]:
        if False:
            yield RawListing(source="agents", source_id="x", url="https://x", title="x")

    EXTRACTION_METHODS["fake"] = empty_method
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=True))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert results == []
    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.coverage_status == "auto-harvested"
        assert agent.last_checked is not None


@pytest.mark.asyncio
async def test_fetch_skips_agent_recrawled_too_recently(session, monkeypatch):
    """UX-Entscheidung (Nutzer-Rückfrage zur Crawl-Frequenz): Makler-Sites
    werden unabhängig vom gewählten Poll-Intervall max. ~1x/Tag pro Agent neu
    gecrawlt. Ein last_checked von vor 2 Stunden ist zu frisch -- der Handler
    darf gar nicht erst aufgerufen werden."""
    _make_agent(session, last_checked=datetime.utcnow() - timedelta(hours=2))

    call_count = {"n": 0}

    async def fake_method(agent, client) -> AsyncIterator[RawListing]:
        call_count["n"] += 1
        yield RawListing(source="agents", source_id="x", url="https://x", title="x", price_eur=1)

    EXTRACTION_METHODS["fake"] = fake_method
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=True))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert results == []
    assert call_count["n"] == 0


@pytest.mark.asyncio
async def test_fetch_crawls_agent_when_last_checked_is_stale_enough(session, monkeypatch):
    """Gegenprobe: last_checked von vor 25 Stunden liegt über der
    MIN_RECRAWL_INTERVAL-Schwelle (20 Std.) -- der Agent wird ganz normal
    gecrawlt."""
    _make_agent(session, last_checked=datetime.utcnow() - timedelta(hours=25))

    async def fake_method(agent, client) -> AsyncIterator[RawListing]:
        yield RawListing(source="agents", source_id="x", url="https://x", title="x", price_eur=450000)

    EXTRACTION_METHODS["fake"] = fake_method
    monkeypatch.setattr("app.sources.agents_adapter.is_allowed", AsyncMock(return_value=True))

    adapter = AgentSiteSource()
    async with adapter:
        results = [raw async for raw in adapter.fetch()]

    assert len(results) == 1
```

- [ ] **Step 3: Tests laufen lassen, sicherstellen dass die neuen fehlschlagen**

Run: `DB_PATH=./data/immo.db pytest tests/test_agents_adapter.py -v`
Expected: die 8 neuen Tests FAIL (`_default_extraction_methods` fehlt noch / HER-726-Gate blockt noch / Selbsttest inkl. `last_nonempty_at`-Logik fehlt noch / `MIN_RECRAWL_INTERVAL`-Guard fehlt noch). Die 8 bestehenden Tests (inklusive der 3 in Step 1 angepassten) PASS weiterhin unverändert — sie ändern nur Testdaten, keine unter der alten Implementierung geprüfte Logik.

- [ ] **Step 4: `app/sources/agents_adapter.py` komplett ersetzen**

Kompletter neuer Dateiinhalt:

```python
"""Generischer, DB-getriebener Adapter für die agents-Tabelle.

Tritt NEBEN die statische REGISTRY, ersetzt sie nicht (Vollabdeckung-Spec
§5.3). Verteilt jede agents-Zeile mit coverage_status == "auto-harvested" an
die in EXTRACTION_METHODS registrierte Methode. Phase 2b registriert hier die
Kaskaden-Handler aus app.sources.agent_handlers: `vendor:<x>` (alle Einträge
aus app.agent_cascade_detect.VENDORS) und `detail_links` teilen sich EINEN
generischen Crawl+Extraktions-Handler (Phase 0 lieferte nur Vendor-
Fingerprints, keine Vendor-spezifischen Selektoren — `vendor:<x>` bleibt nur
Herkunfts-Tag), `sitemap_objekte`/`structured_data`/`feed_adapter` haben je
eigene Handler.

Zweistufiger Selbsttest (Vollabdeckung-Spec §7): das Ergebnis eines Handlers
wird gepuffert (Objektzahl pro Makler ist klein) und geprüft, bevor es
weitergereicht wird.
- Lieferte ein Makler NOCH NIE etwas (last_nonempty_at ist None) und der
  aktuelle Lauf liefert nichts Verwertbares, wird die optimistische, rein
  klassifikationsbasierte `auto-harvested`-Einstufung aus Phase 2a
  (app.agent_onboarding) sofort auf `needs-manual-watch` zurückgestuft
  ("Selbsttest vor Aktivierung").
- War der Makler zuvor erfolgreich, wird ein einzelner leerer Lauf NICHT als
  Rezept-Bruch gewertet (Spec §7 verlangt zwei aufeinanderfolgende leere
  Läufe) — nur `last_checked` wird aktualisiert, `coverage_status` bleibt
  `auto-harvested`. Der Zwei-Läufe-Zähler für echte Bruch-Erkennung ist
  Change-Gate-Arbeit (Phase 2c).
Auf dem Erfolgspfad werden `last_checked`/`last_nonempty_at`/
`last_listing_count` geschrieben — vorher waren diese Spalten nur auf den
Fehlerpfaden gepflegt, für funktionierende Agents also tot.

Crawl-Frequenz-Guard (UX-Entscheidung nach Nutzer-Rückfrage): AgentSiteSource
hat bewusst KEIN eigenes Poll-Intervall-Setting — ein zweites Dashboard-Feld
nur für Makler-Sites wäre für den Nutzer schwer einzuordnen. Stattdessen
erzwingt fetch() strukturell (nicht nur per UI-Warnung), dass ein einzelner
Agent höchstens alle MIN_RECRAWL_INTERVAL neu gecrawlt wird — unabhängig vom
gewählten poll_interval_minutes (Dashboard-Presets: 6 Std. bis 3 Tage). Die
schnellste UI-Option (6 Std.) würde ohne diesen Guard Makler-Sites 4x
häufiger crawlen als Spec §3 "Täglich" vorsieht. Portal-Quellen sind davon
nicht betroffen und folgen weiterhin exakt dem gewählten Intervall."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select

import app.db as db_module
from app.agent_cascade_detect import VENDORS
from app.db import Agent
from app.logging_setup import log
from app.models import RawListing
from app.robots import is_allowed
from app.sources import agent_handlers
from app.sources.base import SourceAdapter

ExtractionMethod = Callable[[Agent, httpx.AsyncClient], AsyncIterator[RawListing]]

# Höflichkeits-Guard (Spec §3/§8): unabhängig vom gewählten poll_interval_minutes
# wird ein einzelner Agent höchstens alle 20 Stunden neu gecrawlt (etwas unter
# 24h, um Scheduler-Jitter zu tolerieren, ohne einen Tag ganz auszulassen).
# Bewusst kein DB-Setting — das ist eine Höflichkeits-/Rechtsgrenze, kein
# Produkt-Feature, das der Nutzer versehentlich lockern können soll.
MIN_RECRAWL_INTERVAL = timedelta(hours=20)


def _default_extraction_methods() -> dict[str, ExtractionMethod]:
    methods: dict[str, ExtractionMethod] = {
        "detail_links": agent_handlers.crawl_and_extract,
        "sitemap_objekte": agent_handlers.sitemap_objekte_handler,
        "structured_data": agent_handlers.structured_data_handler,
        "feed_adapter": agent_handlers.feed_adapter_handler,
    }
    methods.update({f"vendor:{vendor}": agent_handlers.crawl_and_extract for vendor in VENDORS})
    return methods


EXTRACTION_METHODS: dict[str, ExtractionMethod] = _default_extraction_methods()


def _passes_self_test(listings: list[RawListing]) -> bool:
    """Vollabdeckung-Spec §7: ein Rezept wird aktiv, wenn es mindestens ein
    Objekt mit Titel, Detail-Link UND mindestens einem Sachattribut (Preis
    ODER Fläche) liefert. Fehlende Preise allein sind KEIN Fehlschlag — viele
    Seeobjekte tragen grundsätzlich "Preis auf Anfrage"."""
    for raw in listings:
        if not raw.title or not raw.url:
            continue
        if raw.price_eur is not None or raw.qm is not None:
            return True
    return False


class AgentSiteSource(SourceAdapter):
    """Ein Adapter-Objekt repräsentiert alle Makler-eigenen Websites
    zusammen — jede agents-Zeile wird einzeln isoliert verarbeitet, ein
    fehlschlagender Makler bricht nie den Gesamtlauf ab (Spec §7)."""

    name = "agents"

    async def fetch(self) -> AsyncIterator[RawListing]:
        assert self.client is not None
        with db_module.SessionLocal() as session:
            agents = list(session.scalars(select(Agent).where(Agent.coverage_status == "auto-harvested")))

        # `agents` sind detachte ORM-Instanzen — die Session ist schon zu. In
        # dieser Schleife nur lesend verwenden (inkl. agent.last_nonempty_at,
        # bereits Teil des initialen SELECTs); wer in die Agent-Zeile
        # zurückschreiben will, öffnet eine frische Session und lädt die Zeile
        # neu (wie die robots-disallowed-/Selbsttest-/Erfolgs-Zweige unten),
        # statt die detachte Instanz zu mutieren.
        for agent in agents:
            if agent.last_checked is not None and (datetime.utcnow() - agent.last_checked) < MIN_RECRAWL_INTERVAL:
                # Höflichkeits-Guard: unabhängig vom Poll-Intervall max. ~1x/Tag
                # pro Agent (siehe Modul-Docstring "Crawl-Frequenz-Guard").
                log.debug("agents_adapter.recrawl_too_soon", agent_id=agent.id)
                continue

            method_name = (agent.extraction or {}).get("method")
            if not method_name:
                log.warning("agents_adapter.no_method", agent_id=agent.id, agent_name=agent.name)
                continue
            handler = EXTRACTION_METHODS.get(method_name)
            if handler is None:
                log.warning("agents_adapter.unknown_method", agent_id=agent.id, method=method_name)
                continue
            # HER-726: feed_adapter braucht keine listing_url, sondern
            # extraction["feed_url"] — das Gate darf ihn deshalb nicht mehr
            # unbedingt an listing_url binden.
            feed_url = (agent.extraction or {}).get("feed_url")
            if not agent.listing_url and not feed_url:
                log.warning("agents_adapter.no_listing_url", agent_id=agent.id)
                continue

            try:
                robots_check_url = agent.listing_url or feed_url
                if not await is_allowed(self.client, robots_check_url):
                    log.info("agents_adapter.robots_disallowed", agent_id=agent.id, url=robots_check_url)
                    with db_module.SessionLocal() as session:
                        db_agent = session.get(Agent, agent.id)
                        if db_agent is not None:
                            db_agent.coverage_status = "robots-disallowed"
                            db_agent.coverage_reason = f"robots.txt verbietet Zugriff auf {robots_check_url}"
                            db_agent.last_checked = datetime.utcnow()
                            session.commit()
                    continue

                harvested = [raw async for raw in handler(agent, self.client)]
                now = datetime.utcnow()

                if not _passes_self_test(harvested):
                    if agent.last_nonempty_at is None:
                        # Nie zuvor erfolgreich -> die optimistische
                        # Phase-2a-Klassifikation war falsch, sofort
                        # zurückstufen (Spec §7: Selbsttest vor Aktivierung).
                        log.info("agents_adapter.self_test_failed", agent_id=agent.id, count=len(harvested))
                        with db_module.SessionLocal() as session:
                            db_agent = session.get(Agent, agent.id)
                            if db_agent is not None:
                                db_agent.coverage_status = "needs-manual-watch"
                                db_agent.coverage_reason = (
                                    f"Selbsttest fehlgeschlagen: Handler {method_name!r} lieferte "
                                    "keine verwertbaren Objekte (Titel, Detail-Link und mind. ein "
                                    "Sachattribut nötig)."
                                )
                                db_agent.last_checked = now
                                session.commit()
                    else:
                        # War zuvor erfolgreich -> ein einzelner leerer Lauf
                        # ist noch kein Rezept-Bruch (Spec §7: Bruch erst nach
                        # ZWEI aufeinanderfolgenden leeren Läufen — die dafür
                        # nötige Zähl-Logik ist Change-Gate-Arbeit, Phase 2c).
                        # Nur last_checked aktualisieren, Status bleibt
                        # auto-harvested.
                        log.info("agents_adapter.empty_run_after_prior_success", agent_id=agent.id)
                        with db_module.SessionLocal() as session:
                            db_agent = session.get(Agent, agent.id)
                            if db_agent is not None:
                                db_agent.last_checked = now
                                session.commit()
                    continue

                with db_module.SessionLocal() as session:
                    db_agent = session.get(Agent, agent.id)
                    if db_agent is not None:
                        db_agent.last_checked = now
                        db_agent.last_nonempty_at = now
                        db_agent.last_listing_count = len(harvested)
                        session.commit()

                for raw in harvested:
                    yield raw
            except Exception as e:
                log.error(
                    "agents_adapter.agent_failed",
                    agent_id=agent.id,
                    agent_name=agent.name,
                    error=str(e),
                )
                continue
```

- [ ] **Step 5: Tests laufen lassen, sicherstellen dass alle grün sind**

Run: `DB_PATH=./data/immo.db pytest tests/test_agents_adapter.py -v`
Expected: PASS (16 Tests)

- [ ] **Step 6: Vollständige Regression + Lint + Commit**

```bash
DB_PATH=./data/immo.db pytest -v
DB_PATH=./data/immo.db ruff check app/sources/agents_adapter.py tests/test_agents_adapter.py
git add app/sources/agents_adapter.py tests/test_agents_adapter.py
git commit -m "feat(agents): Kaskaden-Handler registrieren, HER-726-Gate fixen, zweistufiger Selbsttest + Crawl-Frequenz-Guard (Spec §3/§7/§8)"
```

---

### Task 9: Dashboard — Erklärzeile zum Makler-Crawl-Rhythmus

**Files:**
- Modify: `frontend/src/components/settings/MechanicsTab.tsx`

**Interfaces:**
- Consumes: nichts Neues — reine Präsentations-Ergänzung, keine neue Query/Mutation/Prop.
- Produces: nichts, das andere Tasks konsumieren — rein informativer UI-Text.

**Kontext (UX-Entscheidung nach Nutzer-Rückfrage):** Task 8 sorgt strukturell dafür, dass Makler-Sites unabhängig vom gewählten Poll-Intervall max. ~1×/Tag pro Agent gecrawlt werden (`MIN_RECRAWL_INTERVAL`). Dashboard-technisch bleibt es bewusst bei EINEM Intervall-Setting (`poll_interval_minutes`, Presets 6 Std./12 Std./1-3 Tage) — kein zweites, verwirrendes Feld nur für Makler-Sites. Damit die Diskrepanz zwischen „eingestelltem Intervall" und „tatsächlichem Makler-Crawl-Rhythmus" für den Nutzer nicht wie ein stiller Bug wirkt, bekommt der bestehende „Crawling (Poll)"-Block im Dashboard eine kurze erklärende Zeile.

- [ ] **Step 1: Erklärzeile im Crawling-Block ergänzen**

In `frontend/src/components/settings/MechanicsTab.tsx` steht der „Crawling (Poll)"-Block aktuell so (Ausschnitt):

```tsx
        <div className="flex items-center gap-3 flex-wrap" style={{ opacity: (s.poll_enabled ?? true) ? 1 : 0.4, pointerEvents: (s.poll_enabled ?? true) ? 'auto' : 'none' }}>
          {([
            [360, '6 Std.'], [720, '12 Std.'], [1440, '1 Tag'], [2880, '2 Tage'], [4320, '3 Tage'],
          ] as [number, string][]).map(([v, label]) => (
            <button
              key={v}
              onClick={() => pollMut.mutate(v)}
              className="px-3 py-1.5 rounded-lg text-sm font-medium border transition-all"
              style={
                s.poll_interval_minutes === v
                  ? { background: 'var(--accent)', color: 'white', borderColor: 'var(--accent)' }
                  : { color: 'var(--fg)', borderColor: 'var(--border)', background: 'white' }
              }
            >
              {label}
            </button>
          ))}
        </div>
      </div>
```

Direkt nach dem schließenden `</div>` der Preset-Buttons (noch innerhalb des äußeren „Crawling (Poll)"-`<div>`) eine neue, gedämpfte Info-Zeile einfügen:

```tsx
        <div className="flex items-center gap-3 flex-wrap" style={{ opacity: (s.poll_enabled ?? true) ? 1 : 0.4, pointerEvents: (s.poll_enabled ?? true) ? 'auto' : 'none' }}>
          {([
            [360, '6 Std.'], [720, '12 Std.'], [1440, '1 Tag'], [2880, '2 Tage'], [4320, '3 Tage'],
          ] as [number, string][]).map(([v, label]) => (
            <button
              key={v}
              onClick={() => pollMut.mutate(v)}
              className="px-3 py-1.5 rounded-lg text-sm font-medium border transition-all"
              style={
                s.poll_interval_minutes === v
                  ? { background: 'var(--accent)', color: 'white', borderColor: 'var(--accent)' }
                  : { color: 'var(--fg)', borderColor: 'var(--border)', background: 'white' }
              }
            >
              {label}
            </button>
          ))}
        </div>
        <p className="text-xs mt-2" style={{ color: 'var(--muted)' }}>
          Makler-Websites werden aus Rücksicht auf robots.txt max. 1×/Tag pro Website neu geprüft — unabhängig von diesem Intervall.
        </p>
      </div>
```

- [ ] **Step 2: Typecheck**

```bash
cd frontend && npx tsc --noEmit
```

Expected: keine neuen Fehler (reine JSX-Text-Ergänzung, keine Typänderung).

- [ ] **Step 3: Visuelle Verifikation**

Günstigste ausreichende Stufe (DoD §5 „Verifizierer-Wahl"): kein Playwright nötig für eine statische Text-Ergänzung ohne Interaktivität. `npm run dev` im `frontend/`-Verzeichnis starten, Dashboard öffnen, zum Settings-Tab „Mechanik" navigieren, prüfen dass die neue Zeile unter den Poll-Interval-Buttons erscheint und im Light-Theme lesbar ist (`--muted`-Token).

- [ ] **Step 4: Commit**

```bash
cd frontend && npm run build
cd ..
git add frontend/src/components/settings/MechanicsTab.tsx
git commit -m "feat(dashboard): Erklärzeile zum Makler-Crawl-Rhythmus im Poll-Intervall-Block"
```

---

### Task 10: Manueller End-to-End-Test + Doku-Update

**Files:**
- Modify: `docs/STATUS.md`

**Interfaces:**
- Consumes: alle vorherigen Tasks (voller Kaskaden-Handler-Stack).
- Produces: verifizierter End-to-End-Durchlauf gegen eine echte Makler-Site, aktualisierter Status-Snapshot.

- [ ] **Step 1: Vollständige Test-Suite + Lint gegen den gesamten Diff laufen lassen**

```bash
DB_PATH=./data/immo.db pytest -v
DB_PATH=./data/immo.db ruff check .
```

Expected: alle Tests PASS (bestehende 55 Tests aus Phase 0-2a + alle in diesem Plan neuen/geänderten), `ruff check .` sauber.

- [ ] **Step 2: Manueller End-to-End-Test gegen eine echte Domain**

Kein automatisierter Test — echter Netzwerk-Abruf gegen eine reale Site, per Hand einmalig verifiziert. Eine der 21 vom Nutzer benannten Referenz-Makler aus `docs/superpowers/phase0-messbericht.md` (z.B. `bs-immo.de`, bereits als Portal-Adapter-Domain bekannt, oder eine der dort gelisteten Domains) zuerst über Phase 2a onboarden, dann über Phase 2b tatsächlich ernten:

```bash
DB_PATH=./data/immo.db python3 -c "
import app.db as db_module
db_module.init_db()
from app.db import Agent
with db_module.SessionLocal() as s:
    a = Agent(name='E2E Test Makler', verified_domain='bs-immo.de')
    s.add(a)
    s.commit()
    print('agent id:', a.id)
"
DB_PATH=./data/immo.db python -m scripts.onboard_agents
```

Notiere die von `onboard_agents` ausgegebene `coverage_status`/`extraction` für den Test-Agent. Ist `coverage_status == "auto-harvested"`, den echten Harvest anstoßen:

```bash
DB_PATH=./data/immo.db python3 -c "
import asyncio
import httpx
import app.db as db_module
from app.db import Agent
from app.robots import USER_AGENT
from app.sources.agents_adapter import AgentSiteSource

async def main():
    adapter = AgentSiteSource()
    async with adapter:
        count = 0
        async for raw in adapter.fetch():
            count += 1
            print(raw.title, raw.price_eur, raw.qm, raw.plz, raw.city, raw.address, raw.url)
        print('total:', count)

asyncio.run(main())
"
```

Erwartung: entweder mindestens ein `RawListing` mit plausiblem Titel/Preis-oder-Fläche wird ausgegeben (mit `address` gleich `None` — Diskriminierungsfrage: ist `plz`/`city` das Objekt oder das Makler-Büro? bei Stichprobe eyeballen, ob sie sich zwischen Objekten unterscheiden), ODER — falls der Selbsttest fehlschlägt — die Agent-Zeile steht danach auf `coverage_status == "needs-manual-watch"` mit einer `coverage_reason`, die "Selbsttest" enthält (per `DB_PATH=./data/immo.db python3 -c "..."` gegen `Agent`-Tabelle nachprüfbar). Beide Ausgänge sind ein gültiger, erklärter Zustand — ein drittes Ergebnis (stille Exception, leerer Lauf ohne Statusänderung) ist ein Bug.

Test-Agent danach wieder löschen:

```bash
DB_PATH=./data/immo.db python3 -c "
import app.db as db_module
from app.db import Agent
with db_module.SessionLocal() as s:
    s.query(Agent).filter(Agent.name == 'E2E Test Makler').delete()
    s.commit()
"
```

- [ ] **Step 3: `docs/STATUS.md` aktualisieren**

Im Abschnitt „Offener Backlog" den Satz zu Phase 2 aktualisieren: `Phase 0, Phase 1 und Phase 2a` wird zu `Phase 0, Phase 1, Phase 2a und Phase 2b`, und der Hinweis auf den „nächsten Schritt" wird auf Phase 2c (Change-Gate-Fingerprint + Zwei-Läufe-Zähler für Bruch-Erkennung + Playwright-Rendering für JS-Shells/403-Sites) umgeschrieben, mit Verweis auf die in diesem Plan bewusst zurückgestellten Punkte (siehe Self-Review-Notizen).

- [ ] **Step 4: Commit**

```bash
git add docs/STATUS.md
git commit -m "docs(status): Phase 2b (Feld-Extraktor + Cascade-Handler) abgeschlossen, nächster Schritt Phase 2c"
```

---

## Self-Review-Notizen

- **Spec-Abdeckung:** §3 (Crawl-Frequenz „Täglich" — strukturell erzwungen über `MIN_RECRAWL_INTERVAL` statt nur empfohlen, siehe „Crawl-Frequenz-Guard" unten) → Task 8/9. §4.1 (alle fünf auto-harvestbaren Kaskadenstufen bekommen Handler; `vendor:<x>` teilt sich einen Handler mit `detail_links`, begründet durch den Phase-0-Befund, dass nur Fingerprints, keine Selektoren gemessen wurden) → Task 4-7. §5.1 (`extraction`-Sparse-Key-Zugriff ausschließlich per `.get()`; `last_checked`/`last_nonempty_at`/`last_listing_count` erstmals auf dem Erfolgspfad beschrieben) → durchgängig in Task 5/7/8 geprüft, Task 8 explizit. §7 (zweistufiger Selbsttest: sofortige Rückstufung nur ohne jeden bisherigen Erfolg, Toleranz für einen einzelnen leeren Lauf danach, fehlender Preis kein Fehlschlag, kein stiller Verlust) → Task 8. §8 (Crawl-Budget, keine granulare Pro-Detailseite-robots-Prüfung, konsistent mit Phase 2a; Höflichkeits-Guard gegen zu häufigen Recrawl) → Task 4 Docstring + Task 8 + Global Constraints.
- **Crawl-Frequenz-Guard geprüft (UX-Entscheidung nach Nutzer-Rückfrage, Fix in Task 8/9):** `AgentSiteSource` bekommt bewusst kein eigenes Poll-Intervall-Setting — das gemeinsame `poll_interval_minutes` bleibt die einzige Nutzer-Stellschraube (Dashboard-Presets 6 Std. bis 3 Tage), Portal-Quellen sind unverändert schnell pollbar. Der `MIN_RECRAWL_INTERVAL`-Guard in `AgentSiteSource.fetch()` (Task 8) macht die Spec-§3-Vorgabe „Täglich" strukturell wahr, unabhängig davon, welches Intervall der Nutzer wählt — auch bei versehentlich zu schnell gewähltem Intervall kann kein Makler öfter als ~1x/Tag gecrawlt werden. Regressionstests: `test_fetch_skips_agent_recrawled_too_recently`, `test_fetch_crawls_agent_when_last_checked_is_stale_enough`. Task 9 macht das Verhalten im Dashboard transparent, statt es als stille Diskrepanz zwischen eingestelltem Intervall und tatsächlichem Makler-Crawl-Rhythmus zu belassen.
- **Bewusst außerhalb dieses Plans** (siehe auch Global Constraints): Change-Gate-Fingerprint (Phase 2c) — dieser Plan holt bei jedem Lauf alle gefundenen Detailseiten neu ab, ohne Delta-Erkennung; das ist Spec §8s „nur für neue Objekte" noch nicht erfüllt, sondern bewusst auf Phase 2c verschoben (Pipeline-Dedup via `dedup_hash` verhindert zwar doppelte DB-Einträge, spart aber keine Netzwerk-Requests). Der Zwei-Läufe-Zähler für echte Bruch-Erkennung (Phase 2c, siehe Task 8). Playwright-Rendering für JS-Shells/403-Sites (Phase 2c). LLM-Rezept für die `learned_recipe`-Stufe (Phase 2d). SSRF-Guard auf `verified_domain` (HER-725, vor Phase 3 — `verified_domain` bleibt weiterhin nur manuell gesetzt). Refactor der vier bestehenden Portal-Adapter auf den neuen `agent_field_extract`-Extraktor (Scope-Entscheidung, kein Regressionsrisiko für aktive Quellen).
- **Bekannte Lücke im Toleranz-Zweig, bewusst auf Phase 2c verschoben (Final-Review-Fund, nach Nutzer-Rückfrage zurückgestellt):** Der „ein einzelner leerer Lauf nach vorherigem Erfolg wird toleriert"-Zweig (Task 8, `_passes_self_test` False + `agent.last_nonempty_at` gesetzt) unterscheidet aktuell NICHT zwischen zwei strukturell verschiedenen Fällen: (a) der Handler liefert 0 Objekte (echter transienter Ausfall — worum es bei diesem Zweig ursprünglich ging) und (b) der Handler liefert N Objekte, von denen KEINS den Selbsttest besteht (z.B. nach einem Website-Relaunch, der Preis/Fläche aus dem Markup entfernt hat — ein echtes Rezept-Problem). Beide Fälle landen aktuell im selben Toleranz-Pfad: `coverage_status` bleibt `auto-harvested`, nur `last_checked` wird aktualisiert, kein Log oberhalb von `info`-Level, die extrahierten aber selbsttest-untauglichen Objekte werden bei jedem Lauf erneut still verworfen. Das ist der „stille Verlust", den Spec §7 verbietet — hier eingeführt durch den Zweig, der eigentlich vor einem anderen stillen Verlust (Rückstufung wegen eines einzelnen transienten 5xx) schützen sollte. Phase 2c baut ohnehin den Zwei-Läufe-Zähler für echte Bruch-Erkennung — die Fall-(a)/(b)-Unterscheidung (bei Fall (b) mind. `log.warning` mit Objektzahl, als Grundlage für den künftigen Zähler) gehört dorthin, statt hier eine Zwischenlösung zu bauen.
- **Typkonsistenz geprüft:** `find_detail_links(html, base, limit=None)` (Task 1) → `crawl_and_extract` (Task 4) ruft mit `limit=None` auf, `agent_probe.py` (unverändert, Task 1 ist rückwärtskompatibel) ruft weiter ohne `limit` und bekommt weiterhin eine 3er-Stichprobe. `extract_jsonld_nodes(html) -> list[dict]` (Task 1) → `structured_data_handler` (Task 6) iteriert direkt über die Knoten-Dicts. `extract_fields(html, text) -> dict` mit exakt den Keys `title`/`price_eur`/`qm`/`rooms`/`plz`/`city`/`property_type` (Task 2, KEIN `address`-Key) wird identisch in allen vier Handlern (Task 4/5/6/7) konsumiert. `fields_from_jsonld(node) -> dict` mit Keys `title`/`url`/`price_eur`/`qm`/`rooms`/`plz`/`city` (Task 3, ebenfalls kein `address`-Key) und `merge_fields(primary, fallback) -> dict` (Task 3) → `structured_data_handler` (Task 6) — Key-Namen stimmen überein (das zusätzliche `property_type`-Feld aus den Regex-Fields wird von `merge_fields` korrekt ergänzt, da JSON-LD-Fields dieses Feld gar nicht führen; `_EMPTY_REGEX_FIELDS` in Task 6 führt exakt dieselben Keys wie `extract_fields()`s Rückgabe). `ExtractionMethod`-Signatur (`Callable[[Agent, httpx.AsyncClient], AsyncIterator[RawListing]]`, unverändert aus Phase 1) wird von allen vier Handlern erfüllt und in `_default_extraction_methods()` (Task 8) konsistent registriert.
- **Dedup-Sicherheit geprüft (Advisor-Fund, Fix in Task 2-8 durchgängig):** kein Handler befüllt `RawListing.address` — alle vier setzen `plz`/`city`. `dedup_hash()` (`app/models.py`) fällt damit bei Agent-Listings immer auf `source_id` zurück (pro-URL-eindeutig), auch wenn `qm`/`price_eur` fehlen. Regressionstest: `test_crawl_and_extract_keeps_objects_distinct_despite_shared_footer_address` (Task 4) simuliert den ursprünglichen Bug (identische Footer-Adresse auf allen Detailseiten, keine Preis-/Flächenangabe) und prüft explizit auf drei unterschiedliche `dedup_hash()`-Werte. `app/pipeline.py`s Regionsfilter (`_location_ok`, liest `address`/`title`/`city`/`plz`) und Geocoding (`_resolve_location`, liest `address`/`plz`/`city`) funktionieren mit nur `plz`/`city` unverändert weiter — beide Funktionen sind bereits auf alle drei Felder ausgelegt.
- **Selbsttest-Eskalation geprüft (Advisor-Fund, Fix in Task 8):** ein einzelner leerer Handler-Lauf stuft einen zuvor erfolgreichen Agent NICHT zurück (`test_fetch_tolerates_single_empty_run_after_prior_success`), ein Agent ohne jeden bisherigen Erfolg dagegen sofort (`test_fetch_downgrades_agent_on_first_ever_empty_run`). Der Erfolgspfad schreibt `last_checked`/`last_nonempty_at`/`last_listing_count` (`test_fetch_writes_last_checked_and_last_nonempty_at_on_success`) — vorher blieben diese Spec-§5.1-Felder für funktionierende Agents tot.
- **Regressionsschutz für Phase-2a-Code geprüft:** `find_detail_links()`-Signaturänderung ist additiv (Default `limit=3` identisch zum bisherigen Verhalten) — `app/agent_probe.py` (Phase 2a, ungetestet in diesem Plan) bleibt unverändert lauffähig. Die drei in Task 8 Step 1 angepassten Tests in `tests/test_agents_adapter.py` ändern nur Testdaten (zusätzliches `price_eur`), nicht die geprüfte Verhaltenslogik selbst.

## Execution Handoff

Plan gespeichert unter `docs/superpowers/plans/2026-08-11-makler-vollabdeckung-phase2b-feld-extraktor-cascade-handler.md`. Zwei Ausführungsoptionen:

**1. Subagent-Driven (empfohlen)** — frischer Subagent pro Task, Review zwischen den Tasks, schnelle Iteration

**2. Inline Execution** — Ausführung in dieser Session über executing-plans, Batch-Ausführung mit Checkpoints

Welcher Ansatz?
