"""Statisches HTML vs. gerenderte Seite — bringt ein echter Browser die Objekte?

Der Phase-0-Prober misst nur, was httpx sieht. Viele Makler-Sites laden ihre
Objektliste per JavaScript nach; dort meldet der statische Abruf fälschlich
"keine Objekte". Dieses Skript ruft dieselbe Angebotsseite zweimal ab — einmal
mit httpx, einmal mit Playwright — und vergleicht, was jeweils sichtbar wird.

    python -m scripts.probe_rendered                     # Referenz-Sites
    python -m scripts.probe_rendered https://example.de  # eigene URL
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from scripts.probe_agent_sites import (
    AREA_RE,
    DETAIL_RE,
    HEADERS,
    PRICE_RE,
    detect_vendors,
    find_listing_url,
)

# Vom Nutzer benannte Referenz-Makler der Region
REFERENCE = [
    "https://www.starnbergersee-immobilien.de/",
    "https://loeger-immobilien.de/",
    "https://www.riedel-immobilien.de/",
    "https://www.ubi-immobilien.de/",
    "https://www.locate-immobilien.com/",
]


def measure(html: str, base: str) -> dict:
    """Was ist in diesem HTML an Objektdaten sichtbar?"""
    soup = BeautifulSoup(html, "html.parser")
    host = urlparse(base).netloc
    links = set()
    for a in soup.find_all("a", href=True):
        full = urljoin(base, a["href"])
        if urlparse(full).netloc == host and DETAIL_RE.search(full):
            links.add(full.split("#")[0])
    links.discard(base.split("#")[0])
    return {
        "detail_links": len(links),
        "prices": len(PRICE_RE.findall(html)),
        "areas": len(AREA_RE.findall(html)),
        "kb": len(html) // 1024,
        "sample": sorted(links)[:3],
    }


async def static_get(url: str) -> tuple[str, str] | None:
    async with httpx.AsyncClient(headers=HEADERS, timeout=25.0, follow_redirects=True) as c:
        try:
            r = await c.get(url)
        except Exception:
            return None
        if r.status_code >= 400:
            return None
        return r.text, str(r.url)


async def rendered_get(browser, url: str) -> tuple[str, str] | None:
    """Echter Browser: JS ausführen, Lazy-Loading anstoßen, dann HTML lesen."""
    ctx = await browser.new_context(
        locale="de-DE",
        viewport={"width": 1440, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
        ),
    )
    page = await ctx.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        # Cookie-Banner wegklicken — sonst bleibt der Inhalt oft verdeckt
        for label in ("Alle akzeptieren", "Akzeptieren", "Zustimmen", "Einverstanden", "OK"):
            try:
                btn = page.get_by_role("button", name=re.compile(label, re.I)).first
                if await btn.is_visible(timeout=800):
                    await btn.click(timeout=1500)
                    break
            except Exception:
                continue
        await page.mouse.wheel(0, 4000)
        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        return await page.content(), page.url
    except Exception:
        return None
    finally:
        await ctx.close()


async def probe_one(browser, root: str) -> dict:
    out: dict = {"root": root}

    # Angebotsseite bestimmen — erst statisch, sonst gerendert
    home = await static_get(root)
    listing = None
    if home:
        listing = find_listing_url(home[0], home[1])
    if not listing:
        r = await rendered_get(browser, root)
        if r:
            listing = find_listing_url(r[0], r[1])
    if not listing:
        listing = root
    out["listing_url"] = listing

    s = await static_get(listing)
    out["static"] = measure(*s) if s else {"error": "blocked/unreachable"}

    d = await rendered_get(browser, listing)
    out["rendered"] = measure(*d) if d else {"error": "render failed"}

    blob = (s[0] if s else "") + " " + (d[0] if d else "")
    out["vendors"] = detect_vendors(blob)
    return out


async def main() -> None:
    urls = sys.argv[1:] or REFERENCE
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        rows = []
        for u in urls:
            rows.append(await probe_one(browser, u))
            await asyncio.sleep(1.0)
        await browser.close()

    print(f"\n{'Site':<34} {'Quelle':<10} {'Objekte':>8} {'Preise':>7} {'m²':>5} {'KB':>5}")
    print("-" * 76)
    for row in rows:
        host = urlparse(row["root"]).netloc.replace("www.", "")
        for mode in ("static", "rendered"):
            m = row[mode]
            if "error" in m:
                print(f"{host if mode == 'static' else '':<34} {mode:<10} {m['error']:>8}")
            else:
                print(
                    f"{host if mode == 'static' else '':<34} {mode:<10} "
                    f"{m['detail_links']:>8} {m['prices']:>7} {m['areas']:>5} {m['kb']:>5}"
                )
        v = ",".join(row["vendors"]) or "-"
        print(f"{'':<34} {'vendor':<10} {v}")
        sample = row["rendered"].get("sample") or row["static"].get("sample") or []
        for s in sample[:2]:
            print(f"{'':<34} {'→':<10} {s[:76]}")
        print()

    Path("docs/superpowers/phase0-rendered.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    gain = sum(1 for r in rows if r["rendered"].get("detail_links", 0) > r["static"].get("detail_links", 0))
    print(f"Sites, bei denen Rendering mehr Objekte sichtbar macht: {gain}/{len(rows)}")


if __name__ == "__main__":
    asyncio.run(main())
