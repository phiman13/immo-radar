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
