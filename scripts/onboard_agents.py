"""Onboarding für Makler-Sites: probt agent.verified_domain, klassifiziert
die Kaskadenstufe und schreibt das Ergebnis zurück (Vollabdeckung-Spec §4.1).

Manueller Trigger, solange Phase 3 (Discovery) und Phase 4 (Dashboard-Tab)
noch nicht existieren.

Usage:
    python -m scripts.onboard_agents                 # alle unknown-Agents
    python -m scripts.onboard_agents --agent-id 3     # ein einzelner Agent
"""

from __future__ import annotations

import argparse
import asyncio

import httpx
from sqlalchemy import select

import app.db as db_module
from app.agent_onboarding import onboard_agent
from app.db import Agent
from app.logging_setup import configure_logging
from app.robots import USER_AGENT


async def _agent_ids_to_onboard(agent_id: int | None) -> list[int]:
    with db_module.SessionLocal() as session:
        if agent_id is not None:
            return [agent_id]
        stmt = select(Agent.id).where(Agent.verified_domain.is_not(None), Agent.coverage_status == "unknown")
        return list(session.scalars(stmt))


async def main(agent_id: int | None) -> None:
    configure_logging()
    ids = await _agent_ids_to_onboard(agent_id)
    if not ids:
        print("Keine Agents zum Onboarden (verified_domain gesetzt + coverage_status == 'unknown').")
        return

    print(f"Onboarding {len(ids)} Agent(s) …")
    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "de-DE,de;q=0.9"},
    ) as client:
        for aid in ids:
            agent = await onboard_agent(aid, client)
            print(f"  [{agent.id:>4}] {agent.name:<30} {agent.coverage_status:<20} {agent.extraction}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent-id", type=int, default=None)
    args = ap.parse_args()
    asyncio.run(main(args.agent_id))
