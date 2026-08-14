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

import html
import re

from app.models import PropertyType

_LABELED_PRICE_RE = re.compile(r"(?:Kaufpreis|Preis)\b[^0-9€]{0,40}([\d.]{4,})\s*(?:€|EUR)", re.I)
_PRICE_RE = re.compile(r"([\d.]{4,})\s*(?:€|EUR)")
_QM_RE = re.compile(r"([\d.,]+)\s*m²")
_ROOMS_RE = re.compile(r"([\d,]+)\s*Zi(?:mmer)?\b", re.I)
# Bewusst NUR ein Wort nach der PLZ: auf einer ganzen Detailseite (statt
# eines isolierten Kartentext-Snippets) folgt auf PLZ+Ort oft direkt ein
# weiteres grossgeschriebenes Wort (deutsche Substantivgrossschreibung, z.B.
# "82327 Tutzing Immobilie") -- ein optionaler zweiter Match-Teil würde das
# fälschlich in den Ortsnamen ziehen (real beobachtet in Produktion). Die
# tatsächlichen mehrteiligen Ortsnamen im Suchgebiet (app.pipeline.
# LOCATION_ALLOWLIST_RE, z.B. "Berg (Starnberger See)", "St. Heinrich") haben
# ohnehin abweichende Trenner, die dieses simple Muster nie sauber trifft.
_PLZ_ORT_RE = re.compile(r"\b(\d{5})\s+([A-ZÄÖÜ][a-zäöüß\-]+)")

_TITLE_TAG_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")
_OG_TITLE_RE = re.compile(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', re.I)
_WHITESPACE_RE = re.compile(r"\s+")


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


def extract_title(html_source: str, fallback_text: str = "") -> str:
    """`html_source` bewusst nicht `html` genannt -- das Modul importiert
    `html` für `html.unescape()`, ein gleichnamiger Parameter würde diesen
    Import innerhalb der Funktion verdecken."""
    m = _TITLE_TAG_RE.search(html_source)
    if m:
        candidate = _WHITESPACE_RE.sub(" ", html.unescape(_TAG_STRIP_RE.sub("", m.group(1)))).strip()
        if len(candidate) > 4:
            return candidate[:200]
    m = _OG_TITLE_RE.search(html_source)
    if m:
        candidate = _WHITESPACE_RE.sub(" ", html.unescape(m.group(1))).strip()
        if len(candidate) > 4:
            return candidate[:200]
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


_CDATA_RE = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.S)


def _clean_feed_text(raw: str) -> str:
    m = _CDATA_RE.search(raw)
    if m:
        text = m.group(1).strip()
    else:
        text = _TAG_STRIP_RE.sub("", raw).strip()
    return html.unescape(text)


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
        postal_code = address.get("postalCode")
        plz = str(postal_code) if isinstance(postal_code, (str, int, float)) and postal_code != "" else None
        locality = address.get("addressLocality")
        city = locality if isinstance(locality, str) and locality else None
    elif isinstance(address, str):
        plz, city = extract_plz_city(address)

    name = node.get("name")
    url = node.get("url")
    return {
        "title": name if isinstance(name, str) else None,
        "url": url if isinstance(url, str) else None,
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
