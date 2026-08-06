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
from urllib.parse import urljoin
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
from app.agent_probe import fetch, find_listing_url, find_openimmo, validate_feed
from app.robots import USER_AGENT

HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "de-DE,de;q=0.9"}

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
    "see-immo.de",
    "remax-starnberg.com",
    "starnberger-immobilien.de",
    "bpl-immobilien.de",
    "nikki-livings.de",
    "i-m-living.de",
    "immobilien-sis.com",
    "funer-immobilien-starnberg.de",
    "imothek.de",
    "immobilien.vr-starnberg-zugspitze.de",
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
                out["robots_allows_root"] = rp.can_fetch(USER_AGENT, root)
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
