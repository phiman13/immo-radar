"""Phase-0-Vermessung: Was steckt technisch hinter Makler-Websites?

Misst pro Site, welche Extraktions-Strategie greifen würde — Feed, Vendor-Template,
strukturierte Daten, Sitemap oder (als letzte Stufe) ein gelerntes Selektor-Rezept.
Das Ergebnis entscheidet, welche Kaskadenstufen überhaupt gebaut werden.

Read-only, höflich: eigener User-Agent, robots.txt wird ausgewertet, wenige Abrufe
pro Host, gedrosselte Parallelität.

    python -m scripts.probe_agent_sites            # alle Domains
    python -m scripts.probe_agent_sites --limit 5  # Schnelltest
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

UA = "immo-radar-probe/0.1 (privates Immobilien-Scouting; Kontakt via immo.herrlich.dev)"
HEADERS = {"User-Agent": UA, "Accept-Language": "de-DE,de;q=0.9"}

# Stichprobe: Makler im Suchgebiet (Fünfseenland) + überregionale mit Seeobjekten.
DOMAINS = [
    # Tutzing / Kerngebiet
    "loeger-immobilien.de",
    "graef-immo.de",
    "locate-immobilien.com",
    "torres-immobilien.de",
    "see-residenz.de",
    "kpcimmobilien.de",
    # Starnberg / Pöcking / Feldafing / Berg
    "heidinger-immobilien.de",
    "jannikzimmer.com",
    "starnbergersee-immobilien.de",
    "immobilienmakler-starnberg-blasig.de",
    "weichselgartner-immo.de",
    "schlossberger-immobilien.de",
    "bs-immo.de",
    # Ammersee / Herrsching / Andechs
    "zillerimmobilien.de",
    "windisch-immobilien.de",
    "sedlmayr-immo.de",
    "akurat.net",
    "citigrund.de",
    # Weilheim / Seeshaupt / Bernried / Penzberg
    "liebhardt-immobilien.de",
    # Überregional / München mit Seeobjekten
    "riedel-immobilien.de",
    "ubi-immobilien.de",
    "aigner-immobilien.de",
    "rogers-immobilien.de",
    "alpenimmobilien.de",
    "suedhausbau.de",
    "freitag.immobilien",
    # Franchise-Netze
    "von-poll.com",
    "engelvoelkers.com",
    "dahlercompany.com",
]

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


def find_detail_links(html: str, base: str) -> tuple[int, list[str]]:
    """Objektlinks strukturell finden: die größte Gruppe gleichförmiger Links.

    Wortlisten scheitern an Legacy-CMS (`index.php4?cmd=searchDetails&cursor=7`)
    und an fremdsprachigen Slugs. Die Struktur trägt weiter: eine Angebotsseite
    verlinkt viele Objekte nach identischem Muster, während Navigationslinks
    einzeln und uneinheitlich sind.
    """
    soup = BeautifulSoup(html, "html.parser")
    host = urlparse(base).netloc
    groups: dict[str, set[str]] = {}
    for a in soup.find_all("a", href=True):
        full = urljoin(base, a["href"]).split("#")[0]
        if urlparse(full).netloc != host or full.rstrip("/") == base.rstrip("/"):
            continue
        groups.setdefault(link_shape(full), set()).add(full)

    # Kandidaten: Gruppen mit mehreren gleichförmigen Links. Navigation und
    # Footer erzeugen kleine, uneinheitliche Gruppen und fallen so heraus.
    best: tuple[int, list[str]] = (0, [])
    for shape, urls in groups.items():
        if len(urls) < 3:
            continue
        score = len(urls)
        if DETAIL_RE.search(next(iter(urls))):
            score *= 2  # sprechender Pfad bestätigt zusätzlich
        if re.search(r"(kontakt|impressum|datenschutz|team|news|blog)", shape, re.I):
            continue
        if score > best[0]:
            best = (score, sorted(urls))
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
            PRICE_RE.search(title)
            or AREA_RE.search(title)
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


async def fetch(client: httpx.AsyncClient, url: str) -> httpx.Response | None:
    try:
        r = await client.get(url)
        return r
    except Exception:
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
        # Kurze Pfade und sprechende Linktexte bevorzugen. Dateiendungen
        # abschneiden, sonst verliert /Angebote.htm gegen /angebote/.
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


async def probe(domain: str, sem: asyncio.Semaphore) -> dict:
    out: dict = {"domain": domain, "reachable": False}
    async with sem:
        async with httpx.AsyncClient(headers=HEADERS, timeout=25.0, follow_redirects=True) as client:
            root = f"https://{domain}"
            r = await fetch(client, root)
            if r is None:  # DNS/TLS-Fehler: einmal mit www. gegenprüfen
                root = f"https://www.{domain}"
                r = await fetch(client, root)
            if r is None or r.status_code >= 400:
                # 403/429 = aktiv geblockt (braucht echten Browser), sonst tot
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

            # robots.txt
            rp_txt = await fetch(client, urljoin(root, "/robots.txt"))
            sitemap_urls: list[str] = []
            if rp_txt is not None and rp_txt.status_code == 200:
                out["robots"] = True
                sitemap_urls = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", rp_txt.text)
                rp = RobotFileParser()
                rp.parse(rp_txt.text.splitlines())
                out["robots_allows_root"] = rp.can_fetch(UA, root)
            else:
                out["robots"] = False
                out["robots_allows_root"] = True  # kein robots.txt = kein Verbot

            # Sitemap: Index auflösen und Unter-Sitemaps mit Objekt-Post-Type
            # gezielt auswerten — dort stehen die Objekt-URLs vollständig drin.
            if not sitemap_urls:
                sitemap_urls = [urljoin(root, "/sitemap.xml"), urljoin(root, "/wp-sitemap.xml")]
            out["sitemap"] = False
            out["sitemap_object_urls"] = 0
            for sm_url in sitemap_urls[:2]:
                sm = await fetch(client, sm_url)
                if sm is None or sm.status_code != 200 or "<" not in sm.text[:200]:
                    continue
                out["sitemap"] = True
                locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sm.text)
                out["sitemap_entries"] = len(locs)
                out["sitemap_listing_like"] = sum(1 for u in locs if LISTING_HINTS.search(u))

                # Unter-Sitemaps, deren *Name* auf Objekte hindeutet
                subs = [u for u in locs if u.endswith(".xml") and SITEMAP_OBJECT_RE.search(u)]
                obj_urls: set[str] = set()
                for sub in subs[:3]:
                    sr = await fetch(client, sub)
                    if sr is None or sr.status_code != 200:
                        continue
                    for u in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sr.text):
                        if DETAIL_RE.search(u):
                            obj_urls.add(u)
                # Fallback: Objekt-URLs direkt im Haupt-Index
                obj_urls.update(u for u in locs if DETAIL_RE.search(u))
                out["sitemap_object_urls"] = len(obj_urls)
                out["sitemap_object_sample"] = sorted(obj_urls)[:2]
                break

            # RSS/Atom
            soup_home = BeautifulSoup(home, "html.parser")
            feeds = [
                urljoin(root, link["href"])
                for link in soup_home.find_all("link", rel=lambda v: v and "alternate" in v)
                if link.get("type", "").lower() in ("application/rss+xml", "application/atom+xml")
                and link.get("href")
            ]
            # Feeds nicht nur finden, sondern auf Immobilien-Inhalt prüfen
            checked = [await validate_feed(client, f) for f in feeds[:2]]
            out["feeds"] = checked
            out["has_immo_feed"] = any(f.get("immo_like") for f in checked)

            # OpenImmo: Erwähnung im Markup vs. tatsächlich abrufbare XML
            out["openimmo_hint"] = bool(re.search(r"openimmo", home + header_blob, re.I))
            out["openimmo_url"] = await find_openimmo(client, root)

            # CMS / Vendor
            gen = soup_home.find("meta", attrs={"name": "generator"})
            out["generator"] = gen.get("content", "")[:80] if gen else ""
            out["wordpress"] = bool(re.search(r"wp-content|wp-json|wordpress", home, re.I))

            # Angebotsseite finden und dort erneut messen
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

            # Kernfrage: Verlinkt die Angebotsseite überhaupt Objekt-Detailseiten?
            if listing_html:
                n, sample = find_detail_links(listing_html, listing_url)
                out["detail_links"] = n
                out["detail_sample"] = sample
            else:
                out["detail_links"] = 0

            await asyncio.sleep(1.0)  # Höflichkeitspause pro Host
    return out


def classify(row: dict) -> str:
    """Welche Kaskadenstufe würde hier tatsächlich greifen?

    Bewusst streng: ein vorhandener Feed zählt nur, wenn er Immobilien enthält,
    und JSON-LD nur bei immobilienspezifischen Typen. Ein WordPress-Blogfeed
    oder ein `WebPage`-Marker ist kein Extraktionsweg.
    """
    if not row.get("reachable"):
        return "blocked (braucht Browser)" if row.get("blocked") else "unreachable"
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


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="docs/superpowers/phase0-probe.json")
    args = ap.parse_args()

    domains = DOMAINS[: args.limit] if args.limit else DOMAINS
    sem = asyncio.Semaphore(5)
    rows = await asyncio.gather(*(probe(d, sem) for d in domains))

    for row in rows:
        row["stage"] = classify(row)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(rows, indent=2, ensure_ascii=False))

    # Tabelle
    print(f"\n{'Domain':<38} {'Stufe':<22} {'Vendor':<20} {'Detail':>6} {'Preise':>6} {'m²':>5}")
    print("-" * 102)
    for row in sorted(rows, key=lambda r: r["stage"]):
        sig = row.get("signals", {})
        print(
            f"{row['domain']:<38} {row['stage']:<22} "
            f"{','.join(row.get('vendors', []))[:19]:<20} "
            f"{row.get('detail_links', 0):>6} {sig.get('prices', 0):>6} {sig.get('areas', 0):>5}"
        )

    # Aggregat
    print("\n=== Verteilung ===")
    from collections import Counter

    for stage, n in Counter(r["stage"] for r in rows).most_common():
        print(f"  {stage:<26} {n:>3}  ({n / len(rows) * 100:.0f} %)")

    vend = Counter(v for r in rows for v in r.get("vendors", []))
    print("\n=== Vendor-Verbreitung ===")
    for name, n in vend.most_common():
        print(f"  {name:<26} {n:>3}")
    if not vend:
        print("  (keine Fingerprints getroffen)")

    reach = sum(1 for r in rows if r.get("reachable"))
    print(f"\nErreichbar: {reach}/{len(rows)}   Ergebnis: {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
