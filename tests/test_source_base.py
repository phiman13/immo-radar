"""Regressionstest: SourceAdapter setzt einen ehrlichen, identifizierenden
User-Agent statt eines Chrome-Fakes (Vollabdeckung-Spec §8)."""

from __future__ import annotations

import pytest

from app.sources.base import SourceAdapter


class _DummySource(SourceAdapter):
    name = "dummy"

    async def fetch(self):
        return
        yield  # pragma: no cover


@pytest.mark.asyncio
async def test_user_agent_is_honest_not_a_chrome_fake():
    async with _DummySource() as adapter:
        ua = adapter.client.headers["User-Agent"]
        assert "immo-radar" in ua
        assert "Chrome" not in ua
        assert "Macintosh" not in ua
        assert "herrlich.dev" in ua  # Kontakt-URL laut Spec §8 Pflicht
