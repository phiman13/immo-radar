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
import hashlib
import re
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.agent_cascade_detect import DETAIL_RE, SITEMAP_OBJECT_RE, extract_jsonld_nodes, find_detail_links
from app.agent_field_extract import extract_fields, fields_from_jsonld, merge_fields, parse_feed_items
from app.db import Agent
from app.logging_setup import log
from app.models import PropertyType, RawListing

MAX_DETAIL_PAGES_PER_AGENT = 40
DETAIL_FETCH_DELAY_SECONDS = 0.5

# Change-Gate-Fingerprint (Vollabdeckung-Spec Phase 2c §3): eine bereits
# bekannte Detailseite wird erst nach REFRESH_WINDOW erneut abgerufen, damit
# Preis-/Status-Änderungen (ListingHistory in app.pipeline._upsert()) nicht
# einfrieren, aber der tägliche Crawl nicht jedes Mal alle Objekte neu holt.
REFRESH_WINDOW = timedelta(days=7)

_CONTACT_MARKER_RE = re.compile(r"contact|kontakt", re.I)


def _strip_contact_blocks(html: str) -> str:
    """HER-812: Detailseiten enthalten fast immer auch die Kontaktadresse der
    Agentur (Footer, Kontakt-Widget, Impressum-Block) — extract_plz_city()
    nimmt den ERSTEN PLZ+Ort-Treffer im Gesamttext, und die Büroadresse steht
    im HTML meist VOR der eigentlichen Objektadresse. Real beobachtet
    2026-08-14: fünf verschiedene Objekte auf ubi-immobilien.de landeten
    dadurch alle mit identischen Koordinaten in der DB (Büroadresse statt
    Objektstandort) — eine KI-Bewertung deckte den Fall auf, bei dem das
    tatsächliche Objekt nachweislich in Murnau lag, nicht in Tutzing.

    Entfernt <footer>/<address>-Elemente sowie Elemente, deren class/id
    "contact"/"kontakt" enthält, VOR der Text-Extraktion — generalisierbare
    CMS-Konventionen (verifiziert an einer echten Site), keine
    ortsspezifische Namensliste wie das inzwischen entfernte
    LOCATION_ALLOWLIST_RE (HER-807)."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["footer", "address"]):
        tag.decompose()
    for tag in soup.find_all(True):
        if tag.decomposed:
            continue
        classes = " ".join(tag.get("class") or [])
        tag_id = tag.get("id") or ""
        if _CONTACT_MARKER_RE.search(classes) or _CONTACT_MARKER_RE.search(tag_id):
            tag.decompose()
    return str(soup)


def _source_id(agent_id: int, url: str) -> str:
    """Hash-basiert statt truncated Slug (Review-Fund, Finding 6): eine
    64-Zeichen-Slug-Tail-Truncation kann bei zwei URLs mit langem gemeinsamem
    Suffix (z.B. .../kaufen/exklusive-seevilla-...-tutzing/ vs.
    .../verkauft/exklusive-seevilla-...-tutzing/) kollidieren. Da
    RawListing.address für Agent-Listings immer None ist (siehe
    app.agent_field_extract-Modul-Docstring), ist source_id die GESAMTE
    Dedup-Identität — eine Kollision hier kollabiert zwei echte Objekte auf
    einen Hash."""
    digest = hashlib.sha256(url.encode()).hexdigest()[:16]
    return f"agent-{agent_id}-{digest}"


async def _fetch_detail_listing(agent: Agent, client: httpx.AsyncClient, url: str) -> RawListing | None:
    try:
        r = await client.get(url)
        r.raise_for_status()
    except Exception as e:
        log.warning("agent_handlers.detail_fetch_failed", agent_id=agent.id, url=url, error=str(e))
        return None

    html = _strip_contact_blocks(r.text)
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    fields = extract_fields(html, text)
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


def _urls_to_fetch(all_urls: list[str], known_urls: dict[str, datetime], now: datetime) -> list[str]:
    """Change-Gate-Fingerprint (Vollabdeckung-Spec Phase 2c §3): liefert nur
    URLs, die noch nie gesehen wurden ODER deren letzte Bestätigung länger
    als REFRESH_WINDOW zurückliegt. Canary-Regel: wären es 0 (weil alle
    bekannten URLs frisch sind), wird stattdessen die am längsten nicht
    bestätigte bekannte URL erzwungen -- sonst liefert der Handler in einem
    "alles frisch"-Lauf 0 Objekte, und der Selbsttest in
    app.sources.agents_adapter._passes_self_test() würde fälschlich einen
    Rezept-Bruch auslösen, obwohl nur das Change-Gate gegriffen hat. Das gilt
    AUCH bei nur einer einzigen bekannten URL: app.sources.agents_adapter
    Task 5 (Zwei-Läufe-Zähler) erhöht consecutive_empty_runs bei JEDEM leeren
    Lauf unabhängig von der Ursache und stuft nach zwei Läufen zurück --
    ein Single-Listing-Agent ohne Canary-Erzwingung würde dadurch nach dem
    zweiten "alles frisch"-Lauf fälschlich auf needs-manual-watch
    zurückgestuft, obwohl sein einziges Objekt weiterhin online ist."""
    due = [url for url in all_urls if url not in known_urls or (now - known_urls[url]) >= REFRESH_WINDOW]
    if due:
        return due
    known_among_all = [url for url in all_urls if url in known_urls]
    if not known_among_all:
        return []
    oldest = min(known_among_all, key=lambda u: known_urls[u])
    return [oldest]


async def crawl_and_extract(
    agent: Agent, client: httpx.AsyncClient, known_urls: dict[str, datetime] | None = None
) -> AsyncIterator[RawListing]:
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


async def _discover_sitemap_object_urls(client: httpx.AsyncClient, sitemap_url: str) -> list[str]:
    host = urlparse(sitemap_url).netloc
    try:
        r = await client.get(sitemap_url)
        r.raise_for_status()
    except Exception as e:
        log.warning("agent_handlers.sitemap_fetch_failed", url=sitemap_url, error=str(e))
        return []

    # <loc>-Werte gegen die jeweils abgerufene Sitemap-URL absolutieren (wie
    # Finding 1 für Feed-Links) BEVOR der Host-Vergleich läuft — sonst würde
    # ein relativer <loc>-Eintrag durch urlparse(u).netloc == "" fälschlich
    # als "off-host" verworfen statt korrekt aufgelöst zu werden.
    locs = [urljoin(sitemap_url, u) for u in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", r.text)]
    subs = [
        u for u in locs if u.endswith(".xml") and SITEMAP_OBJECT_RE.search(u) and urlparse(u).netloc == host
    ]
    obj_urls: set[str] = {u for u in locs if DETAIL_RE.search(u) and urlparse(u).netloc == host}
    for i, sub in enumerate(subs[:3]):
        if i > 0:
            await asyncio.sleep(DETAIL_FETCH_DELAY_SECONDS)
        try:
            sr = await client.get(sub)
            sr.raise_for_status()
        except Exception as e:
            log.warning("agent_handlers.sub_sitemap_fetch_failed", url=sub, error=str(e))
            continue
        sub_locs = [urljoin(sub, u) for u in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sr.text)]
        obj_urls.update(u for u in sub_locs if DETAIL_RE.search(u) and urlparse(u).netloc == host)
    return sorted(obj_urls)


async def sitemap_objekte_handler(
    agent: Agent, client: httpx.AsyncClient, known_urls: dict[str, datetime] | None = None
) -> AsyncIterator[RawListing]:
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


_EMPTY_REGEX_FIELDS = {
    "title": None,
    "price_eur": None,
    "qm": None,
    "rooms": None,
    "plz": None,
    "city": None,
    "property_type": None,
}


async def structured_data_handler(
    agent: Agent, client: httpx.AsyncClient, known_urls: dict[str, datetime] | None = None
) -> AsyncIterator[RawListing]:
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

    listing_host = urlparse(agent.listing_url).netloc
    nodes = extract_jsonld_nodes(r.text)
    for node in nodes[:MAX_DETAIL_PAGES_PER_AGENT]:
        jsonld_fields = fields_from_jsonld(node)
        url = jsonld_fields.get("url")
        if not url:
            continue
        url = urljoin(agent.listing_url, url)
        if urlparse(url).netloc != listing_host:
            # Finding 3: robots.txt wird nur einmal für agent.listing_url
            # geprüft (agents_adapter.py, vor Handler-Dispatch) — ein
            # JSON-LD-"url", das absolut auf einen anderen Host zeigt, würde
            # sonst Content abrufen, dessen robots.txt nie konsultiert wurde.
            log.warning("agent_handlers.structured_url_off_host", agent_id=agent.id, url=url)
            continue

        text = ""
        detail_html = ""
        try:
            dr = await client.get(url)
            dr.raise_for_status()
            detail_html = _strip_contact_blocks(dr.text)
            text = BeautifulSoup(detail_html, "html.parser").get_text(" ", strip=True)
        except Exception as e:
            log.warning(
                "agent_handlers.structured_detail_fetch_failed", agent_id=agent.id, url=url, error=str(e)
            )

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


async def feed_adapter_handler(
    agent: Agent, client: httpx.AsyncClient, known_urls: dict[str, datetime] | None = None
) -> AsyncIterator[RawListing]:
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

    feed_host = urlparse(feed_url).netloc
    items = parse_feed_items(r.text)[:MAX_DETAIL_PAGES_PER_AGENT]
    for item in items:
        link = urljoin(feed_url, item["link"])
        if urlparse(link).netloc != feed_host:
            # Finding 3 (Nachtrag): robots.txt wird nur einmal für
            # agent.listing_url geprüft (agents_adapter.py, vor
            # Handler-Dispatch) — ein Feed-<link>, das sich absolut auf einen
            # anderen Host auflöst, würde sonst Content abrufen, dessen
            # robots.txt nie konsultiert wurde.
            log.warning("agent_handlers.feed_link_off_host", agent_id=agent.id, url=link)
            continue
        blob = f"{item['title']} {item['description']}"
        fields = extract_fields("", blob)
        yield RawListing(
            source="agents",
            source_id=_source_id(agent.id, link),
            url=link,
            title=item["title"] or fields["title"],
            description=item["description"][:2000] or None,
            price_eur=fields["price_eur"],
            qm=fields["qm"],
            rooms=fields["rooms"],
            plz=fields["plz"],
            city=fields["city"],
            property_type=fields["property_type"],
        )
