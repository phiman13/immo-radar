"""Tests for notify_new_listing() score-threshold guard."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import app.notify.telegram as telegram_module


def _make_listing(lage_score=None, ai_score=None):
    return SimpleNamespace(
        id=1,
        title="Test Wohnung",
        price_eur=250_000,
        qm=75,
        rooms=3,
        address="Tutzing",
        year_built=2000,
        energie_class=None,
        ai_score=ai_score,
        ai_reasoning=None,
        risk_flags=None,
        source="test",
        url="https://example.com",
        images=[],
        lage_score=lage_score,
    )


def test_notify_skips_below_threshold(monkeypatch):
    """Listing below score threshold must NOT call send_telegram."""
    monkeypatch.setattr(telegram_module, "get_setting", lambda _key: 50.0)

    send_called = []

    async def fake_send(text, image_url=None, buttons=None):
        send_called.append(True)
        return True

    monkeypatch.setattr(telegram_module, "send_telegram", fake_send)

    listing = _make_listing(lage_score=30.0)
    asyncio.run(telegram_module.notify_new_listing(listing))

    assert not send_called, "send_telegram must NOT be called for listings below threshold"


def test_notify_sends_above_threshold(monkeypatch):
    """Listing at or above threshold must call send_telegram."""
    monkeypatch.setattr(telegram_module, "get_setting", lambda _key: 50.0)

    send_called = []

    async def fake_send(text, image_url=None, buttons=None):
        send_called.append(True)
        return True

    monkeypatch.setattr(telegram_module, "send_telegram", fake_send)

    # Patch SessionLocal so DB write doesn't fail in test environment
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr(telegram_module, "SessionLocal", lambda: mock_session)

    listing = _make_listing(lage_score=70.0)
    asyncio.run(telegram_module.notify_new_listing(listing))

    assert send_called, "send_telegram must be called for listings above threshold"


def test_notify_sends_when_score_is_none(monkeypatch):
    """If lage_score is None, threshold check is skipped and notification is sent."""
    monkeypatch.setattr(telegram_module, "get_setting", lambda _key: 50.0)

    send_called = []

    async def fake_send(text, image_url=None, buttons=None):
        send_called.append(True)
        return True

    monkeypatch.setattr(telegram_module, "send_telegram", fake_send)

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr(telegram_module, "SessionLocal", lambda: mock_session)

    listing = _make_listing(lage_score=None)
    asyncio.run(telegram_module.notify_new_listing(listing))

    assert send_called, "send_telegram must be called when lage_score is None"


def test_notify_sends_when_threshold_is_none(monkeypatch):
    """If threshold is None (not configured), no filtering — notification is sent."""
    monkeypatch.setattr(telegram_module, "get_setting", lambda _key: None)

    send_called = []

    async def fake_send(text, image_url=None, buttons=None):
        send_called.append(True)
        return True

    monkeypatch.setattr(telegram_module, "send_telegram", fake_send)

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr(telegram_module, "SessionLocal", lambda: mock_session)

    listing = _make_listing(lage_score=10.0)
    asyncio.run(telegram_module.notify_new_listing(listing))

    assert send_called, "send_telegram must be called when threshold is unconfigured"
