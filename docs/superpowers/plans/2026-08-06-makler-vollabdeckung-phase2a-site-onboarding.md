# Makler-Vollabdeckung Phase 2a: Site-Onboarding — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Given an `Agent`-Zeile mit gesetztem `verified_domain`, die passende Kaskadenstufe (Vollabdeckung-Spec §4.1) ermitteln und das Ergebnis persistieren — `extraction`-Dict, `listing_url`, `coverage_status`/`coverage_reason` — damit Phase 2b weiß, welchen Handler sie später dispatchen muss.

**Architecture:** Drei neue Module. `app/agent_cascade_detect.py` promoted die reinen, I/O-freien Erkennungsfunktionen aus `scripts/probe_agent_sites.py` (Vendor-Fingerprints, vokabularfreie Detail-Link-Erkennung, JSON-LD-Erkennung) unverändert — direkt gegen HTML-Strings testbar. `app/agent_probe.py` adaptiert den Netzwerk-Teil (`probe()`/`classify()`) zu einer Ein-Domain-Funktion, die den Client des Aufrufers nutzt statt einen eigenen zu öffnen, und die — anders als das reine Messwerkzeug — sofort abbricht, sobald `robots.txt` die Startseite verbietet. `app/agent_onboarding.py` bildet die klassifizierte Stufe auf das `extraction`-Schema aus Spec §5.1 ab und schreibt sie zurück, per optionalem Session-Parameter nach demselben Muster wie `geocode()` in `app/geocoding.py`. `scripts/onboard_agents.py` ist der manuelle CLI-Trigger (Dashboard-Trigger folgt erst in Phase 3/4).

**Tech Stack:** Python 3.12, httpx (async), BeautifulSoup4, SQLAlchemy, pytest-asyncio — alles bereits im Projekt vorhanden, keine neuen Abhängigkeiten.

## Global Constraints

- **DB-Zugriff:** neue Module importieren `import app.db as db_module` und rufen `db_module.SessionLocal()` zur Aufrufzeit — nie `from app.db import SessionLocal` auf Modulebene (Tests patchen `db_module.SessionLocal`, ein modulweiter Import-Binding sieht den Patch nicht).
- **User-Agent:** ausschließlich `from app.robots import USER_AGENT` wiederverwenden — kein neuer/zweiter UA-String. Das Phase-0-Messwerkzeug hatte einen eigenen `-probe`-Suffix-String; das wird hier bewusst nicht übernommen, sonst driften robots.txt-Prüfung (`app.robots.is_allowed`) und Probe auseinander.
- **Mutable JSON-Defaults:** falls neue SQLAlchemy-Spalten hinzukommen, `default=dict`/`default=list` verwenden, nie literale `{}`/`[]`.
- **`extraction`-Schema ist die tragende Schnittstelle für Phase 2b — exakte Feldnamen, keine Abweichung:**
  ```python
  {
      "method": str,        # Dispatch-Key für EXTRACTION_METHODS in Phase 2b,
                             # z.B. "vendor:onoffice", "detail_links",
                             # "feed_adapter", "sitemap_objekte", "structured_data"
      "vendor": str,        # nur gesetzt wenn method mit "vendor:" beginnt —
                             # redundant zu method, aber Spec §5.1 verlangt das
                             # Feld separat fürs Dashboard
      "feed_url": str | None,
      "sitemap_url": str | None,
      "needs_browser": bool,  # nur bei method-losen/blockierten Agents gesetzt
  }
  ```
- **`coverage_status` ausschließlich aus `app.db.COVERAGE_STATUSES`** — kein neuer Statuswert.
- **robots.txt hat Vorrang vor jeder Kaskaden-Klassifikation** (Spec §8: "Disallow → kein Abruf"). Das unterscheidet `agent_probe.py` bewusst vom Phase-0-Messwerkzeug, das trotz Disallow weiterlas (einmaliger Testlauf gegen vom Nutzer geprüfte Domains) — das echte, automatisiert laufende Onboarding darf das nicht.
- **Kein Objekt-Abruf in diesem Plan.** Phase 2a klassifiziert nur, welche Stufe greifen würde, und ruft dafür maximal die Startseite, `robots.txt`, `sitemap.xml`, bis zu 2 Feeds und die Angebotsseite ab (identisch zum bereits erprobten Umfang aus `probe_agent_sites.py`). Das tatsächliche Abholen einzelner Objekt-Detailseiten ist Phase 2b.
- **Höflichkeitspause:** `await asyncio.sleep(1.0)` am Ende eines erfolgreichen Probes bleibt erhalten (eine Pause pro Host und Onboarding-Lauf).
- **Ruff-Baseline:** `ruff check .` muss auf allen neuen/geänderten Dateien sauber durchlaufen (line-length 110, Regeln E/F/I/B/UP). Blockt der Pre-Commit-Hook auf vorbestehenden Fehlern einer *angefassten* Datei: mechanisch fixen + im Commit/Report explizit offenlegen — nie `--no-verify`.
- **Lokale Env:** `DB_PATH=./data/immo.db pytest` / `DB_PATH=./data/immo.db ruff check .` (`.env` zeigt auf einen Docker-internen Pfad).
- **Test-Isolation:** neue Tests folgen dem etablierten Fixture-Muster aus `tests/test_geocoding.py`/`tests/test_agents_adapter.py` — eigene SQLite-Test-DB über `create_engine(f"sqlite:///{tmp_path}/test.db")` + `monkeypatch.setattr(db_module, "engine"/"SessionLocal", ...)`, `httpx`-Aufrufe über `unittest.mock.AsyncMock`/`MagicMock` gemockt (kein `respx`, das Projekt nutzt es nirgends).

---

### Task 1: Reine Erkennungsfunktionen promoten

**Files:**
- Create: `app/agent_cascade_detect.py`
- Test: `tests/test_agent_cascade_detect.py`

**Interfaces:**
- Produces: `link_shape(url: str) -> str`, `is_object_like(url: str) -> bool`, `find_detail_links(html: str, base: str) -> tuple[int, list[str]]`, `detect_vendors(blob: str) -> list[str]`, `detect_structured(html: str) -> dict`, `content_signals(html: str) -> dict`, sowie die Konstanten `VENDORS`, `IMMO_LD_TYPES`, `PRICE_RE`, `AREA_RE`, `DETAIL_RE`, `LISTING_HINTS`. Werden von Task 2 (`app/agent_probe.py`) importiert.

- [ ] **Step 1: Datei mit den promoteten Funktionen anlegen**

Wortgleich aus `scripts/probe_agent_sites.py` übernommen (Zeilen 79–276, 364–400), nur der Modul-Docstring ist neu:

```python
"""Vokabularfreie, I/O-freie Erkennungsbausteine der Extraktions-Kaskade
(Vollabdeckung-Spec §4.1). Promoted aus scripts/probe_agent_sites.py
(Phase 0) — dort empirisch an 39 Makler-Sites gehärtet, hier unverändert
weiterverwendet. Reine Funktionen: kein Netzwerk, keine DB, direkt gegen
HTML-Strings testbar. Netzwerk-Orchestrierung liegt in app/agent_probe.py."""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

# Fingerprints: Kennung -> Regex-Muster im HTML/Header.
VENDORS = {
    "wp-immomakler": r"wp-content/plugins/immomakler|immomakler",
    "onoffice": r"onoffice-for-wp-websites|onoffice\.de|onofficeSDK|oo-form",
    "propstack": r"propstack\.de|propstack\.io|propstack-",
    "flowfact": r"flowfact|ff-immo|flowfact-connector",
    "immonex": r"immonex|inx_property|inx-",
    "openimmo2wp": r"openimmo2wp|oi2wp",
    "estatik": r"wp-content/plugins/estatik",
    "wp-property": r"wp-content/plugins/wp-property",
    "justimmo": r"justimmo",
    "fio": r"fio-systems|fio\.de|fiowebsite",
    "immoscout-widget": r"immobilienscout24\.de/expose|is24-widget",
    "reseda": r"reseda",
    "immosolve": r"immosolve",
    "casavi": r"casavi",
    # TYPO3-Extension für OpenImmo-Import (see-immo.de)
    "typo3-openimmo": r"tx_openimmo|typo3conf/ext/openimmo",
    # Legacy-Makler-CMS mit Cursor-URLs; identisch bei starnbergersee-immobilien
    # und remax-starnberg — Fingerprint über das URL-Schema statt über Assets.
    "cursor-cms": r"index\.php4?\?cmd=searchDetails|objq%5Bcursor%5D|objq\[cursor\]",
    # Fremdgehostetes Objekt-Widget (Livewire) — Objekte liegen auf einer
    # anderen Domain als der Makler-Site selbst (z.B. imothek.de). Nur als
    # src= (Script/Iframe-Einbettung) werten, nicht als href= — sonst matcht
    # jeder bloße Outbound-Partnerlink zu immobilie1.de (Fund: dahlercompany.com
    # verlinkt es mit rel="nofollow", ohne jede technische Integration).
    "immobilie1-widget": r'src=["\']https?://(?:www\.)?immobilie1\.de',
}

LISTING_HINTS = re.compile(
    r"(immobilien|objekte|angebote|kaufobjekte|immobilienangebote|referenzen|"
    r"aktuelle-objekte|verkaufsobjekte|kaufen|exposes?)",
    re.I,
)

PRICE_RE = re.compile(r"\d{1,3}(?:[.\s]\d{3})+\s*(?:€|EUR)")
AREA_RE = re.compile(r"\d{2,4}(?:[,.]\d+)?\s*m²")

# Objekt-Detailseiten folgen fast immer einem dieser Pfadmuster.
# Wichtig: deutsche Endungen zulassen — /objekte/, /immobilien-tutzing/ … —
# und ein weiteres Pfadsegment verlangen, sonst matcht die Übersichtsseite
# selbst oder eine Serviceseite wie /immobilien-verkaufen/.
DETAIL_RE = re.compile(
    r"/(?:immobilie|objekt|expose|exposé|estate|property|immo|angebot"
    r"|listing|realestate|wohnung|haus)[a-zäöüß-]*"
    r"/[^/?#]{4,}"
    r"|[?&](?:objekt|immo|expose|property|estate)[-_]?id=",
    re.I,
)


def link_shape(url: str) -> str:
    """Normalisiert eine URL zu ihrem Strukturmuster.

    /objekte/haus-am-see        → /objekte/*
    /index.php4?cmd=x&cursor=7  → /index.php4?cmd&cursor
    So fallen Links, die sich nur im Objektbezeichner unterscheiden, in dieselbe
    Gruppe — unabhängig davon, ob der Pfad sprechend ist.
    """
    p = urlparse(url)
    segs = [s for s in p.path.split("/") if s]
    shape = "/".join(segs[:-1]) if len(segs) > 1 else (segs[0] if segs else "")
    keys = sorted(k.split("=")[0] for k in p.query.split("&") if k) if p.query else []
    return f"/{shape}/*" + ("?" + "&".join(keys) if keys else "")


# Links, die zwar pro Objekt existieren, aber nicht zum Objekt führen.
# cHash bewusst NICHT hier: das ist TYPO3s generischer Cache-Busting-Parameter
# auf praktisch jedem Link (auch echten Objektseiten) — kein Formular-Signal.
FORM_LINK_RE = re.compile(
    r"(anfrage|request|kontakt|contact|merkzettel|merkliste|watchlist|vormerk"
    r"|expose-anfordern|print|drucken|share|teilen)",
    re.I,
)

# Objekt-Slugs sind lange, mehrgliedrige Wortketten ("moderne-gartenwohnung-in-
# ruhiger-wohnlage-von-weilheim"). Navigationsslugs sind kurz ("leistungen").
SLUG_MIN_LEN = 25
SLUG_MIN_PARTS = 4

# Letztes Pfadsegment: Kategorie-/Navigationsseiten, die auf derselben Ebene
# wie Objekte liegen (/immobilien/neubau/ neben /immobilien/<objekt-slug>/)
# und sonst die Gruppierung verunreinigen.
NAV_LAST_SEGMENT_RE = re.compile(
    r"^(neubau|kaufen|mieten|verkaufen|vermieten|kontakt|news|blog|team|karriere"
    r"|ueber-uns|about|impressum|datenschutz|agb|finanzierung|bewertung"
    r"|wertermittlung|kapitalanlagen?|grundstuecke|gewerbeimmobilien"
    r"|auslandsimmobilien|international|referenzen|leistungen|partner)$",
    re.I,
)


def is_object_like(url: str) -> bool:
    """Ist das eher ein Objekt als eine Kategorieseite?

    Zwei Fälle: Der Objektbezeichner steckt entweder im letzten Pfadsegment
    (sprechender Slug) oder in einem Query-Parameter (Legacy-CMS wie
    `index.php4?...&objq[cursor]=7`). Ein Query-Parameter mit numerischem Wert
    neben `cmd=searchDetails`/`id=`/`cursor=` zählt als Objektsignal, auch wenn
    der Pfad selbst kurz ist.
    """
    p = urlparse(url)
    if re.search(r"(cursor|objekt.?id|obj.?id|haus|wohnung|expose.?id)\]?=\d+", p.query, re.I):
        return True
    segs = [s for s in p.path.split("/") if s]
    if not segs:
        return False
    last = segs[-1]
    if NAV_LAST_SEGMENT_RE.match(last):
        return False
    return len(last) >= 12 or last.count("-") >= 2


def find_detail_links(html: str, base: str) -> tuple[int, list[str]]:
    """Objektlinks strukturell finden — ohne Vokabular-Annahmen.

    Wortlisten scheitern an Legacy-CMS (`index.php4?cmd=searchDetails&cursor=7`)
    und an fremdsprachigen Slugs. Zwei strukturelle Signale tragen weiter:

    1. **Gleichförmige Gruppe** — viele Links unter demselben Präfix bzw. mit
       derselben Query-Signatur, die sich nur im Objektbezeichner unterscheiden.
    2. **Lange Root-Slugs** — manche CMS legen Objekte flach im Root ab, wodurch
       jedes Objekt ein eigenes Präfix bekommt und (1) leerläuft. Solche Slugs
       sind aber deutlich länger und mehrgliedriger als Navigationslinks.
    """
    soup = BeautifulSoup(html, "html.parser")
    # Nur <footer> entfernen. <nav>/<header> pauschal zu entfernen ist gefährlich:
    # manche Themes verschachteln die Objektliste darin — bei einer Testsite
    # blieben davon 3 von 119 Links übrig.
    for tag in soup.find_all("footer"):
        tag.decompose()

    host = urlparse(base).netloc
    base_norm = base.split("#")[0].rstrip("/")
    candidates: set[str] = set()
    for a in soup.find_all("a", href=True):
        full = urljoin(base, a["href"]).split("#")[0]
        p = urlparse(full)
        if p.netloc != host or full.rstrip("/") == base_norm:
            continue
        if FORM_LINK_RE.search(p.query) or FORM_LINK_RE.search(p.path):
            continue
        candidates.add(full)

    # (1) Gruppen mit gemeinsamem Muster. Innerhalb einer Gruppe können
    # Kategorie-/Navigationsseiten auf derselben Ebene wie Objekte liegen
    # (/immobilien/neubau/ neben /immobilien/<objekt-slug>/) — deshalb wird
    # jedes Gruppenmitglied zusätzlich einzeln auf Objekt-Charakter geprüft.
    groups: dict[str, set[str]] = {}
    for url in candidates:
        groups.setdefault(link_shape(url), set()).add(url)

    best: tuple[int, list[str]] = (0, [])
    for shape, urls in groups.items():
        if len(urls) < 3 or re.search(r"(impressum|datenschutz|team|news|blog)", shape, re.I):
            continue
        object_urls = {u for u in urls if is_object_like(u)}
        if len(object_urls) < 3:
            continue
        score = len(object_urls) * (2 if DETAIL_RE.search(next(iter(object_urls))) else 1)
        if score > best[0]:
            best = (score, sorted(object_urls))

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


# Namen von Unter-Sitemaps, die auf einen Objekt-Post-Type hindeuten.
# WordPress-SEO-Plugins erzeugen z.B. listing-sitemap.xml oder
# immobilie-sitemap.xml — das ist zuverlässiger als URL-Muster zu raten.
SITEMAP_OBJECT_RE = re.compile(
    r"(listing|immobilie|objekt|property|estate|expose|angebot|wohnung|haus)", re.I
)

# Immobilienspezifische schema.org-Typen. Generische Typen wie WebPage,
# Organization oder BreadcrumbList sagen nichts über Objektdaten aus.
IMMO_LD_TYPES = {
    "RealEstateListing",
    "Residence",
    "Apartment",
    "House",
    "SingleFamilyResidence",
    "Accommodation",
    "Place",
    "Offer",
    "Product",
}


def detect_vendors(blob: str) -> list[str]:
    return [name for name, pat in VENDORS.items() if re.search(pat, blob, re.I)]


def detect_structured(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    types: set[str] = set()
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.get_text() or ""
        try:
            data = json.loads(raw)
        except Exception:
            # Manche Sites betten mehrere Objekte oder kaputtes JSON ein
            types.update(re.findall(r'"@type"\s*:\s*"([^"]+)"', raw))
            continue
        for node in data if isinstance(data, list) else [data]:
            if isinstance(node, dict):
                t = node.get("@type")
                if isinstance(t, list):
                    types.update(t)
                elif t:
                    types.add(t)
                for sub in node.get("@graph", []) or []:
                    if isinstance(sub, dict) and sub.get("@type"):
                        st = sub["@type"]
                        types.update(st if isinstance(st, list) else [st])
    microdata = bool(soup.find(attrs={"itemtype": re.compile(r"schema\.org", re.I)}))
    return {"jsonld_types": sorted(types), "microdata": microdata}


def content_signals(html: str) -> dict:
    """Enthält das *statische* HTML bereits Objektdaten — oder ist es eine JS-Shell?"""
    return {
        "prices": len(PRICE_RE.findall(html)),
        "areas": len(AREA_RE.findall(html)),
        "html_kb": len(html) // 1024,
    }
```

- [ ] **Step 2: Failing Tests schreiben**

```python
"""Tests für app.agent_cascade_detect — reine, I/O-freie Erkennungsbausteine
der Extraktions-Kaskade, promoted aus Phase 0 (scripts/probe_agent_sites.py)."""

from __future__ import annotations

from app.agent_cascade_detect import (
    content_signals,
    detect_structured,
    detect_vendors,
    find_detail_links,
    is_object_like,
    link_shape,
)


def test_link_shape_groups_object_slugs_by_prefix():
    assert link_shape("https://x.de/objekte/haus-am-see") == "/objekte/*"
    assert link_shape("https://x.de/objekte/wohnung-tutzing") == "/objekte/*"


def test_link_shape_normalizes_query_keys_not_values():
    a = link_shape("https://x.de/index.php4?cmd=searchDetails&cursor=7")
    b = link_shape("https://x.de/index.php4?cmd=searchDetails&cursor=99")
    assert a == b


def test_is_object_like_rejects_known_nav_segment():
    assert is_object_like("https://x.de/immobilien/kontakt") is False


def test_is_object_like_accepts_long_hyphenated_slug():
    assert is_object_like("https://x.de/immobilien/moderne-gartenwohnung-tutzing") is True


def test_is_object_like_accepts_legacy_query_id():
    assert is_object_like("https://x.de/index.php4?cmd=searchDetails&objq[cursor]=7") is True


def test_find_detail_links_groups_object_pages_and_skips_nav():
    html = """
    <html><body>
      <a href="/immobilien/moderne-villa-am-see-tutzing">A</a>
      <a href="/immobilien/gemuetliche-wohnung-starnberg">B</a>
      <a href="/immobilien/grosszuegiges-haus-poecking">C</a>
      <a href="/immobilien/kontakt">Kontakt</a>
      <a href="/immobilien/team">Team</a>
    </body></html>
    """
    n, sample = find_detail_links(html, "https://x.de/immobilien/")
    assert n == 3
    assert all("/immobilien/" in u for u in sample)
    assert not any(u.endswith(("/kontakt", "/team")) for u in sample)


def test_find_detail_links_finds_flat_root_slugs():
    html = """
    <html><body>
      <a href="/moderne-gartenwohnung-in-ruhiger-wohnlage-tutzing">A</a>
      <a href="/grosszuegiges-einfamilienhaus-mit-seeblick-poecking">B</a>
      <a href="/exklusive-villa-direkt-am-starnberger-see">C</a>
      <a href="/kontakt">Kontakt</a>
    </body></html>
    """
    n, sample = find_detail_links(html, "https://x.de/")
    assert n == 3
    assert len(sample) == 3


def test_find_detail_links_returns_empty_below_group_threshold():
    html = '<html><body><a href="/immobilien/einzelnes-objekt-tutzing">A</a></body></html>'
    n, sample = find_detail_links(html, "https://x.de/immobilien/")
    assert n == 0
    assert sample == []


def test_detect_vendors_matches_onoffice_fingerprint():
    blob = '<script src="https://cdn.example.de/onoffice-for-wp-websites/app.js"></script>'
    assert "onoffice" in detect_vendors(blob)


def test_detect_vendors_returns_empty_for_unknown_markup():
    assert detect_vendors("<html><body>Nichts Besonderes</body></html>") == []


def test_detect_structured_extracts_immo_jsonld_type():
    html = """
    <script type="application/ld+json">
    {"@type": "RealEstateListing", "name": "Testobjekt"}
    </script>
    """
    result = detect_structured(html)
    assert "RealEstateListing" in result["jsonld_types"]


def test_detect_structured_ignores_generic_webpage_type():
    html = '<script type="application/ld+json">{"@type": "WebPage"}</script>'
    result = detect_structured(html)
    assert result["jsonld_types"] == ["WebPage"]


def test_content_signals_counts_prices_and_areas():
    html = "Preis: 450.000 € — Wohnfläche: 120 m² — Zweites Objekt: 89.000 EUR, 45 m²"
    sig = content_signals(html)
    assert sig["prices"] == 2
    assert sig["areas"] == 2
```

- [ ] **Step 3: Tests laufen lassen, sicherstellen dass sie fehlschlagen**

Run: `DB_PATH=./data/immo.db pytest tests/test_agent_cascade_detect.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'app.agent_cascade_detect'`

- [ ] **Step 4: Tests grün bekommen**

Datei aus Step 1 anlegen (bereits vollständiger Code oben).

Run: `DB_PATH=./data/immo.db pytest tests/test_agent_cascade_detect.py -v`
Expected: PASS (13 Tests)

- [ ] **Step 5: Lint + Commit**

```bash
DB_PATH=./data/immo.db ruff check app/agent_cascade_detect.py tests/test_agent_cascade_detect.py
git add app/agent_cascade_detect.py tests/test_agent_cascade_detect.py
git commit -m "feat(agents): reine Kaskaden-Erkennungsfunktionen aus Phase 0 promoten"
```

---

### Task 2: Netzwerk-Orchestrierung — Ein-Domain-Probe

**Files:**
- Create: `app/agent_probe.py`
- Test: `tests/test_agent_probe.py`

**Interfaces:**
- Consumes: `app.agent_cascade_detect.{detect_vendors, detect_structured, content_signals, find_detail_links, DETAIL_RE, LISTING_HINTS, IMMO_LD_TYPES, SITEMAP_OBJECT_RE}` (Task 1); `app.robots.USER_AGENT`.
- Produces: `async def probe_agent(domain: str, client: httpx.AsyncClient) -> dict` und `def classify_stage(row: dict) -> str`. Werden von Task 3 (`app/agent_onboarding.py`) importiert. `probe_agent()`'s Rückgabe-Dict trägt mindestens: `reachable`, `robots_allows_root`, `blocked`, `listing_url`, `vendors`, `structured`, `signals`, `detail_links`, `openimmo_url`, `has_immo_feed`, `feeds`, `sitemap_object_urls`, `sitemap_object_sample` — identisch zu den Keys, die `scripts/probe_agent_sites.py`'s `probe()` bereits liefert.

- [ ] **Step 1: Datei mit Netzwerk-Helfern und Orchestrator anlegen**

Adaptiert aus `scripts/probe_agent_sites.py` (Zeilen 279–362, 403–517, 520–542). Wichtigste Abweichung vom Original: `probe_agent()` bricht sofort ab, sobald `robots_allows_root` `False` ist — das Messwerkzeug durfte trotz Disallow weiterlesen (einmaliger, vom Nutzer verantworteter Testlauf), das automatisierte Onboarding gegen unbekannte Domains nicht (Spec §8). Außerdem: kein eigener Client/Semaphore mehr (Aufrufer liefert den `httpx.AsyncClient`), kein lokaler `UA`-String (wiederverwendet `app.robots.USER_AGENT`).

```python
"""Ein-Domain-Netzwerk-Orchestrierung der Extraktions-Kaskade (Vollabdeckung-
Spec §4.1). Adaptiert aus scripts/probe_agent_sites.py (Phase 0): dort probt
`probe()` viele Domains parallel mit eigenem Client für eine Messung; hier
probt `probe_agent()` GENAU EINE Domain mit dem vom Aufrufer bereitgestellten
Client, für den echten Onboarding-Vorgang in app.agent_onboarding.

Wichtigste Abweichung vom Messwerkzeug: robots.txt hat Vorrang. Ein Disallow
auf der Startseite beendet den Probe sofort (Spec §8) — das Messwerkzeug las
trotzdem weiter, weil es einmalig gegen vom Nutzer geprüfte Domains lief."""

from __future__ import annotations

import asyncio
import re
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from app.agent_cascade_detect import (
    DETAIL_RE,
    IMMO_LD_TYPES,
    LISTING_HINTS,
    SITEMAP_OBJECT_RE,
    content_signals,
    detect_structured,
    detect_vendors,
    find_detail_links,
)
from app.robots import USER_AGENT


async def fetch(client: httpx.AsyncClient, url: str) -> httpx.Response | None:
    try:
        return await client.get(url)
    except Exception:
        return None


async def validate_feed(client: httpx.AsyncClient, url: str) -> dict:
    """Enthält der Feed Objekte — oder ist es der WordPress-Blogfeed?

    Der naive Test (Preis/m² irgendwo im Body) schlägt bei SEO-Ratgeberartikeln
    an ("Was ist mein Haus wert?"). Entscheidend ist deshalb die *Einzel-Einträge*:
    Objekte liegen unter Objekt-Pfaden und tragen Eckdaten im Titel, Blogposts
    liegen unter /blog/ oder Datumspfaden und stellen Fragen.
    """
    r = await fetch(client, url)
    if r is None or r.status_code != 200:
        return {"url": url, "ok": False}

    items = re.findall(r"<(?:item|entry)\b.*?</(?:item|entry)>", r.text, re.S | re.I)
    hits = 0
    for it in items:
        link_m = re.search(r"<link[^>]*>([^<]+)</link>|<link[^>]*href=\"([^\"]+)\"", it, re.I)
        link = (link_m.group(1) or link_m.group(2) or "") if link_m else ""
        title_m = re.search(r"<title[^>]*>(.*?)</title>", it, re.S | re.I)
        title = title_m.group(1) if title_m else ""
        looks_like_object = bool(DETAIL_RE.search(link)) or bool(
            re.search(r"\d{1,3}(?:[.\s]\d{3})+\s*(?:€|EUR)", title)
            or re.search(r"\d{2,4}(?:[,.]\d+)?\s*m²", title)
            or re.search(r"\d+([,.]\d+)?[-\s]?Zimmer", title, re.I)
        )
        if looks_like_object and "?" not in title:
            hits += 1
    return {
        "url": url,
        "ok": True,
        "items": len(items),
        "object_items": hits,
        "immo_like": hits >= 2,
    }


async def find_openimmo(client: httpx.AsyncClient, root: str) -> str | None:
    """Typische Ablageorte einer öffentlich erreichbaren OpenImmo-XML."""
    for path in (
        "/openimmo.xml",
        "/export/openimmo.xml",
        "/wp-content/uploads/openimmo/",
        "/wp-content/uploads/immonex-openimmo/",
        "/openimmo/",
    ):
        r = await fetch(client, urljoin(root, path))
        if r is not None and r.status_code == 200 and re.search(r"openimmo|<immobilie", r.text[:4000], re.I):
            return urljoin(root, path)
    return None


def find_listing_url(html: str, base: str) -> str | None:
    """Beste Kandidaten-URL für die Angebotsübersicht aus den Startseiten-Links."""
    soup = BeautifulSoup(html, "html.parser")
    host = urlparse(base).netloc
    best: tuple[int, str] | None = None
    for a in soup.find_all("a", href=True):
        full = urljoin(base, a["href"])
        if urlparse(full).netloc != host:
            continue
        path = urlparse(full).path
        if not LISTING_HINTS.search(path):
            continue
        text = a.get_text(" ", strip=True).lower()
        score = 0
        stem = re.sub(r"\.(html?|php\d?|aspx?)$", "", path.rstrip("/"), flags=re.I)
        if re.search(r"(immobilien|objekte|angebote|kaufobjekte)$", stem, re.I):
            score += 3
        if any(w in text for w in ("angebot", "objekt", "immobilien", "kaufen")):
            score += 2
        score -= path.count("/")
        if best is None or score > best[0]:
            best = (score, full)
    return best[1] if best else None


async def probe_agent(domain: str, client: httpx.AsyncClient) -> dict:
    """Probt EINE Domain und liefert die Rohdaten für classify_stage().

    `client` muss bereits einen höflichen User-Agent tragen (siehe
    app.sources.base.SourceAdapter — derselbe String wie app.robots.USER_AGENT,
    damit robots.can_fetch() und der tatsächliche Abruf nicht auseinanderlaufen)."""
    out: dict = {"domain": domain, "reachable": False}
    root = f"https://{domain}/"
    r = await fetch(client, root)
    if r is None:  # DNS/TLS-Fehler: einmal mit www. gegenprüfen
        root = f"https://www.{domain}/"
        r = await fetch(client, root)
    if r is None or r.status_code >= 400:
        if r is not None and r.status_code in (401, 403, 429):
            out["error"] = f"HTTP {r.status_code}"
            out["blocked"] = True
        else:
            out["error"] = f"HTTP {r.status_code}" if r else "unreachable"
        return out

    out["reachable"] = True
    out["final_url"] = str(r.url)
    home = r.text
    header_blob = " ".join(f"{k}:{v}" for k, v in r.headers.items())

    rp_txt = await fetch(client, urljoin(root, "/robots.txt"))
    sitemap_urls: list[str] = []
    if rp_txt is not None and rp_txt.status_code == 200:
        out["robots"] = True
        sitemap_urls = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", rp_txt.text)
        rp = RobotFileParser()
        rp.parse(rp_txt.text.splitlines())
        out["robots_allows_root"] = rp.can_fetch(USER_AGENT, root)
    else:
        out["robots"] = False
        out["robots_allows_root"] = True  # kein robots.txt = kein Verbot

    if not out["robots_allows_root"]:
        # Spec §8: Disallow -> kein weiterer Abruf. Anders als das
        # Phase-0-Messwerkzeug bricht das echte Onboarding hier ab.
        return out

    out["sitemap"] = False
    out["sitemap_object_urls"] = 0
    if not sitemap_urls:
        sitemap_urls = [urljoin(root, "/sitemap.xml"), urljoin(root, "/wp-sitemap.xml")]
    for sm_url in sitemap_urls[:2]:
        sm = await fetch(client, sm_url)
        if sm is None or sm.status_code != 200 or "<" not in sm.text[:200]:
            continue
        out["sitemap"] = True
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sm.text)
        out["sitemap_entries"] = len(locs)
        out["sitemap_listing_like"] = sum(1 for u in locs if LISTING_HINTS.search(u))

        subs = [u for u in locs if u.endswith(".xml") and SITEMAP_OBJECT_RE.search(u)]
        obj_urls: set[str] = set()
        for sub in subs[:3]:
            sr = await fetch(client, sub)
            if sr is None or sr.status_code != 200:
                continue
            for u in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sr.text):
                if DETAIL_RE.search(u):
                    obj_urls.add(u)
        obj_urls.update(u for u in locs if DETAIL_RE.search(u))
        out["sitemap_object_urls"] = len(obj_urls)
        out["sitemap_object_sample"] = sorted(obj_urls)[:2]
        break

    soup_home = BeautifulSoup(home, "html.parser")
    feeds = [
        urljoin(root, link["href"])
        for link in soup_home.find_all("link", rel=lambda v: v and "alternate" in v)
        if link.get("type", "").lower() in ("application/rss+xml", "application/atom+xml")
        and link.get("href")
    ]
    checked = [await validate_feed(client, f) for f in feeds[:2]]
    out["feeds"] = checked
    out["has_immo_feed"] = any(f.get("immo_like") for f in checked)

    out["openimmo_hint"] = bool(re.search(r"openimmo", home + header_blob, re.I))
    out["openimmo_url"] = await find_openimmo(client, root)

    gen = soup_home.find("meta", attrs={"name": "generator"})
    out["generator"] = gen.get("content", "")[:80] if gen else ""
    out["wordpress"] = bool(re.search(r"wp-content|wp-json|wordpress", home, re.I))

    listing_url = find_listing_url(home, str(r.url))
    out["listing_url"] = listing_url
    blob = home + " " + header_blob
    listing_html = ""
    if listing_url:
        lr = await fetch(client, listing_url)
        if lr is not None and lr.status_code == 200:
            listing_html = lr.text
            blob += " " + listing_html

    out["vendors"] = detect_vendors(blob)
    out["structured"] = detect_structured(listing_html or home)
    out["signals"] = content_signals(listing_html or home)
    out["probed_listing_page"] = bool(listing_html)

    if listing_html:
        n, sample = find_detail_links(listing_html, listing_url)
        out["detail_links"] = n
        out["detail_sample"] = sample
    else:
        out["detail_links"] = 0

    await asyncio.sleep(1.0)  # Höflichkeitspause pro Host
    return out


def classify_stage(row: dict) -> str:
    """Welche Kaskadenstufe würde hier tatsächlich greifen?

    Bewusst streng: ein vorhandener Feed zählt nur, wenn er Immobilien enthält,
    und JSON-LD nur bei immobilienspezifischen Typen. Ein WordPress-Blogfeed
    oder ein `WebPage`-Marker ist kein Extraktionsweg."""
    if not row.get("reachable"):
        return "blocked (braucht Browser)" if row.get("blocked") else "unreachable"
    if row.get("robots_allows_root") is False:
        return "robots-disallowed"
    if row.get("openimmo_url") or row.get("has_immo_feed"):
        return "1-feed/openimmo"
    if row.get("vendors"):
        return "2-vendor"
    st = row.get("structured", {})
    if IMMO_LD_TYPES.intersection(st.get("jsonld_types", [])):
        return "3-structured"
    if row.get("sitemap_object_urls", 0) >= 3:
        return "4-sitemap-objekte"
    if row.get("detail_links", 0) >= 3:
        return "5-detail-links"
    if row.get("signals", {}).get("prices", 0) >= 2:
        return "6-recipe (HTML hat Daten)"
    return "7-js-shell/unklar"
```

- [ ] **Step 2: Failing Tests schreiben**

```python
"""Tests für app.agent_probe — Ein-Domain-Netzwerk-Orchestrierung der
Extraktions-Kaskade. httpx wird über AsyncMock mit URL-Routing gemockt
(Projekt-Konvention, siehe tests/test_robots.py) — kein respx."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent_probe import classify_stage, probe_agent


def _resp(status_code=200, text="", url=None):
    r = MagicMock()
    r.status_code = status_code
    r.text = text
    r.url = url or "https://x.de/"
    r.headers = {}
    return r


def _routed_client(routes: dict[str, MagicMock], default=None):
    """routes: URL (exakt) -> Response-Mock. Alles andere -> default (404)."""
    client = AsyncMock()

    async def _get(url, *a, **kw):
        if url in routes:
            return routes[url]
        return default or _resp(status_code=404)

    client.get = AsyncMock(side_effect=_get)
    return client


@pytest.mark.asyncio
async def test_probe_agent_unreachable_domain_short_circuits():
    client = AsyncMock()
    client.get = AsyncMock(side_effect=Exception("connection refused"))

    row = await probe_agent("tot.example.de", client)

    assert row["reachable"] is False
    assert row["error"] == "unreachable"


@pytest.mark.asyncio
async def test_probe_agent_403_marks_blocked():
    client = _routed_client({"https://blocked.example.de/": _resp(status_code=403)})

    row = await probe_agent("blocked.example.de", client)

    assert row["reachable"] is False
    assert row["blocked"] is True


@pytest.mark.asyncio
async def test_probe_agent_stops_after_robots_disallow():
    """Spec §8: Disallow -> kein weiterer Abruf. Der Sitemap-Pfad darf nie
    angefragt werden, wenn robots.txt die Startseite verbietet."""
    routes = {
        "https://x.de/": _resp(text="<html></html>"),
        "https://x.de/robots.txt": _resp(text="User-agent: *\nDisallow: /"),
    }
    client = _routed_client(routes)

    row = await probe_agent("x.de", client)

    assert row["robots_allows_root"] is False
    assert "sitemap" not in row
    called_urls = {c.args[0] for c in client.get.await_args_list}
    assert "https://x.de/sitemap.xml" not in called_urls


@pytest.mark.asyncio
async def test_probe_agent_detects_vendor_and_detail_links():
    home_html = """
    <html><body>
      <script src="/wp-content/plugins/onoffice-for-wp-websites/app.js"></script>
      <a href="/immobilien/">Immobilien</a>
    </body></html>
    """
    listing_html = """
    <html><body>
      <a href="/immobilien/villa-am-see-tutzing">A</a>
      <a href="/immobilien/wohnung-starnberg-zentral">B</a>
      <a href="/immobilien/haus-poecking-mit-garten">C</a>
    </body></html>
    """
    routes = {
        "https://x.de/": _resp(text=home_html),
        "https://x.de/robots.txt": _resp(status_code=404),
        "https://x.de/sitemap.xml": _resp(status_code=404),
        "https://x.de/wp-sitemap.xml": _resp(status_code=404),
        "https://x.de/immobilien/": _resp(text=listing_html, url="https://x.de/immobilien/"),
    }
    client = _routed_client(routes)

    row = await probe_agent("x.de", client)

    assert row["reachable"] is True
    assert "onoffice" in row["vendors"]
    assert row["detail_links"] == 3
    assert classify_stage(row) == "2-vendor"


def test_classify_stage_unreachable():
    assert classify_stage({"reachable": False}) == "unreachable"


def test_classify_stage_blocked():
    assert classify_stage({"reachable": False, "blocked": True}) == "blocked (braucht Browser)"


def test_classify_stage_robots_disallowed_before_any_cascade_check():
    row = {"reachable": True, "robots_allows_root": False, "vendors": ["onoffice"]}
    assert classify_stage(row) == "robots-disallowed"


def test_classify_stage_prefers_vendor_over_detail_links():
    row = {
        "reachable": True,
        "robots_allows_root": True,
        "vendors": ["onoffice"],
        "detail_links": 10,
    }
    assert classify_stage(row) == "2-vendor"


def test_classify_stage_falls_back_to_js_shell():
    row = {
        "reachable": True,
        "robots_allows_root": True,
        "vendors": [],
        "structured": {"jsonld_types": []},
        "sitemap_object_urls": 0,
        "detail_links": 0,
        "signals": {"prices": 0},
    }
    assert classify_stage(row) == "7-js-shell/unklar"
```

- [ ] **Step 3: Tests laufen lassen, sicherstellen dass sie fehlschlagen**

Run: `DB_PATH=./data/immo.db pytest tests/test_agent_probe.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'app.agent_probe'`

- [ ] **Step 4: Tests grün bekommen**

Datei aus Step 1 anlegen (bereits vollständiger Code oben).

Run: `DB_PATH=./data/immo.db pytest tests/test_agent_probe.py -v`
Expected: PASS (9 Tests)

- [ ] **Step 5: Lint + Commit**

```bash
DB_PATH=./data/immo.db ruff check app/agent_probe.py tests/test_agent_probe.py
git add app/agent_probe.py tests/test_agent_probe.py
git commit -m "feat(agents): Ein-Domain-Probe + Kaskaden-Klassifikation (robots-first)"
```

---

### Task 3: Onboarding — Klassifikation persistieren

**Files:**
- Create: `app/agent_onboarding.py`
- Test: `tests/test_agent_onboarding.py`

**Interfaces:**
- Consumes: `app.agent_probe.{probe_agent, classify_stage}` (Task 2); `app.db.Agent`; `import app.db as db_module`.
- Produces: `async def onboard_agent(agent_id: int, client: httpx.AsyncClient, session=None) -> Agent`. Schreibt `extraction`, `listing_url`, `coverage_status`, `coverage_reason`, `robots_status`, `last_checked` auf die `Agent`-Zeile. Session-Semantik identisch zu `geocode()` in `app/geocoding.py`: wird eine Session übergeben, committet `onboard_agent` NICHT selbst (Aufrufer committet); ohne übergebene Session öffnet und committet die Funktion selbst.

- [ ] **Step 1: Datei mit Mapping-Tabellen und Schreibfunktion anlegen**

```python
"""Bildet eine klassifizierte Kaskadenstufe (app.agent_probe.classify_stage)
auf das extraction-Schema ab (Vollabdeckung-Spec §5.1) und schreibt das
Ergebnis auf die Agent-Zeile zurück.

Session-Muster identisch zu geocode() in app/geocoding.py: SQLite erlaubt nur
einen offenen Schreiber — wer bereits eine Transaktion offen hält (z.B.
run_source()), übergibt seine Session; onboard_agent() merged/committet dann
nicht selbst, sondern überlässt das dem Aufrufer."""

from __future__ import annotations

from datetime import datetime

import httpx

import app.db as db_module
from app.agent_probe import classify_stage, probe_agent
from app.db import Agent

_AUTO_HARVEST_STAGES = {
    "1-feed/openimmo",
    "2-vendor",
    "3-structured",
    "4-sitemap-objekte",
    "5-detail-links",
}

# stage -> (coverage_status, coverage_reason, zusätzliche extraction-Felder)
_TERMINAL_STAGES: dict[str, tuple[str, str, dict]] = {
    "6-recipe (HTML hat Daten)": (
        "needs-manual-watch",
        "HTML enthält Preis-/Flächenangaben, aber kein automatischer "
        "Erkennungsweg — wartet auf das LLM-Rezept (Phase 2, Stufe learned_recipe).",
        {},
    ),
    "7-js-shell/unklar": (
        "needs-manual-watch",
        "Keine Objektdaten im statischen HTML erkennbar — vermutlich JS-Shell "
        "oder unbekannte Struktur.",
        {},
    ),
    "unreachable": (
        "unreachable",
        "Site nicht erreichbar (DNS/TLS-Fehler oder HTTP-Fehlerstatus).",
        {},
    ),
    "blocked (braucht Browser)": (
        "bot-blocked",
        "HTTP 401/403/429 — Bot-Schutz vermutet, braucht Playwright-Rendering (Phase 2c).",
        {"needs_browser": True},
    ),
}


def _extraction_for_auto_harvest_stage(stage: str, row: dict) -> dict:
    if stage == "1-feed/openimmo":
        feed_url = row.get("openimmo_url")
        if not feed_url:
            feed_url = next((f["url"] for f in row.get("feeds", []) if f.get("immo_like")), None)
        return {"method": "feed_adapter", "feed_url": feed_url}
    if stage == "2-vendor":
        vendor = row["vendors"][0]
        return {"method": f"vendor:{vendor}", "vendor": vendor}
    if stage == "3-structured":
        return {"method": "structured_data"}
    if stage == "4-sitemap-objekte":
        sample = row.get("sitemap_object_sample") or []
        return {"method": "sitemap_objekte", "sitemap_url": sample[0] if sample else None}
    if stage == "5-detail-links":
        return {"method": "detail_links"}
    raise ValueError(f"kein auto-harvest-Mapping für Stufe {stage!r}")


async def _onboard(agent_id: int, client: httpx.AsyncClient, session) -> Agent:
    agent = session.get(Agent, agent_id)
    if agent is None:
        raise ValueError(f"agent {agent_id} not found")
    if not agent.verified_domain:
        raise ValueError(f"agent {agent_id} has no verified_domain")

    row = await probe_agent(agent.verified_domain, client)
    stage = classify_stage(row)
    agent.last_checked = datetime.utcnow()

    if row.get("reachable"):
        agent.robots_status = "disallowed" if row.get("robots_allows_root") is False else "allowed"
    else:
        agent.robots_status = None

    if stage in _AUTO_HARVEST_STAGES:
        agent.extraction = _extraction_for_auto_harvest_stage(stage, row)
        agent.listing_url = row.get("listing_url")
        agent.coverage_status = "auto-harvested"
        agent.coverage_reason = None
    elif stage == "robots-disallowed":
        agent.coverage_status = "robots-disallowed"
        agent.coverage_reason = "robots.txt verbietet den Zugriff auf die Startseite."
        agent.extraction = {}
    else:
        status, reason, extra = _TERMINAL_STAGES.get(
            stage, ("needs-manual-watch", f"Unbekannte Kaskadenstufe: {stage}", {})
        )
        agent.coverage_status = status
        agent.coverage_reason = reason
        agent.extraction = extra

    return agent


async def onboard_agent(agent_id: int, client: httpx.AsyncClient, session=None) -> Agent:
    """Probt agent.verified_domain, klassifiziert die Kaskadenstufe und
    schreibt extraction/listing_url/coverage_status/coverage_reason zurück.

    `session`: optionale Session des Aufrufers. Ohne Angabe öffnet und
    committet onboard_agent() selbst; mit übergebener Session bleibt das
    Committen beim Aufrufer (SQLite-Single-Writer, siehe Modul-Docstring)."""
    if session is not None:
        return await _onboard(agent_id, client, session)
    with db_module.SessionLocal() as own_session:
        agent = await _onboard(agent_id, client, own_session)
        own_session.commit()
        return agent
```

- [ ] **Step 2: Failing Tests schreiben**

```python
"""Tests für app.agent_onboarding — bildet die klassifizierte Kaskadenstufe
auf das extraction-Schema ab und schreibt sie auf die Agent-Zeile."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db as db_module
from app.agent_onboarding import onboard_agent
from app.db import Agent, Base


@pytest.fixture()
def session(monkeypatch, tmp_path):
    test_engine = create_engine(f"sqlite:///{tmp_path}/test.db", echo=False, future=True)
    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)
    return TestSession


def _make_agent(session, **overrides) -> int:
    defaults = dict(name="Test Makler", verified_domain="x.de")
    defaults.update(overrides)
    with session() as s:
        agent = Agent(**defaults)
        s.add(agent)
        s.commit()
        return agent.id


@pytest.mark.asyncio
async def test_onboard_agent_sets_auto_harvested_for_vendor_stage(session, monkeypatch):
    agent_id = _make_agent(session)
    fake_row = {
        "reachable": True,
        "robots_allows_root": True,
        "vendors": ["onoffice"],
        "listing_url": "https://x.de/immobilien/",
        "structured": {"jsonld_types": []},
        "sitemap_object_urls": 0,
        "detail_links": 0,
        "signals": {"prices": 0},
    }
    monkeypatch.setattr("app.agent_onboarding.probe_agent", AsyncMock(return_value=fake_row))

    client = AsyncMock()
    with session() as s:
        await onboard_agent(agent_id, client, session=s)
        s.commit()

    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.coverage_status == "auto-harvested"
        assert agent.extraction == {"method": "vendor:onoffice", "vendor": "onoffice"}
        assert agent.listing_url == "https://x.de/immobilien/"
        assert agent.last_checked is not None


@pytest.mark.asyncio
async def test_onboard_agent_sets_needs_manual_watch_for_js_shell(session, monkeypatch):
    agent_id = _make_agent(session)
    fake_row = {
        "reachable": True,
        "robots_allows_root": True,
        "vendors": [],
        "structured": {"jsonld_types": []},
        "sitemap_object_urls": 0,
        "detail_links": 0,
        "signals": {"prices": 0},
    }
    monkeypatch.setattr("app.agent_onboarding.probe_agent", AsyncMock(return_value=fake_row))

    client = AsyncMock()
    with session() as s:
        await onboard_agent(agent_id, client, session=s)
        s.commit()

    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.coverage_status == "needs-manual-watch"
        assert "JS-Shell" in agent.coverage_reason


@pytest.mark.asyncio
async def test_onboard_agent_sets_robots_disallowed(session, monkeypatch):
    agent_id = _make_agent(session)
    fake_row = {"reachable": True, "robots_allows_root": False}
    monkeypatch.setattr("app.agent_onboarding.probe_agent", AsyncMock(return_value=fake_row))

    client = AsyncMock()
    with session() as s:
        await onboard_agent(agent_id, client, session=s)
        s.commit()

    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.coverage_status == "robots-disallowed"
        assert agent.robots_status == "disallowed"


@pytest.mark.asyncio
async def test_onboard_agent_sets_bot_blocked_with_needs_browser_hint(session, monkeypatch):
    agent_id = _make_agent(session)
    fake_row = {"reachable": False, "blocked": True}
    monkeypatch.setattr("app.agent_onboarding.probe_agent", AsyncMock(return_value=fake_row))

    client = AsyncMock()
    with session() as s:
        await onboard_agent(agent_id, client, session=s)
        s.commit()

    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.coverage_status == "bot-blocked"
        assert agent.extraction == {"needs_browser": True}


@pytest.mark.asyncio
async def test_onboard_agent_raises_for_missing_verified_domain(session):
    agent_id = _make_agent(session, verified_domain=None)
    client = AsyncMock()

    with pytest.raises(ValueError, match="verified_domain"):
        with session() as s:
            await onboard_agent(agent_id, client, session=s)


@pytest.mark.asyncio
async def test_onboard_agent_without_explicit_session_commits_itself(session, monkeypatch):
    agent_id = _make_agent(session)
    fake_row = {
        "reachable": True,
        "robots_allows_root": True,
        "vendors": ["onoffice"],
        "listing_url": "https://x.de/immobilien/",
        "structured": {"jsonld_types": []},
        "sitemap_object_urls": 0,
        "detail_links": 0,
        "signals": {"prices": 0},
    }
    monkeypatch.setattr("app.agent_onboarding.probe_agent", AsyncMock(return_value=fake_row))

    client = AsyncMock()
    await onboard_agent(agent_id, client)  # keine Session übergeben

    with session() as s:
        agent = s.get(Agent, agent_id)
        assert agent.coverage_status == "auto-harvested"
```

- [ ] **Step 3: Tests laufen lassen, sicherstellen dass sie fehlschlagen**

Run: `DB_PATH=./data/immo.db pytest tests/test_agent_onboarding.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'app.agent_onboarding'`

- [ ] **Step 4: Tests grün bekommen**

Datei aus Step 1 anlegen (bereits vollständiger Code oben).

Run: `DB_PATH=./data/immo.db pytest tests/test_agent_onboarding.py -v`
Expected: PASS (6 Tests)

- [ ] **Step 5: Lint + Commit**

```bash
DB_PATH=./data/immo.db ruff check app/agent_onboarding.py tests/test_agent_onboarding.py
git add app/agent_onboarding.py tests/test_agent_onboarding.py
git commit -m "feat(agents): Onboarding schreibt Kaskaden-Klassifikation auf Agent-Zeile"
```

---

### Task 4: CLI-Trigger + manueller End-to-End-Test

**Files:**
- Create: `scripts/onboard_agents.py`
- Test: `tests/test_onboard_agents_cli.py`

**Interfaces:**
- Consumes: `app.agent_onboarding.onboard_agent` (Task 3); `app.robots.USER_AGENT`; `app.db.{Agent, COVERAGE_STATUSES}`.
- Produces: CLI-Skript, aufrufbar als `python -m scripts.onboard_agents` (alle Agents mit `verified_domain` und `coverage_status == "unknown"`) oder `python -m scripts.onboard_agents --agent-id 3` (ein einzelner Agent, unabhängig vom Status — für gezieltes Nachtriggern).

- [ ] **Step 1: CLI-Skript anlegen**

Mirrored an `scripts/verify_source.py`'s Struktur (Argument-Parsing, `configure_logging()`, Tabellen-Ausgabe).

```python
"""Onboarding für Makler-Sites: probt agent.verified_domain, klassifiziert
die Kaskadenstufe und schreibt das Ergebnis zurück (Vollabdeckung-Spec §4.1).

Manueller Trigger, solange Phase 3 (Discovery) und Phase 4 (Dashboard-Tab)
noch nicht existieren.

Usage:
    python -m scripts.onboard_agents                 # alle unknown-Agents
    python -m scripts.onboard_agents --agent-id 3     # ein einzelner Agent
"""

from __future__ import annotations

import argparse
import asyncio

import httpx
from sqlalchemy import select

import app.db as db_module
from app.agent_onboarding import onboard_agent
from app.db import Agent
from app.logging_setup import configure_logging
from app.robots import USER_AGENT


async def _agent_ids_to_onboard(agent_id: int | None) -> list[int]:
    with db_module.SessionLocal() as session:
        if agent_id is not None:
            return [agent_id]
        stmt = select(Agent.id).where(
            Agent.verified_domain.is_not(None), Agent.coverage_status == "unknown"
        )
        return list(session.scalars(stmt))


async def main(agent_id: int | None) -> None:
    configure_logging()
    ids = await _agent_ids_to_onboard(agent_id)
    if not ids:
        print("Keine Agents zum Onboarden (verified_domain gesetzt + coverage_status == 'unknown').")
        return

    print(f"Onboarding {len(ids)} Agent(s) …")
    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "de-DE,de;q=0.9"},
    ) as client:
        for aid in ids:
            agent = await onboard_agent(aid, client)
            print(f"  [{agent.id:>4}] {agent.name:<30} {agent.coverage_status:<20} {agent.extraction}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent-id", type=int, default=None)
    args = ap.parse_args()
    asyncio.run(main(args.agent_id))
```

- [ ] **Step 2: Failing Test schreiben**

```python
"""Test für scripts.onboard_agents — Agent-Auswahl für den CLI-Trigger."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db as db_module
from app.db import Agent, Base
from scripts.onboard_agents import _agent_ids_to_onboard


@pytest.fixture()
def session(monkeypatch, tmp_path):
    test_engine = create_engine(f"sqlite:///{tmp_path}/test.db", echo=False, future=True)
    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)
    return TestSession


@pytest.mark.asyncio
async def test_agent_ids_to_onboard_selects_unknown_with_verified_domain(session):
    with session() as s:
        a = Agent(name="A", verified_domain="a.de", coverage_status="unknown")
        b = Agent(name="B", verified_domain=None, coverage_status="unknown")
        c = Agent(name="C", verified_domain="c.de", coverage_status="auto-harvested")
        s.add_all([a, b, c])
        s.commit()
        a_id = a.id

    ids = await _agent_ids_to_onboard(None)

    assert ids == [a_id]


@pytest.mark.asyncio
async def test_agent_ids_to_onboard_with_explicit_id_ignores_status(session):
    with session() as s:
        c = Agent(name="C", verified_domain="c.de", coverage_status="auto-harvested")
        s.add(c)
        s.commit()
        c_id = c.id

    ids = await _agent_ids_to_onboard(c_id)

    assert ids == [c_id]
```

- [ ] **Step 3: Test laufen lassen, sicherstellen dass er fehlschlägt**

Run: `DB_PATH=./data/immo.db pytest tests/test_onboard_agents_cli.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'scripts.onboard_agents'`

- [ ] **Step 4: Test grün bekommen**

Datei aus Step 1 anlegen (bereits vollständiger Code oben).

Run: `DB_PATH=./data/immo.db pytest tests/test_onboard_agents_cli.py -v`
Expected: PASS (2 Tests)

- [ ] **Step 5: Manueller End-to-End-Test gegen eine echte Domain**

Kein automatisierter Test — echter Netzwerk-Abruf gegen eine reale Site, per Hand einmalig verifiziert:

```bash
DB_PATH=./data/immo.db python3 -c "
import app.db as db_module
db_module.init_db()
from app.db import Agent
with db_module.SessionLocal() as s:
    a = Agent(name='BS Immobilien Test', verified_domain='bs-immo.de')
    s.add(a)
    s.commit()
    print('agent id:', a.id)
"
DB_PATH=./data/immo.db python -m scripts.onboard_agents
```

Erwartung: Zeile mit `coverage_status` ungleich `unknown` und einem plausiblen `extraction`-Dict (z.B. `{'method': 'detail_links'}` oder ein `vendor:`-Key). Danach die Testzeile wieder löschen:

```bash
DB_PATH=./data/immo.db python3 -c "
import app.db as db_module
from app.db import Agent
with db_module.SessionLocal() as s:
    s.query(Agent).filter(Agent.name == 'BS Immobilien Test').delete()
    s.commit()
"
```

- [ ] **Step 6: Lint + Commit**

```bash
DB_PATH=./data/immo.db ruff check scripts/onboard_agents.py tests/test_onboard_agents_cli.py
git add scripts/onboard_agents.py tests/test_onboard_agents_cli.py
git commit -m "feat(agents): CLI-Trigger für Site-Onboarding"
```

---

## Self-Review-Notizen

- **Spec-Abdeckung:** §4.1 (Kaskaden-Klassifikation, robots-first) → Task 2/3. §5.1 (`extraction`-Schema, `coverage_status`-Werte) → Task 3. §8 (robots.txt-Vorrang, ehrlicher User-Agent) → Task 2 (früher Abbruch), wiederverwendet `app.robots.USER_AGENT` aus Phase 1. §11 (Testing: Kaskadenstufen gegen HTML-Fixtures, Grenzfälle) → Task 1/2 Tests.
- **Bewusst außerhalb dieses Plans:** Objekt-Detailseiten abrufen und zu `RawListing` parsen (Phase 2b), Change-Gate-Fingerprint (Phase 2c), Playwright-Rendering (Phase 2c), LLM-Rezept (Phase 2d), Discovery/Domain-Auflösung (Phase 3), Dashboard-Tab (Phase 4). Der dormant Deadlock-Bug in `agents_adapter.py`s robots-disallowed-Zweig (zweite `SessionLocal()` innerhalb einer offenen `run_source()`-Transaktion) bleibt in diesem Plan unangetastet — er ist weiterhin unerreichbar, solange `EXTRACTION_METHODS` leer ist, und wird erst mit Phase 2b scharf; der Fix gehört dorthin, nicht hierher.
- **Typkonsistenz geprüft:** `probe_agent(domain, client) -> dict` (Task 2) → `onboard_agent`s `row = await probe_agent(...)` (Task 3) — Feldnamen (`reachable`, `robots_allows_root`, `vendors`, `listing_url`, `sitemap_object_sample`, `feeds`, `openimmo_url`) stimmen zwischen Produzent und Konsument überein. `classify_stage(row) -> str` liefert exakt die Stufen-Strings, die `_AUTO_HARVEST_STAGES`/`_TERMINAL_STAGES` in Task 3 als Keys erwarten (inkl. des neuen `"robots-disallowed"`-Strings, der in `scripts/probe_agent_sites.py`'s Original-`classify()` noch nicht existierte).

## Execution Handoff

Plan gespeichert unter `docs/superpowers/plans/2026-08-06-makler-vollabdeckung-phase2a-site-onboarding.md`. Zwei Ausführungsoptionen:

**1. Subagent-Driven (empfohlen)** — frischer Subagent pro Task, Review zwischen den Tasks, schnelle Iteration

**2. Inline Execution** — Ausführung in dieser Session über executing-plans, Batch-Ausführung mit Checkpoints

Welcher Ansatz?
