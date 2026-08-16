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
import ipaddress
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

# HER-725: probe_agent() baut daraus eine Netzwerk-Ziel-URL (f"https://{domain}/").
# Aktuell wird Agent.verified_domain nur manuell gesetzt (vertrauenswürdig) --
# sobald Phase 3 (Discovery) dieses Feld aus Websuche-Ergebnissen befüllt, ist
# der Wert nicht mehr vertrauenswürdig, und ein Wert wie "169.254.169.254"
# (Cloud-Metadata) oder "localhost:8001" (das eigene Dashboard) würde den
# Worker-Container gegen sich selbst oder das VPS-interne Netz probieren
# lassen. Erzwingt einen plausiblen, öffentlich adressierbaren Hostnamen --
# strikt als Whitelist (nur Buchstaben/Ziffern/Bindestrich/Punkt, mindestens
# ein Label-Trenner), keine IP-Literale, keine reservierten/internen TLDs.
_HOSTNAME_RE = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))+$")
_RESERVED_TLD_RE = re.compile(r"\.(local|localhost|internal|test|invalid|example|onion)$", re.I)


def validate_domain(domain: str) -> None:
    """Raised ValueError, wenn `domain` kein plausibler, öffentlich
    routbarer Hostname ist -- statt zu proben (Ticket-Vorgabe HER-725)."""
    if not isinstance(domain, str) or not domain.strip():
        raise ValueError(f"invalid domain: {domain!r}")
    candidate = domain.strip().rstrip(".")

    # IP-Literale explizit verbieten (auch öffentliche): ein Makler wird
    # immer über einen echten Domainnamen erreicht, nie über eine nackte IP.
    # Deckt ohne Sonderfall-Logik private/loopback/link-local/reservierte
    # Adressen ab (u.a. 127.0.0.1, 169.254.169.254, 10.0.0.0/8).
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        pass
    else:
        raise ValueError(f"domain darf keine IP-Adresse sein: {domain!r}")

    if not _HOSTNAME_RE.match(candidate):
        raise ValueError(f"kein gültiger Hostname: {domain!r}")
    if _RESERVED_TLD_RE.search(candidate):
        raise ValueError(f"reservierte/interne TLD nicht erlaubt: {domain!r}")


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
    damit robots.can_fetch() und der tatsächliche Abruf nicht auseinanderlaufen).

    Raises ValueError (HER-725), wenn `domain` kein plausibler, öffentlich
    routbarer Hostname ist -- SSRF-Guard, bevor daraus eine Ziel-URL gebaut wird."""
    validate_domain(domain)
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
        out["sitemap_url"] = sm_url
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
