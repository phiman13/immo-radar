"""Tests für app.robots — robots.txt-Respekt vor dem Crawlen einer Makler-Site."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.robots import is_allowed


@pytest.mark.asyncio
async def test_is_allowed_no_robots_txt_means_allowed():
    """404 auf robots.txt = kein Verbot vorhanden = erlaubt."""
    client = AsyncMock()
    resp = MagicMock()
    resp.status_code = 404
    client.get = AsyncMock(return_value=resp)

    assert await is_allowed(client, "https://example.de/angebote/") is True


@pytest.mark.asyncio
async def test_is_allowed_disallow_all():
    client = AsyncMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.text = "User-agent: *\nDisallow: /"
    client.get = AsyncMock(return_value=resp)

    assert await is_allowed(client, "https://example.de/angebote/") is False


@pytest.mark.asyncio
async def test_is_allowed_disallow_specific_path_only():
    client = AsyncMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.text = "User-agent: *\nDisallow: /admin/"
    client.get = AsyncMock(return_value=resp)

    assert await is_allowed(client, "https://example.de/angebote/") is True


@pytest.mark.asyncio
async def test_is_allowed_fetches_robots_txt_from_host_root():
    client = AsyncMock()
    resp = MagicMock()
    resp.status_code = 404
    client.get = AsyncMock(return_value=resp)

    await is_allowed(client, "https://example.de/angebote/liste?seite=2")

    client.get.assert_awaited_once_with("https://example.de/robots.txt")


@pytest.mark.asyncio
async def test_is_allowed_network_error_fails_open():
    """Ein Netzwerkfehler beim robots.txt-Abruf darf den Crawl nicht
    blockieren — konservativ genug ist bereits, dass jede Detailseite später
    ihre eigene Fehlerbehandlung hat."""
    client = AsyncMock()
    client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))

    assert await is_allowed(client, "https://example.de/angebote/") is True
