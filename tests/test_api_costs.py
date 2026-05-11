"""Tests for GET /api/system/costs endpoint."""

from __future__ import annotations

from datetime import datetime, timedelta

import app.db as db_module
from app.db import ApiUsage


def seed_api_usage(
    session, ts, model="claude-haiku-4-5-20251001", input_tokens=1000, output_tokens=100, purpose="enrichment"
):
    row = ApiUsage(
        ts=ts, model=model, input_tokens=input_tokens, output_tokens=output_tokens, purpose=purpose
    )
    session.add(row)
    session.commit()
    return row


def test_costs_structure(client):
    now = datetime.utcnow()
    with db_module.SessionLocal() as s:
        seed_api_usage(s, ts=now, input_tokens=1000, output_tokens=100, purpose="enrichment")
        seed_api_usage(s, ts=now - timedelta(hours=2), input_tokens=500, output_tokens=50, purpose="analyze")
        seed_api_usage(
            s, ts=now - timedelta(days=5), input_tokens=800, output_tokens=80, purpose="enrichment"
        )

    r = client.get("/api/system/costs")
    assert r.status_code == 200
    data = r.json()
    assert "last_24h" in data
    assert "last_7d" in data
    assert "breakdown_24h" in data
    assert data["last_24h"]["calls"] == 2
    assert data["last_7d"]["calls"] == 3


def test_costs_usd_positive(client):
    now = datetime.utcnow()
    with db_module.SessionLocal() as s:
        seed_api_usage(s, ts=now, input_tokens=1000, output_tokens=100, purpose="enrichment")
        seed_api_usage(s, ts=now - timedelta(hours=2), input_tokens=500, output_tokens=50, purpose="analyze")
        seed_api_usage(
            s, ts=now - timedelta(days=5), input_tokens=800, output_tokens=80, purpose="enrichment"
        )

    r = client.get("/api/system/costs")
    data = r.json()
    assert data["last_24h"]["usd"] > 0
    assert data["last_7d"]["usd"] >= data["last_24h"]["usd"]


def test_costs_empty(client):
    r = client.get("/api/system/costs")
    assert r.status_code == 200
    data = r.json()
    assert data["last_24h"]["calls"] == 0
    assert data["last_24h"]["usd"] == 0.0
    assert data["last_7d"]["calls"] == 0
