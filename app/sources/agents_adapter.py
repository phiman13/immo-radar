"""Generischer, DB-getriebener Adapter für die agents-Tabelle.

Tritt NEBEN die statische REGISTRY, ersetzt sie nicht (Vollabdeckung-Spec
§5.3). Verteilt jede agents-Zeile mit coverage_status == "auto-harvested" an
die in EXTRACTION_METHODS registrierte Methode. EXTRACTION_METHODS ist in
Phase 1 bewusst leer — Phase 2 registriert hier die acht Vendor-Adapter und
die strukturelle Detail-Link-Erkennung. Eine leere Registry bedeutet, dass
fetch() nichts liefert, was bis Phase 2 korrekt ist.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import datetime

import httpx
from sqlalchemy import select

import app.db as db_module
from app.db import Agent
from app.logging_setup import log
from app.models import RawListing
from app.robots import is_allowed
from app.sources.base import SourceAdapter

ExtractionMethod = Callable[[Agent, httpx.AsyncClient], AsyncIterator[RawListing]]

EXTRACTION_METHODS: dict[str, ExtractionMethod] = {}


class AgentSiteSource(SourceAdapter):
    """Ein Adapter-Objekt repräsentiert alle Makler-eigenen Websites
    zusammen — jede agents-Zeile wird einzeln isoliert verarbeitet, ein
    fehlschlagender Makler bricht nie den Gesamtlauf ab (Spec §7)."""

    name = "agents"

    async def fetch(self) -> AsyncIterator[RawListing]:
        assert self.client is not None
        with db_module.SessionLocal() as session:
            agents = list(session.scalars(select(Agent).where(Agent.coverage_status == "auto-harvested")))

        for agent in agents:
            method_name = (agent.extraction or {}).get("method")
            if not method_name:
                log.warning("agents_adapter.no_method", agent_id=agent.id, agent_name=agent.name)
                continue
            handler = EXTRACTION_METHODS.get(method_name)
            if handler is None:
                log.warning("agents_adapter.unknown_method", agent_id=agent.id, method=method_name)
                continue
            if not agent.listing_url:
                log.warning("agents_adapter.no_listing_url", agent_id=agent.id)
                continue

            try:
                if not await is_allowed(self.client, agent.listing_url):
                    log.info("agents_adapter.robots_disallowed", agent_id=agent.id, url=agent.listing_url)
                    with db_module.SessionLocal() as session:
                        db_agent = session.get(Agent, agent.id)
                        if db_agent is not None:
                            db_agent.coverage_status = "robots-disallowed"
                            db_agent.coverage_reason = f"robots.txt verbietet Zugriff auf {agent.listing_url}"
                            db_agent.last_checked = datetime.utcnow()
                            session.commit()
                    continue

                async for raw in handler(agent, self.client):
                    yield raw
            except Exception as e:
                log.error(
                    "agents_adapter.agent_failed",
                    agent_id=agent.id,
                    agent_name=agent.name,
                    error=str(e),
                )
                continue
