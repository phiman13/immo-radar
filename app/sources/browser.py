from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from playwright.async_api import async_playwright

from app.logging_setup import log


@asynccontextmanager
async def _browser():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/130.0 Safari/537.36"
            ),
            locale="de-DE",
            viewport={"width": 1440, "height": 900},
        )
        try:
            yield context
        finally:
            await context.close()
            await browser.close()


async def fetch_html(url: str, wait_selector: str | None = None, timeout_ms: int = 30000) -> str:
    """Fetch HTML via headless Chromium. Use sparingly — slower than httpx."""
    async with _browser() as ctx:
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=10000)
                except Exception:
                    log.debug("browser.wait_selector_timeout", url=url, selector=wait_selector)
            html = await page.content()
            return html
        finally:
            await page.close()


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
