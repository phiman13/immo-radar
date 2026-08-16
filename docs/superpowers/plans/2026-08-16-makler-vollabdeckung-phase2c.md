# Makler-Vollabdeckung Phase 2c Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Härtet die bestehende Makler-Vollabdeckung (Phase 2b): spart Netzwerk-Requests auf bereits bekannte Objekte (Change-Gate), erkennt echte Rezept-Brüche statt einzelner Ausreißer (Zwei-Läufe-Zähler), und schaltet — nur wenn eine Probe das rechtfertigt — Playwright-Rendering für JS-Shell-/WAF-blockierte Makler-Sites frei.

**Architecture:** Drei unabhängige Bausteine auf derselben Kernschleife (`AgentSiteSource.fetch()` in `app/sources/agents_adapter.py` + die vier `ExtractionMethod`-Handler in `app/sources/agent_handlers.py`). Change-Gate erweitert die Handler-Signatur um einen `known_urls`-Parameter (aus der `Listing`-Tabelle abgeleitet, kein neues Schema). Der Zwei-Läufe-Zähler ersetzt den bisherigen Toleranz-Zweig durch ein neues Zählfeld auf `Agent`. Playwright nutzt einen neuen `browser_session()`-Context-Manager, der einen einzigen Chromium-Prozess pro Agent-Lauf wiederverwendet, statt (wie das bestehende `fetch_html()`) einen pro Aufruf zu starten.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 (ORM), httpx (AsyncMock in Tests), Playwright (async_playwright), pytest + pytest-asyncio.

## Global Constraints

- `REFRESH_WINDOW = timedelta(days=7)` (Change-Gate-Refresh-Fenster, Spec §3.3).
- `MAX_DETAIL_PAGES_PER_AGENT = 40` bleibt unverändert (bestehende Konstante).
- Neues Feld `Agent.consecutive_empty_runs: int` (`default=0, server_default="0"`), Downgrade auf `needs-manual-watch` erst bei Zähler ≥ 2 (Spec §4).
- `Agent.extraction["render"] = "browser"` als neuer, optionaler Sparse-Key (Spec §5.2) — nur setzen, wenn eine Probe (Task 7) das für die jeweilige Domain bestätigt hat.
- Handler-Signatur (`ExtractionMethod`) wird um einen dritten Parameter `known_urls: dict[str, datetime] | None = None` erweitert — **mit Default**, damit alle 32 bestehenden Testaufrufe (14 in `tests/test_agents_adapter.py`, 18 in `tests/test_agent_handlers.py`) unverändert bleiben (Spec verlangt keine Breaking Changes an bestehenden Tests).
- `Listing.is_active` bleibt in dieser Phase unangetastet (nirgends auf `False` gesetzt — keine Delisting-Erkennung, siehe Spec §1/§8).
- Kein Playwright-Produktivcode ohne vorherige Go/No-Go-Probe (Task 7) — nur Domains mit erfolgreicher Probe bekommen `render: "browser"` + `auto-harvested`.
- Testkonvention: `AsyncMock`-URL-Routing für httpx (kein `respx`), SQLite-`tmp_path`-Fixture für DB-Tests, `EXTRACTION_METHODS.clear()`-Autouse-Fixture für `test_agents_adapter.py`.

---

### Task 1: Change-Gate — `_urls_to_fetch()`-Helfer + Signatur-Plumbing

**Files:**
- Modify: `app/sources/agent_handlers.py` (neue Konstante + neue Funktion + Signaturänderung an allen vier Handlern)
- Test: `tests/test_agent_handlers.py`

**Interfaces:**
- Produces: `REFRESH_WINDOW: timedelta` (Modul-Konstante). `_urls_to_fetch(all_urls: list[str], known_urls: dict[str, datetime], now: datetime) -> list[str]` — reine Funktion, kein I/O. Neue Handler-Signatur (alle vier Funktionen): drittes Positional-Argument `known_urls: dict[str, datetime] | None = None`.
- Consumes: nichts Neues aus anderen Tasks.

**Kontext:** Aktuell holt jeder Handler bei jedem Lauf bis zu 40 Detailseiten neu, egal ob das Objekt schon bekannt ist. `_urls_to_fetch()` filtert die von einem Handler entdeckte URL-Liste auf das, was tatsächlich neu gefetcht werden muss: neue URLs (nicht in `known_urls`) + überfällige URLs (`known_urls[url]` älter als `REFRESH_WINDOW`). Wenn das 0 URLs ergäbe, obwohl `known_urls` nicht leer ist, wird stattdessen die am längsten nicht bestätigte bekannte URL erzwungen (Canary-Regel) — sonst liefert der Handler 0 Objekte und der Selbsttest in `agents_adapter.py` (`_passes_self_test`) würde einen Rezept-Bruch vortäuschen, obwohl nur das Change-Gate gegriffen hat.

Dieser Task verdrahtet nur die Signatur und die reine Filterlogik — **nicht** deren Aufruf innerhalb der vier Handler-Schleifen (das ist Task 2/3). Am Ende dieses Tasks verhält sich der Code exakt wie vorher; `known_urls` wird entgegengenommen, aber noch nicht benutzt.

- [ ] **Step 1: Failing Test für `_urls_to_fetch()` schreiben**

Füge am Ende von `tests/test_agent_handlers.py` hinzu:

```python
from datetime import datetime, timedelta

from app.sources.agent_handlers import REFRESH_WINDOW, _urls_to_fetch


def test_urls_to_fetch_includes_new_urls_not_in_known_urls():
    now = datetime(2026, 8, 16, 12, 0, 0)
    result = _urls_to_fetch(["https://x.de/a", "https://x.de/b"], {}, now)
    assert result == ["https://x.de/a", "https://x.de/b"]


def test_urls_to_fetch_skips_fresh_known_urls():
    now = datetime(2026, 8, 16, 12, 0, 0)
    known = {"https://x.de/a": now - timedelta(days=1)}
    result = _urls_to_fetch(["https://x.de/a"], known, now)
    assert result == []


def test_urls_to_fetch_refetches_stale_known_urls():
    now = datetime(2026, 8, 16, 12, 0, 0)
    known = {"https://x.de/a": now - REFRESH_WINDOW - timedelta(hours=1)}
    result = _urls_to_fetch(["https://x.de/a"], known, now)
    assert result == ["https://x.de/a"]


def test_urls_to_fetch_mixes_new_and_stale_but_omits_fresh():
    now = datetime(2026, 8, 16, 12, 0, 0)
    known = {
        "https://x.de/fresh": now - timedelta(days=1),
        "https://x.de/stale": now - REFRESH_WINDOW - timedelta(hours=1),
    }
    result = _urls_to_fetch(
        ["https://x.de/fresh", "https://x.de/stale", "https://x.de/new"], known, now
    )
    assert result == ["https://x.de/stale", "https://x.de/new"]


def test_urls_to_fetch_canary_forces_oldest_known_url_when_all_fresh():
    now = datetime(2026, 8, 16, 12, 0, 0)
    known = {
        "https://x.de/a": now - timedelta(days=1),
        "https://x.de/b": now - timedelta(hours=2),
    }
    result = _urls_to_fetch(["https://x.de/a", "https://x.de/b"], known, now)
    assert result == ["https://x.de/a"]


def test_urls_to_fetch_returns_empty_when_no_urls_discovered_at_all():
    now = datetime(2026, 8, 16, 12, 0, 0)
    assert _urls_to_fetch([], {}, now) == []
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag verifizieren**

Run: `pytest tests/test_agent_handlers.py -k urls_to_fetch -v`
Expected: FAIL mit `ImportError: cannot import name 'REFRESH_WINDOW'` (bzw. `_urls_to_fetch`)

- [ ] **Step 3: `REFRESH_WINDOW` + `_urls_to_fetch()` implementieren**

In `app/sources/agent_handlers.py`, nach der bestehenden Zeile `DETAIL_FETCH_DELAY_SECONDS = 0.5` (Zeile 38) einfügen:

```python
from datetime import datetime, timedelta

# Change-Gate-Fingerprint (Vollabdeckung-Spec Phase 2c §3): eine bereits
# bekannte Detailseite wird erst nach REFRESH_WINDOW erneut abgerufen, damit
# Preis-/Status-Änderungen (ListingHistory in app.pipeline._upsert()) nicht
# einfrieren, aber der tägliche Crawl nicht jedes Mal alle Objekte neu holt.
REFRESH_WINDOW = timedelta(days=7)
```

(Der `from datetime import datetime, timedelta`-Import ersetzt die bisherige `from datetime import ...`-Zeile, falls schon vorhanden — prüfen, ob `datetime`/`timedelta` bereits importiert sind, und nur die fehlenden ergänzen statt zu duplizieren.)

Danach, vor `def crawl_and_extract(...)`, neue Funktion einfügen:

```python
def _urls_to_fetch(all_urls: list[str], known_urls: dict[str, datetime], now: datetime) -> list[str]:
    """Change-Gate-Fingerprint (Vollabdeckung-Spec Phase 2c §3): liefert nur
    URLs, die noch nie gesehen wurden ODER deren letzte Bestätigung länger
    als REFRESH_WINDOW zurückliegt. Canary-Regel: wären es 0 (weil alle
    bekannten URLs frisch sind), wird stattdessen die am längsten nicht
    bestätigte bekannte URL erzwungen -- sonst liefert der Handler in einem
    "alles frisch"-Lauf 0 Objekte, und der Selbsttest in
    app.sources.agents_adapter._passes_self_test() würde fälschlich einen
    Rezept-Bruch auslösen, obwohl nur das Change-Gate gegriffen hat."""
    due = [url for url in all_urls if url not in known_urls or (now - known_urls[url]) >= REFRESH_WINDOW]
    if due:
        return due
    known_among_all = [url for url in all_urls if url in known_urls]
    if not known_among_all:
        return []
    oldest = min(known_among_all, key=lambda u: known_urls[u])
    return [oldest]
```

Dann die Signatur aller vier Handler um den neuen, optionalen dritten Parameter erweitern (Verhalten in diesem Task noch unverändert — `known_urls` wird entgegengenommen, aber nirgends gelesen):

```python
async def crawl_and_extract(
    agent: Agent, client: httpx.AsyncClient, known_urls: dict[str, datetime] | None = None
) -> AsyncIterator[RawListing]:
```

```python
async def sitemap_objekte_handler(
    agent: Agent, client: httpx.AsyncClient, known_urls: dict[str, datetime] | None = None
) -> AsyncIterator[RawListing]:
```

```python
async def structured_data_handler(
    agent: Agent, client: httpx.AsyncClient, known_urls: dict[str, datetime] | None = None
) -> AsyncIterator[RawListing]:
```

```python
async def feed_adapter_handler(
    agent: Agent, client: httpx.AsyncClient, known_urls: dict[str, datetime] | None = None
) -> AsyncIterator[RawListing]:
```

Zuletzt in `app/sources/agents_adapter.py` den `ExtractionMethod`-Type-Alias (Zeile 64) aktualisieren:

```python
ExtractionMethod = Callable[[Agent, httpx.AsyncClient, "dict[str, datetime] | None"], AsyncIterator[RawListing]]
```

`from datetime import datetime` ist in `agents_adapter.py` bereits importiert (Zeile 50) — keine Änderung am Import nötig.

- [ ] **Step 4: Tests laufen lassen, Erfolg verifizieren**

Run: `pytest tests/test_agent_handlers.py tests/test_agents_adapter.py -v`
Expected: PASS — alle neuen `_urls_to_fetch`-Tests grün, alle 32 bestehenden Handler-Aufrufe (2 Argumente) weiterhin grün, da `known_urls` einen Default hat.

- [ ] **Step 5: Lint + Commit**

```bash
ruff check app/sources/agent_handlers.py app/sources/agents_adapter.py tests/test_agent_handlers.py
git add app/sources/agent_handlers.py app/sources/agents_adapter.py tests/test_agent_handlers.py
git commit -m "feat(agents): Change-Gate-Helfer _urls_to_fetch() + Handler-Signatur-Plumbing"
```

---

### Task 2: Change-Gate verdrahten — `crawl_and_extract` + `sitemap_objekte_handler`

**Files:**
- Modify: `app/sources/agent_handlers.py`
- Test: `tests/test_agent_handlers.py`

**Interfaces:**
- Consumes: `_urls_to_fetch()` und `REFRESH_WINDOW` aus Task 1.
- Produces: keine neuen Symbole — nur Verhaltensänderung in den beiden genannten Handlern.

**Kontext:** Beide Handler entdecken zuerst die volle URL-Liste (per `find_detail_links()` bzw. `_discover_sitemap_object_urls()`), kappen sie dann auf `MAX_DETAIL_PAGES_PER_AGENT`. Die Reihenfolge ist wichtig: das Change-Gate muss **vor** dem Cap auf die volle entdeckte Liste angewendet werden — sonst würden neue Objekte, die erst nach Position 40 in der Discovery-Reihenfolge auftauchen, nie berücksichtigt, weil der Cap sie schon vorher abschneidet.

- [ ] **Step 1: Failing Tests schreiben**

Füge in `tests/test_agent_handlers.py` hinzu (nutzt die bestehenden `_resp`/`_routed_client`/`_agent`-Helfer aus derselben Datei):

```python
from datetime import datetime, timedelta


@pytest.mark.asyncio
async def test_crawl_and_extract_skips_fresh_known_url():
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
        "https://x.de/immobilien/wohnung-starnberg-zentral": _resp(text=detail_html),
        "https://x.de/immobilien/haus-poecking-mit-garten": _resp(text=detail_html),
    }
    client = _routed_client(routes)
    agent = _agent(listing_url="https://x.de/immobilien/")
    now = datetime.utcnow()
    known_urls = {"https://x.de/immobilien/villa-am-see-tutzing": now - timedelta(days=1)}

    results = [r async for r in crawl_and_extract(agent, client, known_urls)]

    urls_fetched = {r.url for r in results}
    assert "https://x.de/immobilien/villa-am-see-tutzing" not in urls_fetched
    assert urls_fetched == {
        "https://x.de/immobilien/wohnung-starnberg-zentral",
        "https://x.de/immobilien/haus-poecking-mit-garten",
    }


@pytest.mark.asyncio
async def test_crawl_and_extract_refetches_stale_known_url():
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
    now = datetime.utcnow()
    known_urls = {
        "https://x.de/immobilien/villa-am-see-tutzing": now - timedelta(days=30),
    }

    results = [r async for r in crawl_and_extract(agent, client, known_urls)]

    assert {r.url for r in results} == {
        "https://x.de/immobilien/villa-am-see-tutzing",
        "https://x.de/immobilien/wohnung-starnberg-zentral",
        "https://x.de/immobilien/haus-poecking-mit-garten",
    }


@pytest.mark.asyncio
async def test_sitemap_objekte_handler_skips_fresh_known_url():
    sitemap_xml = """<?xml version="1.0"?>
    <urlset>
      <url><loc>https://x.de/immobilien/villa-am-see-tutzing</loc></url>
      <url><loc>https://x.de/immobilien/wohnung-starnberg-zentral</loc></url>
    </urlset>"""
    detail_html = (
        "<html><body><h1>Villa am See</h1>"
        "<p>Kaufpreis: 450.000 € 180 m² 6 Zimmer 82327 Tutzing</p></body></html>"
    )
    routes = {
        "https://x.de/sitemap.xml": _resp(text=sitemap_xml),
        "https://x.de/immobilien/wohnung-starnberg-zentral": _resp(text=detail_html),
    }
    client = _routed_client(routes)
    agent = _agent(extraction={"method": "sitemap_objekte", "sitemap_url": "https://x.de/sitemap.xml"})
    now = datetime.utcnow()
    known_urls = {"https://x.de/immobilien/villa-am-see-tutzing": now - timedelta(hours=1)}

    results = [r async for r in sitemap_objekte_handler(agent, client, known_urls)]

    assert {r.url for r in results} == {"https://x.de/immobilien/wohnung-starnberg-zentral"}
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag verifizieren**

Run: `pytest tests/test_agent_handlers.py -k "skips_fresh_known_url or refetches_stale_known_url" -v`
Expected: FAIL — alle drei liefern noch alle URLs (Change-Gate noch nicht verdrahtet).

- [ ] **Step 3: Change-Gate in `crawl_and_extract` verdrahten**

In `app/sources/agent_handlers.py`, `crawl_and_extract()` (aktuell Zeile 110-135), die Zeile

```python
    _, urls = find_detail_links(r.text, agent.listing_url, limit=None)
    urls = urls[:MAX_DETAIL_PAGES_PER_AGENT]
```

ersetzen durch:

```python
    _, discovered_urls = find_detail_links(r.text, agent.listing_url, limit=None)
    urls = _urls_to_fetch(discovered_urls, known_urls or {}, datetime.utcnow())[:MAX_DETAIL_PAGES_PER_AGENT]
```

- [ ] **Step 4: Change-Gate in `sitemap_objekte_handler` verdrahten**

In derselben Datei, `sitemap_objekte_handler()` (aktuell Zeile 170-187), die Zeile

```python
    urls = (await _discover_sitemap_object_urls(client, sitemap_url))[:MAX_DETAIL_PAGES_PER_AGENT]
```

ersetzen durch:

```python
    discovered_urls = await _discover_sitemap_object_urls(client, sitemap_url)
    urls = _urls_to_fetch(discovered_urls, known_urls or {}, datetime.utcnow())[:MAX_DETAIL_PAGES_PER_AGENT]
```

- [ ] **Step 5: Tests laufen lassen, Erfolg verifizieren**

Run: `pytest tests/test_agent_handlers.py -v`
Expected: PASS — neue Change-Gate-Tests grün, alle bestehenden `crawl_and_extract`/`sitemap_objekte_handler`-Tests weiterhin grün (sie rufen ohne `known_urls` auf, also `known_urls or {} == {}`, also `_urls_to_fetch` liefert alle URLs unverändert — identisches Verhalten zu vorher).

- [ ] **Step 6: Lint + Commit**

```bash
ruff check app/sources/agent_handlers.py tests/test_agent_handlers.py
git add app/sources/agent_handlers.py tests/test_agent_handlers.py
git commit -m "feat(agents): Change-Gate in crawl_and_extract + sitemap_objekte_handler aktivieren"
```

---

### Task 3: Change-Gate verdrahten — `structured_data_handler` + `feed_adapter_handler`

**Files:**
- Modify: `app/sources/agent_handlers.py`
- Test: `tests/test_agent_handlers.py`

**Interfaces:**
- Consumes: `_urls_to_fetch()` aus Task 1 (identisch zu Task 2).
- Produces: keine neuen Symbole.

**Kontext:** Diese beiden Handler resolven die Ziel-URL erst **pro Knoten/Item** innerhalb ihrer jeweiligen Schleife (JSON-LD-Knoten bzw. Feed-Items), nicht als vorab bekannte flache Liste wie in Task 2. Das Change-Gate muss deshalb **vor** dem Detail-Fetch jedes einzelnen Items geprüft werden, nicht als vorgeschalteter Listen-Filter. Der Discovery-Schritt (JSON-LD-Knoten parsen bzw. Feed-Items parsen) bleibt vollständig — nur der `client.get(url)`-Aufruf zum Detail-Holen wird übersprungen, wenn `url` frisch bekannt ist.

- [ ] **Step 1: Failing Tests schreiben**

```python
@pytest.mark.asyncio
async def test_structured_data_handler_skips_detail_fetch_for_fresh_known_url():
    listing_html = """
    <html><body>
    <script type="application/ld+json">
    {"@type": "Product", "name": "Altbauwohnung", "url": "https://x.de/objekt/1",
     "offers": {"price": "399000"}, "floorSize": {"value": "95"}}
    </script>
    </body></html>
    """
    routes = {"https://x.de/immobilien/": _resp(text=listing_html)}
    client = _routed_client(routes)
    agent = _agent(listing_url="https://x.de/immobilien/", extraction={"method": "structured_data"})
    now = datetime.utcnow()
    known_urls = {"https://x.de/objekt/1": now - timedelta(hours=1)}

    results = [r async for r in structured_data_handler(agent, client, known_urls)]

    assert results == []
    assert "https://x.de/objekt/1" not in {c.args[0] for c in client.get.await_args_list}


@pytest.mark.asyncio
async def test_feed_adapter_handler_skips_detail_fetch_for_fresh_known_url():
    feed_xml = """<?xml version="1.0"?>
    <rss><channel>
      <item>
        <title>Reihenhaus Tutzing 450.000 € 140 m²</title>
        <link>https://x.de/feed-item/1</link>
        <description>Schönes Reihenhaus</description>
      </item>
    </channel></rss>"""
    routes = {"https://x.de/feed.xml": _resp(text=feed_xml)}
    client = _routed_client(routes)
    agent = _agent(extraction={"method": "feed_adapter", "feed_url": "https://x.de/feed.xml"})
    now = datetime.utcnow()
    known_urls = {"https://x.de/feed-item/1": now - timedelta(hours=1)}

    results = [r async for r in feed_adapter_handler(agent, client, known_urls)]

    assert results == []
```

Hinweis: `feed_adapter_handler` extrahiert Felder direkt aus dem Feed-Item (kein zweiter Detail-Request nötig, siehe Docstring) — das Change-Gate greift hier nicht bei einem HTTP-Request, sondern beim **Yield** des Objekts selbst: ein bereits bekanntes, frisches Feed-Item wird nicht erneut als `RawListing` ausgegeben.

- [ ] **Step 2: Tests laufen lassen, Fehlschlag verifizieren**

Run: `pytest tests/test_agent_handlers.py -k "skips_detail_fetch_for_fresh_known_url" -v`
Expected: FAIL — beide Handler liefern noch das Objekt / holen noch die Detailseite.

- [ ] **Step 3: Change-Gate in `structured_data_handler` verdrahten**

In `app/sources/agent_handlers.py`, `structured_data_handler()` (aktuell Zeile 201-266), in der `for node in nodes[:MAX_DETAIL_PAGES_PER_AGENT]:`-Schleife, direkt nach der bestehenden Host-Prüfung

```python
        if urlparse(url).netloc != listing_host:
            log.warning("agent_handlers.structured_url_off_host", agent_id=agent.id, url=url)
            continue
```

einfügen:

```python
        known = known_urls or {}
        if url in known and (datetime.utcnow() - known[url]) < REFRESH_WINDOW:
            continue
```

- [ ] **Step 4: Change-Gate in `feed_adapter_handler` verdrahten**

In derselben Datei, `feed_adapter_handler()` (aktuell Zeile 269-314), in der `for item in items:`-Schleife, direkt nach der bestehenden Host-Prüfung

```python
        if urlparse(link).netloc != feed_host:
            log.warning("agent_handlers.feed_link_off_host", agent_id=agent.id, url=link)
            continue
```

einfügen:

```python
        known = known_urls or {}
        if link in known and (datetime.utcnow() - known[link]) < REFRESH_WINDOW:
            continue
```

- [ ] **Step 5: Tests laufen lassen, Erfolg verifizieren**

Run: `pytest tests/test_agent_handlers.py -v`
Expected: PASS — alle Tests inkl. der beiden neuen grün, bestehende Tests unverändert (sie rufen ohne `known_urls` auf → `known = {}` → keine Skip-Bedingung greift je).

- [ ] **Step 6: Lint + Commit**

```bash
ruff check app/sources/agent_handlers.py tests/test_agent_handlers.py
git add app/sources/agent_handlers.py tests/test_agent_handlers.py
git commit -m "feat(agents): Change-Gate in structured_data_handler + feed_adapter_handler aktivieren"
```

---

### Task 4: `known_urls` aus der DB bauen und in `AgentSiteSource.fetch()` verdrahten

**Files:**
- Modify: `app/sources/agents_adapter.py`
- Test: `tests/test_agents_adapter.py`

**Interfaces:**
- Consumes: `ExtractionMethod`-Signatur aus Task 1 (Handler akzeptieren jetzt `known_urls` als drittes Argument).
- Produces: `AgentSiteSource._known_urls_for_agent(agent_id: int) -> dict[str, datetime]` — neue Methode, ab hier wird sie beim Handler-Dispatch in `fetch()` genutzt.

**Kontext:** Erst dieser Task aktiviert das Change-Gate für echte Agent-Läufe — Task 1-3 haben nur die Handler-seitige Filterlogik gebaut, aber noch niemand füllt `known_urls` mit echten Daten. Jede Agent-Listing landet bereits in `Listing` mit `source="agents"`, `source_id=f"agent-{agent_id}-{hash}"` und `url`/`last_seen_at` (siehe `app/sources/agent_handlers.py::_source_id`, `app/pipeline.py::_upsert`). Der literale Bindestrich direkt nach der Agent-ID im `source_id`-Format verhindert Präfix-Kollisionen zwischen z.B. Agent 1 und Agent 12 (`"agent-1-".startswith`-artiger `LIKE`-Vergleich matcht `"agent-12-..."` nicht, da an der entsprechenden Position `'-'` vs. `'2'` steht).

- [ ] **Step 1: Failing Test schreiben**

Füge in `tests/test_agents_adapter.py` hinzu (nutzt die bestehenden `session`-Fixture, `_make_agent`-Helper und `clean_extraction_methods`-Autouse-Fixture derselben Datei):

```python
from app.db import Listing


def _make_listing(session, **overrides) -> None:
    defaults = dict(
        dedup_hash=f"hash-{overrides.get('url', 'x')}",
        source="agents",
        source_id="agent-1-abc123",
        url="https://x.de/objekt/1",
        title="Testobjekt",
        last_seen_at=datetime.utcnow(),
    )
    defaults.update(overrides)
    with session() as s:
        s.add(Listing(**defaults))
        s.commit()


@pytest.mark.asyncio
async def test_fetch_passes_known_urls_from_existing_listings_to_handler(session, monkeypatch):
    agent_id = _make_agent(session, id=1)
    known_seen_at = datetime.utcnow() - timedelta(days=2)
    _make_listing(
        session,
        dedup_hash="hash-known",
        source_id=f"agent-{agent_id}-known",
        url="https://x.de/objekt/known",
        last_seen_at=known_seen_at,
    )
    captured_known_urls = {}

    async def fake_method(agent, client, known_urls=None) -> AsyncIterator[RawListing]:
        captured_known_urls.update(known_urls or {})
        return
        yield  # pragma: no cover - macht die Funktion zum Async-Generator

    EXTRACTION_METHODS["fake"] = fake_method
    client = AsyncMock()
    monkeypatch.setattr("app.robots.is_allowed", AsyncMock(return_value=True))

    source = AgentSiteSource()
    source.client = client
    [_ async for _ in source.fetch()]

    assert captured_known_urls == {"https://x.de/objekt/known": known_seen_at}


@pytest.mark.asyncio
async def test_fetch_does_not_leak_other_agents_listings_into_known_urls(session, monkeypatch):
    agent_id = _make_agent(session, id=1, name="Agent Eins")
    _make_agent(session, id=12, name="Agent Zwölf")
    _make_listing(
        session,
        dedup_hash="hash-other-agent",
        source_id="agent-12-xyz789",
        url="https://y.de/objekt/other",
        last_seen_at=datetime.utcnow(),
    )
    captured_known_urls = {}

    async def fake_method(agent, client, known_urls=None) -> AsyncIterator[RawListing]:
        captured_known_urls.update(known_urls or {})
        return
        yield  # pragma: no cover

    EXTRACTION_METHODS["fake"] = fake_method
    client = AsyncMock()
    monkeypatch.setattr("app.robots.is_allowed", AsyncMock(return_value=True))

    source = AgentSiteSource()
    source.client = client
    [_ async for _ in source.fetch()]

    assert captured_known_urls == {}
```

Hinweis: `_make_agent()` erzeugt standardmäßig `extraction={"method": "fake"}` (siehe bestehender Helper in derselben Datei) — das passt zu `EXTRACTION_METHODS["fake"] = fake_method` oben.

- [ ] **Step 2: Tests laufen lassen, Fehlschlag verifizieren**

Run: `pytest tests/test_agents_adapter.py -k "known_urls" -v`
Expected: FAIL — `captured_known_urls` bleibt leer, weil `fetch()` noch keine `known_urls` an den Handler übergibt.

- [ ] **Step 3: `_known_urls_for_agent()` implementieren und in `fetch()` verdrahten**

In `app/sources/agents_adapter.py`, Import ergänzen (`select` ist schon importiert, `Listing` fehlt noch):

```python
from app.db import Agent, Listing
```

Neue Methode auf `AgentSiteSource` einfügen, direkt vor `_write_agent()`:

```python
    def _known_urls_for_agent(self, agent_id: int) -> dict[str, datetime]:
        """Change-Gate-Fingerprint (Vollabdeckung-Spec Phase 2c §3): liest
        bestehende Listing-URLs + deren last_seen_at für diesen Agenten aus
        der Listing-Tabelle -- kein neues Schema, jede Agent-Listing trägt
        das schon. Nutzt self.session (offene Aufrufer-Transaktion) wenn
        vorhanden, sonst eine kurzlebige eigene Session -- analog zu
        _write_agent(). Der literale Bindestrich direkt nach der Agent-ID im
        source_id-Format (f"agent-{agent_id}-{hash}", siehe
        app.sources.agent_handlers._source_id) verhindert Präfix-Kollisionen
        zwischen z.B. Agent 1 und Agent 12."""
        stmt = select(Listing.url, Listing.last_seen_at).where(
            Listing.source == "agents",
            Listing.source_id.like(f"agent-{agent_id}-%"),
        )
        if self.session is not None:
            rows = self.session.execute(stmt).all()
            return {url: last_seen for url, last_seen in rows}
        with db_module.SessionLocal() as session:
            rows = session.execute(stmt).all()
            return {url: last_seen for url, last_seen in rows}
```

In `fetch()`, die bestehende Handler-Aufrufzeile

```python
                harvested = [raw async for raw in handler(agent, self.client)]
```

ersetzen durch:

```python
                known_urls = self._known_urls_for_agent(agent.id)
                harvested = [raw async for raw in handler(agent, self.client, known_urls)]
```

- [ ] **Step 4: Bestehende Test-Doubles in `test_agents_adapter.py` auf 3 Parameter erweitern (zwingend, nicht optional)**

`fetch()` ruft ab jetzt `handler(agent, self.client, known_urls)` mit 3 Positional-Argumenten auf. Alle 14 bestehenden Test-Doubles in `tests/test_agents_adapter.py` sind aktuell als `async def fake_method(agent, client)` (bzw. `flaky_method`/`empty_field_method`/`qm_only_method`/`empty_method`) mit nur 2 Parametern definiert — ohne Erweiterung schlägt Step 5 garantiert mit `TypeError: fake_method() takes 2 positional arguments but 3 were given` fehl, das ist keine bloße Möglichkeit.

`grep -n "async def .*(agent, client)" tests/test_agents_adapter.py` liefert die exakten Zeilennummern. Jede der 14 Fundstellen einzeln per `Edit`-Tool anpassen — der dritte Parameter wird in keiner dieser bestehenden Test-Doubles benutzt, nur entgegengenommen:

```python
    async def fake_method(agent, client) -> AsyncIterator[RawListing]:
```

wird zu:

```python
    async def fake_method(agent, client, known_urls=None) -> AsyncIterator[RawListing]:
```

(entsprechend für `flaky_method`/`empty_field_method`/`qm_only_method`/`empty_method` mit ihrem jeweiligen Funktionsnamen, jeweils an allen Fundstellen dieses Namens).

- [ ] **Step 5: Tests laufen lassen, Erfolg verifizieren**

Run: `pytest tests/test_agents_adapter.py -v`
Expected: PASS — beide neuen Tests aus Step 1 grün, alle 14 zuvor angepassten Test-Doubles weiterhin grün.

- [ ] **Step 6: Lint + Commit**

```bash
ruff check app/sources/agents_adapter.py tests/test_agents_adapter.py
git add app/sources/agents_adapter.py tests/test_agents_adapter.py
git commit -m "feat(agents): known_urls aus Listing-Tabelle bauen und Change-Gate aktivieren"
```

---

### Task 5: Zwei-Läufe-Zähler für echte Rezept-Bruch-Erkennung

**Files:**
- Modify: `app/db.py` (neues Feld + Migration)
- Modify: `app/sources/agents_adapter.py` (Toleranz-Zweig ersetzen)
- Test: `tests/test_agents_adapter.py`
- Test: `tests/test_db.py` (falls vorhanden — sonst Migration nur über `test_agents_adapter.py`'s `session`-Fixture abgedeckt, die `Base.metadata.create_all()` nutzt und damit automatisch die neue Spalte bekommt)

**Interfaces:**
- Consumes: nichts aus Task 1-4.
- Produces: `Agent.consecutive_empty_runs: int` (neues Feld).

**Kontext:** Der bestehende Toleranz-Zweig in `AgentSiteSource.fetch()` (aktuell Zeile 196-221) toleriert JEDEN einzelnen leeren/selbsttest-untauglichen Lauf unbegrenzt oft, ohne Zähler — das widerspricht Spec §7 ("zwei aufeinanderfolgende leere Läufe"). Zusätzlich unterscheidet er nicht zwischen Fall (a) 0 Objekte (vermutlich transient) und Fall (b) N>0 Objekte, aber keins besteht den Selbsttest (vermutlich echter Rezept-Bruch, z.B. nach Website-Relaunch).

- [ ] **Step 1: Failing Tests schreiben**

Füge in `tests/test_agents_adapter.py` hinzu:

```python
@pytest.mark.asyncio
async def test_fetch_increments_counter_on_first_empty_run_after_success(session, monkeypatch):
    agent_id = _make_agent(session, last_nonempty_at=datetime.utcnow() - timedelta(days=1))

    async def empty_method(agent, client, known_urls=None) -> AsyncIterator[RawListing]:
        return
        yield  # pragma: no cover

    EXTRACTION_METHODS["fake"] = empty_method
    client = AsyncMock()
    monkeypatch.setattr("app.robots.is_allowed", AsyncMock(return_value=True))

    source = AgentSiteSource()
    source.client = client
    [_ async for _ in source.fetch()]

    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.consecutive_empty_runs == 1
        assert agent.coverage_status == "auto-harvested"


@pytest.mark.asyncio
async def test_fetch_downgrades_after_two_consecutive_empty_runs(session, monkeypatch):
    agent_id = _make_agent(
        session, last_nonempty_at=datetime.utcnow() - timedelta(days=2), consecutive_empty_runs=1
    )

    async def empty_method(agent, client, known_urls=None) -> AsyncIterator[RawListing]:
        return
        yield  # pragma: no cover

    EXTRACTION_METHODS["fake"] = empty_method
    client = AsyncMock()
    monkeypatch.setattr("app.robots.is_allowed", AsyncMock(return_value=True))

    source = AgentSiteSource()
    source.client = client
    [_ async for _ in source.fetch()]

    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.consecutive_empty_runs == 2
        assert agent.coverage_status == "needs-manual-watch"
        assert "zwei" in agent.coverage_reason.lower()


@pytest.mark.asyncio
async def test_fetch_resets_counter_on_success_after_prior_empty_run(session, monkeypatch):
    agent_id = _make_agent(
        session, last_nonempty_at=datetime.utcnow() - timedelta(days=2), consecutive_empty_runs=1
    )

    async def success_method(agent, client, known_urls=None) -> AsyncIterator[RawListing]:
        yield RawListing(
            source="agents",
            source_id=f"agent-{agent.id}-1",
            url="https://x.de/objekt/1",
            title="Villa",
            price_eur=500000,
        )

    EXTRACTION_METHODS["fake"] = success_method
    client = AsyncMock()
    monkeypatch.setattr("app.robots.is_allowed", AsyncMock(return_value=True))

    source = AgentSiteSource()
    source.client = client
    [_ async for _ in source.fetch()]

    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.consecutive_empty_runs == 0


@pytest.mark.asyncio
async def test_fetch_distinguishes_case_b_zero_objects_all_failing_self_test(session, monkeypatch, caplog):
    agent_id = _make_agent(
        session, last_nonempty_at=datetime.utcnow() - timedelta(days=1), consecutive_empty_runs=0
    )

    async def half_broken_method(agent, client, known_urls=None) -> AsyncIterator[RawListing]:
        yield RawListing(
            source="agents",
            source_id=f"agent-{agent.id}-1",
            url="https://x.de/objekt/1",
            title="Objekt ohne Preis oder Fläche",
        )

    EXTRACTION_METHODS["fake"] = half_broken_method
    client = AsyncMock()
    monkeypatch.setattr("app.robots.is_allowed", AsyncMock(return_value=True))

    import logging

    caplog.set_level(logging.WARNING)
    source = AgentSiteSource()
    source.client = client
    [_ async for _ in source.fetch()]

    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.consecutive_empty_runs == 1
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag verifizieren**

Run: `pytest tests/test_agents_adapter.py -k "consecutive_empty_runs or case_b" -v`
Expected: FAIL mit `AttributeError: 'Agent' object has no attribute 'consecutive_empty_runs'` bzw. `TypeError` beim `_make_agent(..., consecutive_empty_runs=1)`-Aufruf.

- [ ] **Step 3: Feld + Migration in `app/db.py` ergänzen**

In der `Agent`-Klasse (Zeile 151-184), nach der bestehenden Zeile

```python
    last_listing_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
```

einfügen:

```python
    consecutive_empty_runs: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
```

In `init_db()` (Zeile 216-236), der `ddl`-Liste eine neue Zeile hinzufügen (Agent-Tabelle heißt `agents`, siehe `__tablename__ = "agents"` in der Klasse):

```python
            "ALTER TABLE agents ADD COLUMN consecutive_empty_runs INTEGER DEFAULT 0",
```

- [ ] **Step 4: Toleranz-Zweig in `AgentSiteSource.fetch()` durch Zähler-Logik ersetzen**

In `app/sources/agents_adapter.py`, den kompletten Block

```python
                if not _passes_self_test(harvested):
                    if agent.last_nonempty_at is None:
                        # Nie zuvor erfolgreich -> die optimistische
                        # Phase-2a-Klassifikation war falsch, sofort
                        # zurückstufen (Spec §7: Selbsttest vor Aktivierung).
                        log.info("agents_adapter.self_test_failed", agent_id=agent.id, count=len(harvested))
                        self._write_agent(
                            agent.id,
                            coverage_status="needs-manual-watch",
                            coverage_reason=(
                                f"Selbsttest fehlgeschlagen: Handler {method_name!r} lieferte "
                                "keine verwertbaren Objekte (Titel, Detail-Link und mind. ein "
                                "Sachattribut nötig)."
                            ),
                            last_checked=now,
                        )
                    else:
                        # War zuvor erfolgreich -> ein einzelner leerer Lauf
                        # ist noch kein Rezept-Bruch (Spec §7: Bruch erst nach
                        # ZWEI aufeinanderfolgenden leeren Läufen -- die dafür
                        # nötige Zähl-Logik ist Change-Gate-Arbeit, Phase 2c).
                        # Nur last_checked aktualisieren, Status bleibt
                        # auto-harvested.
                        log.info("agents_adapter.empty_run_after_prior_success", agent_id=agent.id)
                        self._write_agent(agent.id, last_checked=now)
                    continue
```

ersetzen durch:

```python
                if not _passes_self_test(harvested):
                    if agent.last_nonempty_at is None:
                        # Nie zuvor erfolgreich -> die optimistische
                        # Phase-2a-Klassifikation war falsch, sofort
                        # zurückstufen (Spec §7: Selbsttest vor Aktivierung).
                        # Kein Streak nötig -- Erstaktivierungs-Selbsttest.
                        log.info("agents_adapter.self_test_failed", agent_id=agent.id, count=len(harvested))
                        self._write_agent(
                            agent.id,
                            coverage_status="needs-manual-watch",
                            coverage_reason=(
                                f"Selbsttest fehlgeschlagen: Handler {method_name!r} lieferte "
                                "keine verwertbaren Objekte (Titel, Detail-Link und mind. ein "
                                "Sachattribut nötig)."
                            ),
                            last_checked=now,
                        )
                        continue

                    # War zuvor erfolgreich -> Zwei-Läufe-Zähler (Phase 2c,
                    # Spec §4): ein einzelner leerer/selbsttest-untauglicher
                    # Lauf ist noch kein Rezept-Bruch (Spec §7: Bruch erst
                    # nach ZWEI aufeinanderfolgenden Läufen).
                    empty_runs = (agent.consecutive_empty_runs or 0) + 1
                    if len(harvested) == 0:
                        # Fall (a): Handler lieferte 0 Objekte -- vermutlich
                        # transienter Netzwerkfehler oder Blockade.
                        log.info(
                            "agents_adapter.empty_run_case_a_zero_objects",
                            agent_id=agent.id,
                            consecutive_empty_runs=empty_runs,
                        )
                        case_reason = "Handler lieferte 0 Objekte"
                    else:
                        # Fall (b): Handler lieferte N>0 Objekte, aber keins
                        # bestand den Selbsttest -- vermutlich echter
                        # Rezept-Bruch (z.B. Website-Relaunch entfernte
                        # Preis/Fläche aus dem Markup). Höheres Log-Level als
                        # Fall (a), wie im Phase-2b-Plan als Grundlage für
                        # diesen Zähler vorgezeichnet.
                        log.warning(
                            "agents_adapter.empty_run_case_b_all_failed_self_test",
                            agent_id=agent.id,
                            count=len(harvested),
                            consecutive_empty_runs=empty_runs,
                        )
                        case_reason = f"Handler lieferte {len(harvested)} Objekte, keins bestand den Selbsttest"

                    if empty_runs >= 2:
                        self._write_agent(
                            agent.id,
                            coverage_status="needs-manual-watch",
                            coverage_reason=(
                                f"Zwei aufeinanderfolgende Läufe ohne Selbsttest-Erfolg. "
                                f"Letzter Lauf: {case_reason}."
                            ),
                            consecutive_empty_runs=empty_runs,
                            last_checked=now,
                        )
                    else:
                        self._write_agent(
                            agent.id, consecutive_empty_runs=empty_runs, last_checked=now
                        )
                    continue
```

Und im Erfolgspfad direkt darunter (aktuell Zeile 223-228)

```python
                self._write_agent(
                    agent.id,
                    last_checked=now,
                    last_nonempty_at=now,
                    last_listing_count=len(harvested),
                )
```

den Zähler-Reset ergänzen:

```python
                self._write_agent(
                    agent.id,
                    last_checked=now,
                    last_nonempty_at=now,
                    last_listing_count=len(harvested),
                    consecutive_empty_runs=0,
                )
```

Modul-Docstring (Zeilen 13-28) entsprechend aktualisieren — der Absatz über den "Zweistufigen Selbsttest" soll den neuen Zähler beschreiben statt "Der Zwei-Läufe-Zähler für echte Bruch-Erkennung ist Change-Gate-Arbeit (Phase 2c)" zu versprechen:

```python
Zweistufiger Selbsttest (Vollabdeckung-Spec §7): das Ergebnis eines Handlers
wird gepuffert (Objektzahl pro Makler ist klein) und geprüft, bevor es
weitergereicht wird.
- Lieferte ein Makler NOCH NIE etwas (last_nonempty_at ist None) und der
  aktuelle Lauf liefert nichts Verwertbares, wird die optimistische, rein
  klassifikationsbasierte `auto-harvested`-Einstufung aus Phase 2a
  (app.agent_onboarding) sofort auf `needs-manual-watch` zurückgestuft
  ("Selbsttest vor Aktivierung").
- War der Makler zuvor erfolgreich, zählt `consecutive_empty_runs` (Phase 2c)
  aufeinanderfolgende Läufe ohne Selbsttest-Erfolg. Erst beim ZWEITEN Lauf in
  Folge (Spec §7) erfolgt der Downgrade auf `needs-manual-watch`; der erste
  Fehlschlag aktualisiert nur `last_checked` + den Zähler. Zwei Fälle werden
  im Log unterschieden: Handler lieferte 0 Objekte (Fall a, `log.info`,
  vermutlich transient) vs. Handler lieferte Objekte, aber keins bestand den
  Selbsttest (Fall b, `log.warning`, vermutlich echter Rezept-Bruch, z.B.
  Website-Relaunch).
```

- [ ] **Step 5: Tests laufen lassen, Erfolg verifizieren**

Run: `pytest tests/test_agents_adapter.py -v`
Expected: PASS — alle neuen und bestehenden Tests grün. `_make_agent()` akzeptiert `consecutive_empty_runs` bereits über `**overrides`, keine Änderung an diesem Helper nötig.

- [ ] **Step 6: Vollständige Suite + Lint**

```bash
pytest -v
ruff check app/db.py app/sources/agents_adapter.py tests/test_agents_adapter.py
```

Expected: alle Tests grün, Lint sauber.

- [ ] **Step 7: Commit**

```bash
git add app/db.py app/sources/agents_adapter.py tests/test_agents_adapter.py
git commit -m "feat(agents): Zwei-Läufe-Zähler für echte Rezept-Bruch-Erkennung (Spec §7)"
```

---

### Task 6: `browser_session()` — Browser-Wiederverwendung für Playwright

**Files:**
- Modify: `app/sources/browser.py`
- Create: `tests/test_browser.py`

**Interfaces:**
- Produces: `browser_session() -> AsyncContextManager[Callable[[str, str | None], Awaitable[str]]]` — Context-Manager, liefert eine `fetch(url, wait_selector=None) -> str`-Funktion, die alle Aufrufe innerhalb des `async with`-Blocks denselben Browser/Context teilen lässt.
- Consumes: die bestehende `_browser()`-Hilfsfunktion in derselben Datei (unverändert).

**Kontext:** `fetch_html()` startet pro Aufruf einen kompletten Chromium-Prozess — für `kleinanzeigen.py` (2 Aufrufe/Lauf) ist das akzeptabel, für einen Makler-Agenten mit bis zu 40 Detailseiten/Lauf zu teuer. `browser_session()` öffnet **einen** Browser/Context für die gesamte Dauer des Context-Managers und öffnet/schließt nur je eine `page` pro URL darin — ein `page.goto()`-Fehler für eine einzelne URL wird abgefangen und bricht die Session nicht ab (wie `_fetch_detail_listing()` das heute für `httpx` tut).

Da es im Projekt noch kein Playwright-Test-Vorbild gibt: Tests mocken `async_playwright` komplett (kein echter Chromium-Start), analog zum `AsyncMock`-URL-Routing-Muster für `httpx` in `tests/test_agent_probe.py`.

- [ ] **Step 1: Failing Tests schreiben**

Erstelle `tests/test_browser.py`:

```python
"""Tests für app.sources.browser — Playwright-Wrapper für JS-gerenderte/
WAF-blockierte Makler-Sites (Vollabdeckung-Spec Phase 2c §5). Kein echter
Chromium-Start: async_playwright wird komplett gemockt."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.sources.browser import browser_session


def _mock_playwright_stack():
    """Baut die verschachtelte Mock-Kette nach, die async_playwright()
    normalerweise liefert: p.chromium.launch() -> browser,
    browser.new_context() -> context, context.new_page() -> page."""
    page = AsyncMock()
    page.goto = AsyncMock()
    page.close = AsyncMock()

    context = AsyncMock()
    context.new_page = AsyncMock(return_value=page)
    context.close = AsyncMock()

    browser = AsyncMock()
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock()

    chromium = AsyncMock()
    chromium.launch = AsyncMock(return_value=browser)

    playwright_instance = MagicMock()
    playwright_instance.chromium = chromium

    playwright_cm = AsyncMock()
    playwright_cm.__aenter__ = AsyncMock(return_value=playwright_instance)
    playwright_cm.__aexit__ = AsyncMock(return_value=False)

    return playwright_cm, browser, context, page


@pytest.mark.asyncio
async def test_browser_session_reuses_one_browser_for_multiple_fetches():
    playwright_cm, browser, context, page = _mock_playwright_stack()
    page.content = AsyncMock(side_effect=["<html>eins</html>", "<html>zwei</html>"])

    with patch("app.sources.browser.async_playwright", return_value=playwright_cm):
        async with browser_session() as fetch:
            html1 = await fetch("https://x.de/a")
            html2 = await fetch("https://x.de/b")

    assert html1 == "<html>eins</html>"
    assert html2 == "<html>zwei</html>"
    assert browser.new_context.await_count == 1  # ein Context für beide Fetches
    assert context.new_page.await_count == 2  # aber eine Page pro URL


@pytest.mark.asyncio
async def test_browser_session_closes_browser_after_context_exits():
    playwright_cm, browser, context, page = _mock_playwright_stack()
    page.content = AsyncMock(return_value="<html></html>")

    with patch("app.sources.browser.async_playwright", return_value=playwright_cm):
        async with browser_session() as fetch:
            await fetch("https://x.de/a")

    context.close.assert_awaited_once()
    browser.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_browser_session_page_failure_does_not_abort_session():
    playwright_cm, browser, context, page = _mock_playwright_stack()
    page.goto = AsyncMock(side_effect=[Exception("timeout"), None])
    page.content = AsyncMock(return_value="<html>zwei</html>")

    with patch("app.sources.browser.async_playwright", return_value=playwright_cm):
        async with browser_session() as fetch:
            with pytest.raises(Exception, match="timeout"):
                await fetch("https://x.de/a")
            html2 = await fetch("https://x.de/b")

    assert html2 == "<html>zwei</html>"
    context.close.assert_awaited_once()
    browser.close.assert_awaited_once()
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag verifizieren**

Run: `pytest tests/test_browser.py -v`
Expected: FAIL mit `ImportError: cannot import name 'browser_session'`

- [ ] **Step 3: `browser_session()` implementieren**

In `app/sources/browser.py`, nach der bestehenden `fetch_html()`-Funktion (Zeile 33-47) ergänzen:

```python
@asynccontextmanager
async def browser_session() -> AsyncIterator[Callable[[str, str | None, int], Awaitable[str]]]:
    """Öffnet EINEN Browser/Context für die gesamte Dauer des
    Context-Managers und liefert eine fetch(url, wait_selector=None)-
    Funktion, die alle Aufrufe darin teilt -- vermeidet einen Browser-
    Neustart pro Detailseite (fetch_html() macht das pro Aufruf, tragbar
    für kleinanzeigen.py mit 2 Suchseiten/Lauf, nicht für bis zu 40
    Detailseiten/Agent, siehe Vollabdeckung-Spec Phase 2c §5.1). Ein
    page.goto()-Fehler für eine einzelne URL wird NICHT abgefangen -- die
    aufrufende Handler-Schleife (analog zu httpx-Fehlern in
    _fetch_detail_listing()) fängt ihn pro URL ab, die Session selbst bleibt
    für weitere Aufrufe nutzbar."""
    async with _browser() as ctx:

        async def fetch(url: str, wait_selector: str | None = None, timeout_ms: int = 30000) -> str:
            page = await ctx.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                if wait_selector:
                    try:
                        await page.wait_for_selector(wait_selector, timeout=10000)
                    except Exception:
                        log.debug("browser.wait_selector_timeout", url=url, selector=wait_selector)
                return await page.content()
            finally:
                await page.close()

        yield fetch
```

Am Dateianfang die nötigen Imports ergänzen (`AsyncIterator`, `Callable` fehlen bisher):

```python
from collections.abc import AsyncIterator, Awaitable, Callable
```

- [ ] **Step 4: Test laufen lassen, Erfolg verifizieren**

Run: `pytest tests/test_browser.py -v`
Expected: PASS

- [ ] **Step 5: Lint + Commit**

```bash
ruff check app/sources/browser.py tests/test_browser.py
git add app/sources/browser.py tests/test_browser.py
git commit -m "feat(browser): browser_session() für Browser-Wiederverwendung über mehrere Fetches"
```

---

### Task 7: Go/No-Go-Probe gegen die vier Ziel-Sites

**Files:** keine Code-Änderungen — reiner Recherche-/Verifikationsschritt.

**Kontext:** Aigner Immobilien steht als `bot-blocked`, die anderen drei (Dahler & Company, Locate Immobilien, Imothek) als `needs-manual-watch` (vermutlich JS-Shell). Bevor Task 8 die Handler-Integration baut, muss geklärt sein, ob Playwright bei diesen konkreten Sites überhaupt echten Content liefert — eine WAF, die auch Headless-Chromium fingerprinted, würde die gesamte Integration nutzlos machen.

- [ ] **Step 1: Echte Domains der vier Ziel-Agents ermitteln**

```bash
ssh root@89.167.67.26 "docker compose -f /opt/immo-radar/docker-compose.yml exec -T worker python3 -c \"
import app.db as db
from sqlalchemy import select
with db.SessionLocal() as s:
    for a in s.scalars(select(db.Agent).where(db.Agent.name.in_(['Aigner Immobilien', 'Dahler & Company', 'Locate Immobilien', 'Imothek']))):
        print(a.id, a.name, a.verified_domain, a.listing_url, a.coverage_status, a.coverage_reason)
\""
```

(Falls die Namen in der DB abweichen: `SELECT id, name, coverage_status FROM agents WHERE coverage_status IN ('bot-blocked', 'needs-manual-watch');` zur Orientierung vorschalten.)

- [ ] **Step 2: Jede Domain per `browser_session()` einmal anfragen**

Lokales Einwegskript (nicht committen, im Scratchpad ausführen — kein Playwright auf dem VPS-Worker nötig, `fetch_html`/`browser_session` läuft bereits im `worker`-Container, der Chromium enthält, siehe CLAUDE.md "Docker-Image enthält Chromium"; die Probe läuft deshalb auf dem VPS gegen den Produktions-Container, nicht lokal, damit Netzwerk-/User-Agent-Bedingungen identisch zum echten Harvest-Lauf sind):

```bash
ssh root@89.167.67.26 "docker compose -f /opt/immo-radar/docker-compose.yml exec -T worker python3 -c \"
import asyncio
from app.sources.browser import browser_session
from app.agent_cascade_detect import find_detail_links

DOMAINS = {
    'aigner': 'https://<echte-listing-url-aus-step-1>',
    'dahler': 'https://<echte-listing-url-aus-step-1>',
    'locate': 'https://<echte-listing-url-aus-step-1>',
    'imothek': 'https://<echte-listing-url-aus-step-1>',
}

async def probe():
    async with browser_session() as fetch:
        for name, url in DOMAINS.items():
            try:
                html = await fetch(url)
                count, urls = find_detail_links(html, url, limit=None)
                print(f'{name}: {count} Detail-Links gefunden, Beispiel: {urls[:2]}')
            except Exception as e:
                print(f'{name}: FEHLER {e}')

asyncio.run(probe())
\""
```

Die `<echte-listing-url-aus-step-1>`-Platzhalter mit den tatsächlichen `listing_url`/`verified_domain`-Werten aus Step 1 befüllen, bevor das Skript läuft.

- [ ] **Step 3: Ergebnis pro Site dokumentieren**

Für jede der vier Domains festhalten: `count` > 0 und die Beispiel-URLs sehen wie echte Objekt-Detailseiten aus → **Go**. `count == 0`, eine Exception, oder die Beispiel-URLs sehen nach Cookie-/Challenge-Seite aus → **No-Go**, bleibt `needs-manual-watch`.

Das Ergebnis kommt wortwörtlich in die Commit-Message von Task 8 (kein separates Doku-Artefakt nötig, Spec §5.3: "Kommentar im Plan-Ledger oder Commit-Message reicht"). Kein `git commit` in diesem Task selbst — reiner Recherche-Schritt ohne Code-Änderung.

---

### Task 8: `render: "browser"`-Flag verdrahten + Probe-Ergebnis anwenden

**Files:**
- Modify: `app/sources/agent_handlers.py` (`crawl_and_extract` verzweigt auf `browser_session()`)
- Test: `tests/test_agent_handlers.py`
- Datenänderung: `Agent.extraction["render"]` + `coverage_status` für die in Task 7 als "Go" bewerteten Domains (Produktions-DB, per Skript — kein Migrations-Task, analog zu HER-814s direktem `set_setting()`-Vorgehen).

**Interfaces:**
- Consumes: `browser_session()` aus Task 6, Task-7-Probe-Ergebnis.
- Produces: keine neuen Symbole — Verhaltensänderung in `crawl_and_extract`.

**Kontext:** Nur `crawl_and_extract` wird produktiv gebraucht (Spec §5.2: "primär betroffen") — alle vier Ziel-Sites laufen aktuell über `vendor:<x>`- oder `detail_links`-Method-Keys, die beide auf `crawl_and_extract` zeigen (`app/sources/agents_adapter.py::_default_extraction_methods`). Diese Aufgabe verzweigt den Handler auf `browser_session()` statt `httpx`, wenn `agent.extraction.get("render") == "browser"` gesetzt ist — sowohl für die Listing-Seite als auch für jede Detailseite in einer gemeinsamen Session.

- [ ] **Step 1: Failing Test schreiben**

Füge in `tests/test_agent_handlers.py` hinzu:

```python
@pytest.mark.asyncio
async def test_crawl_and_extract_uses_browser_session_when_render_flag_set(monkeypatch):
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
    pages = {
        "https://x.de/immobilien/": listing_html,
        "https://x.de/immobilien/villa-am-see-tutzing": detail_html,
        "https://x.de/immobilien/wohnung-starnberg-zentral": detail_html,
        "https://x.de/immobilien/haus-poecking-mit-garten": detail_html,
    }

    async def fake_fetch(url, wait_selector=None):
        return pages[url]

    class _FakeBrowserSession:
        async def __aenter__(self):
            return fake_fetch

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr("app.sources.agent_handlers.browser_session", lambda: _FakeBrowserSession())
    client = AsyncMock()  # darf für KEINEN Request benutzt werden
    agent = _agent(listing_url="https://x.de/immobilien/", extraction={"method": "detail_links", "render": "browser"})

    results = [r async for r in crawl_and_extract(agent, client)]

    assert len(results) == 3
    client.get.assert_not_called()
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag verifizieren**

Run: `pytest tests/test_agent_handlers.py -k render_flag_set -v`
Expected: FAIL — `client.get` wird noch aufgerufen, `browser_session` wird noch gar nicht importiert/verwendet in `crawl_and_extract`.

- [ ] **Step 3: `crawl_and_extract` auf das `render`-Flag verzweigen lassen**

In `app/sources/agent_handlers.py` den Import ergänzen:

```python
from app.sources.browser import browser_session
```

`crawl_and_extract()` komplett ersetzen durch:

```python
async def crawl_and_extract(
    agent: Agent, client: httpx.AsyncClient, known_urls: dict[str, datetime] | None = None
) -> AsyncIterator[RawListing]:
    """Handler für alle `vendor:<x>`-Method-Keys UND `detail_links` (Scope-
    Entscheidung Phase 2b): Phase 0 lieferte nur Vendor-Fingerprints, keine
    Vendor-spezifischen Selektoren -- `vendor:<x>` bleibt deshalb nur ein
    Herkunfts-Tag im extraction-Dict, kein eigener Code-Pfad. Findet
    Objekt-URLs strukturell (find_detail_links) auf agent.listing_url, holt
    jede Detailseite, extrahiert Felder generisch.

    render:"browser" (Phase 2c, Spec §5.2): für JS-Shell-/WAF-blockierte
    Sites (nach Go/No-Go-Probe, siehe Plan Task 7) wird sowohl die
    Listing-Seite als auch jede Detailseite über eine gemeinsame
    browser_session() statt httpx geholt -- ein Mischmodus wäre sinnlos,
    WAF-Blocks greifen typischerweise auf beiden Ebenen."""
    if not agent.listing_url:
        log.warning("agent_handlers.crawl_no_listing_url", agent_id=agent.id)
        return

    use_browser = (agent.extraction or {}).get("render") == "browser"

    if use_browser:
        async with browser_session() as fetch:
            try:
                listing_html = await fetch(agent.listing_url)
            except Exception as e:
                log.warning("agent_handlers.listing_fetch_failed", agent_id=agent.id, error=str(e))
                return

            _, discovered_urls = find_detail_links(listing_html, agent.listing_url, limit=None)
            urls = _urls_to_fetch(discovered_urls, known_urls or {}, datetime.utcnow())[
                :MAX_DETAIL_PAGES_PER_AGENT
            ]

            for url in urls:
                try:
                    html = await fetch(url)
                except Exception as e:
                    log.warning("agent_handlers.detail_fetch_failed", agent_id=agent.id, url=url, error=str(e))
                    continue
                stripped = _strip_contact_blocks(html)
                text = BeautifulSoup(stripped, "html.parser").get_text(" ", strip=True)
                fields = extract_fields(stripped, text)
                yield RawListing(
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
                await asyncio.sleep(DETAIL_FETCH_DELAY_SECONDS)
        return

    try:
        r = await client.get(agent.listing_url)
        r.raise_for_status()
    except Exception as e:
        log.warning("agent_handlers.listing_fetch_failed", agent_id=agent.id, error=str(e))
        return

    _, discovered_urls = find_detail_links(r.text, agent.listing_url, limit=None)
    urls = _urls_to_fetch(discovered_urls, known_urls or {}, datetime.utcnow())[:MAX_DETAIL_PAGES_PER_AGENT]

    for url in urls:
        listing = await _fetch_detail_listing(agent, client, url)
        if listing is not None:
            yield listing
        await asyncio.sleep(DETAIL_FETCH_DELAY_SECONDS)
```

(Die Browser-Variante dupliziert die Feld-Extraktion aus `_fetch_detail_listing()` bewusst inline, statt die Funktion umzubauen: `_fetch_detail_listing()` ist fest an `httpx.AsyncClient` gebunden — ein gemeinsamer Extraktions-Kern für beide Fetch-Wege wäre ein größerer Umbau, der über den Scope dieser Phase hinausgeht, siehe Spec §8 "explizit außerhalb dieser Phase: Refactor der vier bestehenden Portal-Adapter".)

- [ ] **Step 4: Test laufen lassen, Erfolg verifizieren**

Run: `pytest tests/test_agent_handlers.py -v`
Expected: PASS — neuer Test grün, alle bestehenden `crawl_and_extract`-Tests weiterhin grün (kein `render`-Key in ihrem `extraction`-Dict → `use_browser` bleibt `False` → unveränderter httpx-Pfad).

- [ ] **Step 5: Vollständige Suite + Lint**

```bash
pytest -v
ruff check app/sources/agent_handlers.py tests/test_agent_handlers.py
```

- [ ] **Step 6: Commit**

```bash
git add app/sources/agent_handlers.py tests/test_agent_handlers.py
git commit -m "feat(agents): render:browser-Flag in crawl_and_extract für JS-Shell-/WAF-Sites"
```

- [ ] **Step 7: Task-7-Probe-Ergebnis auf Produktion anwenden**

Nur für Domains mit **Go**-Ergebnis aus Task 7, jeweils einzeln per Skript auf dem VPS (analog zu HER-814s direktem `set_setting()`-Vorgehen — kein neuer CLI-Befehl nötig für eine einmalige Aktion):

```bash
ssh root@89.167.67.26 "docker compose -f /opt/immo-radar/docker-compose.yml exec -T worker python3 -c \"
import app.db as db
with db.SessionLocal() as s:
    agent = s.get(db.Agent, <agent_id_aus_task_7>)
    agent.extraction = {**agent.extraction, 'render': 'browser'}
    agent.coverage_status = 'auto-harvested'
    agent.coverage_reason = 'Playwright-Probe (Phase 2c, <Datum>) bestätigt: Listing-Seite liefert erreichbaren Objekt-Content über Headless-Chromium.'
    s.commit()
    print('OK', agent.id, agent.name, agent.coverage_status)
\""
```

Nach jeder Umstellung: `docker compose logs -f worker` für den nächsten automatischen Poll-Zyklus beobachten (Intervall siehe `docs/STATUS.md`) und via Dashboard verifizieren, dass echte Listings für die umgestellte Domain ankommen — analog zur produktiven Verifikation der Phase-2b-Onboardings.

Domains mit **No-Go**-Ergebnis bleiben unverändert auf `needs-manual-watch`; `coverage_reason` wird trotzdem aktualisiert, um das Probe-Ergebnis festzuhalten statt stillschweigend nichts zu tun:

```bash
ssh root@89.167.67.26 "docker compose -f /opt/immo-radar/docker-compose.yml exec -T worker python3 -c \"
import app.db as db
with db.SessionLocal() as s:
    agent = s.get(db.Agent, <agent_id_aus_task_7>)
    agent.coverage_reason = 'Playwright-Probe (Phase 2c, <Datum>) fand keinen zugänglichen Objekt-Content (<Fehler/Befund aus Task 7>) -- bleibt manuell beobachtet.'
    s.commit()
    print('OK', agent.id, agent.name, agent.coverage_status)
\""
```

Kein separater `git commit` für diese reinen Datenänderungen — sie sind kein Code, landen aber in der Task-8-Commit-Message (Step 6) referenziert, sobald die Ergebnisse feststehen. Abschließend `docs/STATUS.md` aktualisieren: Phase 2c als abgeschlossen dokumentieren, Ergebnis der Playwright-Probe (wie viele der vier Sites live gingen) nennen, "Nächster Schritt" auf Phase 3 (Discovery) oder Linear-Housekeeping aktualisieren.

```bash
git add docs/STATUS.md
git commit -m "docs(status): Phase 2c (Change-Gate, Zwei-Läufe-Zähler, Playwright) abgeschlossen"
```
