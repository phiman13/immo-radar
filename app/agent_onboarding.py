"""Bildet eine klassifizierte Kaskadenstufe (app.agent_probe.classify_stage)
auf das extraction-Schema ab (Vollabdeckung-Spec §5.1) und schreibt das
Ergebnis auf die Agent-Zeile zurück.

Session-Muster identisch zu geocode() in app/geocoding.py: SQLite erlaubt nur
einen offenen Schreiber — wer bereits eine Transaktion offen hält (z.B.
run_source()), übergibt seine Session; onboard_agent() merged/committet dann
nicht selbst, sondern überlässt das dem Aufrufer."""

from __future__ import annotations

from datetime import datetime

import httpx

import app.db as db_module
from app.agent_probe import classify_stage, probe_agent
from app.db import Agent

_AUTO_HARVEST_STAGES = {
    "1-feed/openimmo",
    "2-vendor",
    "3-structured",
    "4-sitemap-objekte",
    "5-detail-links",
}

# stage -> (coverage_status, coverage_reason, zusätzliche extraction-Felder)
_TERMINAL_STAGES: dict[str, tuple[str, str, dict]] = {
    "6-recipe (HTML hat Daten)": (
        "needs-manual-watch",
        "HTML enthält Preis-/Flächenangaben, aber kein automatischer "
        "Erkennungsweg — wartet auf das LLM-Rezept (Phase 2, Stufe learned_recipe).",
        {},
    ),
    "7-js-shell/unklar": (
        "needs-manual-watch",
        "Keine Objektdaten im statischen HTML erkennbar — vermutlich JS-Shell oder unbekannte Struktur.",
        {},
    ),
    "unreachable": (
        "unreachable",
        "Site nicht erreichbar (DNS/TLS-Fehler oder HTTP-Fehlerstatus).",
        {},
    ),
    "blocked (braucht Browser)": (
        "bot-blocked",
        "HTTP 401/403/429 — Bot-Schutz vermutet, braucht Playwright-Rendering (Phase 2c).",
        {"needs_browser": True},
    ),
}


def _extraction_for_auto_harvest_stage(stage: str, row: dict) -> dict:
    if stage == "1-feed/openimmo":
        feed_url = row.get("openimmo_url")
        if not feed_url:
            feed_url = next((f["url"] for f in row.get("feeds", []) if f.get("immo_like")), None)
        return {"method": "feed_adapter", "feed_url": feed_url}
    if stage == "2-vendor":
        vendor = row["vendors"][0]
        return {"method": f"vendor:{vendor}", "vendor": vendor}
    if stage == "3-structured":
        return {"method": "structured_data"}
    if stage == "4-sitemap-objekte":
        sample = row.get("sitemap_object_sample") or []
        return {"method": "sitemap_objekte", "sitemap_url": sample[0] if sample else None}
    if stage == "5-detail-links":
        return {"method": "detail_links"}
    raise ValueError(f"kein auto-harvest-Mapping für Stufe {stage!r}")


async def _onboard(agent_id: int, client: httpx.AsyncClient, session) -> Agent:
    agent = session.get(Agent, agent_id)
    if agent is None:
        raise ValueError(f"agent {agent_id} not found")
    if not agent.verified_domain:
        raise ValueError(f"agent {agent_id} has no verified_domain")

    row = await probe_agent(agent.verified_domain, client)
    stage = classify_stage(row)
    agent.last_checked = datetime.utcnow()

    if row.get("reachable"):
        agent.robots_status = "disallowed" if row.get("robots_allows_root") is False else "allowed"
    else:
        agent.robots_status = None

    if stage in _AUTO_HARVEST_STAGES:
        agent.extraction = _extraction_for_auto_harvest_stage(stage, row)
        agent.listing_url = row.get("listing_url")
        agent.coverage_status = "auto-harvested"
        agent.coverage_reason = None
    elif stage == "robots-disallowed":
        agent.coverage_status = "robots-disallowed"
        agent.coverage_reason = "robots.txt verbietet den Zugriff auf die Startseite."
        agent.extraction = {}
    else:
        status, reason, extra = _TERMINAL_STAGES.get(
            stage, ("needs-manual-watch", f"Unbekannte Kaskadenstufe: {stage}", {})
        )
        agent.coverage_status = status
        agent.coverage_reason = reason
        agent.extraction = extra

    return agent


async def onboard_agent(agent_id: int, client: httpx.AsyncClient, session=None) -> Agent:
    """Probt agent.verified_domain, klassifiziert die Kaskadenstufe und
    schreibt extraction/listing_url/coverage_status/coverage_reason zurück.

    `session`: optionale Session des Aufrufers. Ohne Angabe öffnet und
    committet onboard_agent() selbst; mit übergebener Session bleibt das
    Committen beim Aufrufer (SQLite-Single-Writer, siehe Modul-Docstring)."""
    if session is not None:
        return await _onboard(agent_id, client, session)
    with db_module.SessionLocal() as own_session:
        agent = await _onboard(agent_id, client, own_session)
        own_session.commit()
        return agent
