"""Bildet eine klassifizierte Kaskadenstufe (app.agent_probe.classify_stage)
auf das extraction-Schema ab (Vollabdeckung-Spec §5.1) und schreibt das
Ergebnis auf die Agent-Zeile zurück.

Session-Muster identisch zu geocode() in app/geocoding.py: SQLite erlaubt nur
einen offenen Schreiber — wer bereits eine Transaktion offen hält (z.B.
run_source()), übergibt seine Session; onboard_agent() merged/committet dann
nicht selbst, sondern überlässt das dem Aufrufer.

`extraction`-Sparse-Key-Vertrag: Keys sind NUR gesetzt, wenn sie für die
jeweilige Kaskadenstufe zutreffen (z.B. hat `{"method": "vendor:x", "vendor":
"x"}` keine `feed_url`/`sitemap_url`/`needs_browser`-Keys; `{"needs_browser":
True}` für blockierte Agents hat gar keinen `method`-Key). Konsumenten (Phase
2b) MÜSSEN `.get()` verwenden, nie Bracket-Zugriff (`extraction["feed_url"]`)
— das gilt auch für `method` selbst, das bei den terminalen bot-blocked-/
unreachable-Stufen fehlt."""

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

# Stufen, die ein Vendor-/Struktur-/Sitemap-Signal allein von der Startseite
# aus erkennen können, OHNE dass dabei zwingend eine Angebotsseite gefunden
# wurde (anders als "1-feed/openimmo", das feed_url statt listing_url trägt,
# und "5-detail-links", das strukturell nur über eine gefundene Angebotsseite
# überhaupt erreichbar ist).
_REQUIRES_LISTING_URL_STAGES = {"2-vendor", "3-structured", "4-sitemap-objekte"}

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
        return {"method": "sitemap_objekte", "sitemap_url": row.get("sitemap_url")}
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
        listing_url = row.get("listing_url")
        # Vendor-/Struktur-/Sitemap-Signal ohne je gefundene Angebotsseite (weder
        # in diesem Probe noch in einem früheren Onboard-Lauf auf dieser Zeile):
        # Phase 2b hätte nichts zu crawlen -> nicht als auto-harvested zählen,
        # sondern für manuelle Nachschau markieren (Fix 2).
        if stage in _REQUIRES_LISTING_URL_STAGES and not listing_url and not agent.listing_url:
            agent.coverage_status = "needs-manual-watch"
            agent.coverage_reason = (
                f"Kaskadenstufe {stage!r} erkannt, aber keine Angebotsseite "
                "(listing_url) gefunden — Extraktion kann noch nicht laufen."
            )
            agent.extraction = {}
        else:
            agent.extraction = _extraction_for_auto_harvest_stage(stage, row)
            # Nie mit None überschreiben: ein Re-Onboard, das diesmal keine
            # listing_url findet, darf eine zuvor gute nicht stillschweigend
            # nullen (Fix 2).
            if listing_url:
                agent.listing_url = listing_url
            agent.coverage_status = "auto-harvested"
            agent.coverage_reason = None
            # Auflage 2 (finale Whole-Branch-Review Phase 2c): eine
            # Reaktivierung muss auch den Zwei-Läufe-Zähler zurücksetzen --
            # sonst kippt ein manuell reaktivierter Agent mit vorherigem
            # Zählerstand nach einem einzigen weiteren Fehlschlag sofort
            # wieder auf needs-manual-watch zurück (app.sources.agents_adapter
            # erhöht consecutive_empty_runs bei jedem leeren Lauf).
            agent.consecutive_empty_runs = 0
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
        # extra ist derselbe Dict-Objekt wie im Modul-Konstanten _TERMINAL_STAGES
        # (z.B. dasselbe {"needs_browser": True} für jeden bot-blockierten
        # Agent) -- Kopie verhindert, dass eine künftige In-Place-Mutation
        # (agent.extraction["x"] = ...) die Konstante für den ganzen Prozess
        # korrumpiert (Fix 3).
        agent.extraction = dict(extra)

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
