"""Tests für app.sources.browser — Playwright-Wrapper für JS-gerenderte/
WAF-blockierte Makler-Sites (Vollabdeckung-Spec Phase 2c §5). Kein echter
Chromium-Start: async_playwright wird komplett gemockt."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.sources.browser import browser_session


def _mock_playwright_stack():
    """Baut die verschachtelte Mock-Kette nach, die async_playwright()
    normalerweise liefert: p.chromium.launch() -> browser,
    browser.new_context() -> context, context.new_page() -> page."""
    page = AsyncMock()
    page.goto = AsyncMock()
    page.close = AsyncMock()

    context = AsyncMock()
    context.new_page = AsyncMock(return_value=page)
    context.close = AsyncMock()

    browser = AsyncMock()
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock()

    chromium = AsyncMock()
    chromium.launch = AsyncMock(return_value=browser)

    playwright_instance = MagicMock()
    playwright_instance.chromium = chromium

    playwright_cm = AsyncMock()
    playwright_cm.__aenter__ = AsyncMock(return_value=playwright_instance)
    playwright_cm.__aexit__ = AsyncMock(return_value=False)

    return playwright_cm, browser, context, page


@pytest.mark.asyncio
async def test_browser_session_reuses_one_browser_for_multiple_fetches():
    playwright_cm, browser, context, page = _mock_playwright_stack()
    page.content = AsyncMock(side_effect=["<html>eins</html>", "<html>zwei</html>"])

    with patch("app.sources.browser.async_playwright", return_value=playwright_cm):
        async with browser_session() as fetch:
            html1 = await fetch("https://x.de/a")
            html2 = await fetch("https://x.de/b")

    assert html1 == "<html>eins</html>"
    assert html2 == "<html>zwei</html>"
    assert browser.new_context.await_count == 1  # ein Context für beide Fetches
    assert context.new_page.await_count == 2  # aber eine Page pro URL


@pytest.mark.asyncio
async def test_browser_session_closes_browser_after_context_exits():
    playwright_cm, browser, context, page = _mock_playwright_stack()
    page.content = AsyncMock(return_value="<html></html>")

    with patch("app.sources.browser.async_playwright", return_value=playwright_cm):
        async with browser_session() as fetch:
            await fetch("https://x.de/a")

    context.close.assert_awaited_once()
    browser.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_browser_session_page_failure_does_not_abort_session():
    playwright_cm, browser, context, page = _mock_playwright_stack()
    page.goto = AsyncMock(side_effect=[Exception("timeout"), None])
    page.content = AsyncMock(return_value="<html>zwei</html>")

    with patch("app.sources.browser.async_playwright", return_value=playwright_cm):
        async with browser_session() as fetch:
            with pytest.raises(Exception, match="timeout"):
                await fetch("https://x.de/a")
            html2 = await fetch("https://x.de/b")

    assert html2 == "<html>zwei</html>"
    context.close.assert_awaited_once()
    browser.close.assert_awaited_once()
