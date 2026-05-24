from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# Wir importieren die Funktion, nachdem sie in Task 1 implementiert ist
from app.web.api.sources import _url_reachable


@pytest.mark.asyncio
async def test_url_reachable_200():
    """HEAD 200 → reachable."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("app.web.api.sources.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.head = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        result = await _url_reachable("https://example.de")
        assert result is True


@pytest.mark.asyncio
async def test_url_reachable_head_404_get_200():
    """HEAD 404 → retry GET → 200 → reachable."""
    head_resp = MagicMock()
    head_resp.status_code = 404
    get_resp = MagicMock()
    get_resp.status_code = 200

    with patch("app.web.api.sources.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.head = AsyncMock(return_value=head_resp)
        mock_client.get = AsyncMock(return_value=get_resp)
        mock_client_cls.return_value = mock_client

        result = await _url_reachable("https://example.de")
        assert result is True


@pytest.mark.asyncio
async def test_url_reachable_both_fail():
    """HEAD 404 → GET 404 → not reachable."""
    fail_resp = MagicMock()
    fail_resp.status_code = 404

    with patch("app.web.api.sources.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.head = AsyncMock(return_value=fail_resp)
        mock_client.get = AsyncMock(return_value=fail_resp)
        mock_client_cls.return_value = mock_client

        result = await _url_reachable("https://ghost-site.de")
        assert result is False


@pytest.mark.asyncio
async def test_url_reachable_connection_error():
    """Netzwerkfehler → not reachable (kein Exception-Propagation)."""
    with patch("app.web.api.sources.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.head = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_client_cls.return_value = mock_client

        result = await _url_reachable("https://nowhere.invalid")
        assert result is False
