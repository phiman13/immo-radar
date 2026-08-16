"""Tests for GET /api/sources/ and PATCH /api/sources/{id}."""

from __future__ import annotations

import app.db as db_module
from app.db import Agent, Source
from app.web.api.sources import _known_source_names


def test_known_source_names_includes_sources_and_agents(test_db):
    """HER-817: die Discover-Referenzliste muss zur Laufzeit aus der DB
    kommen -- die alte, hartkodierte 8-Einträge-Liste kannte weder später
    manuell hinzugefügte 'suggested'-Quellen noch die per Vollabdeckung-
    Kaskade onboarded Makler (agents-Tabelle)."""
    with db_module.SessionLocal() as session:
        session.add(Source(name="bs_immo", display_name="BS Immo"))
        session.add(
            Source(name="neuer_vorschlag", display_name="Neuer Vorschlag GmbH", source_type="suggested")
        )
        session.add(Agent(name="Loeger Immobilien", coverage_status="auto-harvested"))
        session.commit()

    names = _known_source_names()

    assert "BS Immo" in names
    assert "Neuer Vorschlag GmbH" in names
    assert "Loeger Immobilien" in names


def test_known_source_names_deduplicates_and_sorts(test_db):
    with db_module.SessionLocal() as session:
        session.add(Source(name="dup", display_name="Doppelt"))
        session.add(Agent(name="Doppelt", coverage_status="auto-harvested"))
        session.commit()

    names = _known_source_names()

    assert names.count("Doppelt") == 1
    assert names == sorted(names)


def test_get_sources_seeds_defaults(client, test_db):
    """First call should seed default sources."""
    resp = client.get("/api/sources/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 3  # at least immoscout24, immowelt, kleinanzeigen
    names = [s["name"] for s in data]
    assert "immoscout24" in names


def test_get_sources_idempotent(client, test_db):
    """Second call should not duplicate sources."""
    client.get("/api/sources/")
    resp = client.get("/api/sources/")
    data = resp.json()
    names = [s["name"] for s in data]
    assert names.count("immoscout24") == 1


def test_patch_source_toggle(client, test_db):
    """Should be able to disable a source."""
    sources = client.get("/api/sources/").json()
    source_id = sources[0]["id"]

    resp = client.patch(f"/api/sources/{source_id}", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


def test_patch_source_404(client, test_db):
    resp = client.patch("/api/sources/9999", json={"enabled": True})
    assert resp.status_code == 404
