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


def find_detail_links(html: str, base: str, limit: int | None = 3) -> tuple[int, list[str]]:
    """Objektlinks strukturell finden — ohne Vokabular-Annahmen.

    Wortlisten scheitern an Legacy-CMS (`index.php4?cmd=searchDetails&cursor=7`)
    und an fremdsprachigen Slugs. Zwei strukturelle Signale tragen weiter:

    1. **Gleichförmige Gruppe** — viele Links unter demselben Präfix bzw. mit
       derselben Query-Signatur, die sich nur im Objektbezeichner unterscheiden.
    2. **Lange Root-Slugs** — manche CMS legen Objekte flach im Root ab, wodurch
       jedes Objekt ein eigenes Präfix bekommt und (1) leerläuft. Solche Slugs
       sind aber deutlich länger und mehrgliedriger als Navigationslinks.

    `limit` begrenzt die zurückgegebene URL-Liste (Default 3, wie bisher —
    für Probing/Logging reicht eine Stichprobe). `limit=None` liefert die
    volle Liste — für den tatsächlichen Harvest in Phase 2b
    (app.sources.agent_handlers), wo jede gefundene Objekt-URL abgerufen
    werden muss, nicht nur eine Stichprobe.
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

    sample = best[1][:limit] if limit is not None else best[1]
    return len(best[1]), sample


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


def content_signals(html: str) -> dict:
    """Enthält das *statische* HTML bereits Objektdaten — oder ist es eine JS-Shell?"""
    return {
        "prices": len(PRICE_RE.findall(html)),
        "areas": len(AREA_RE.findall(html)),
        "html_kb": len(html) // 1024,
    }
