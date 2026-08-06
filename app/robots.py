"""robots.txt-Respekt (Vollabdeckung-Spec §8: "robots.txt wird pro Lauf
gelesen und respektiert; Disallow -> kein Abruf.").
"""

from __future__ import annotations

from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import httpx

from app.logging_setup import log

USER_AGENT = "immo-radar/0.1 (privates Immobilien-Scouting; Kontakt via immo.herrlich.dev)"


async def is_allowed(client: httpx.AsyncClient, url: str) -> bool:
    """Prüft robots.txt des Hosts von `url`. Kein robots.txt = erlaubt.
    Netzwerkfehler beim Abruf von robots.txt selbst = erlaubt (fail open —
    ein einzelner Hiccup soll den Crawl nicht lahmlegen)."""
    robots_url = urljoin(url, "/robots.txt")
    try:
        r = await client.get(robots_url)
    except httpx.HTTPError as e:
        log.warning("robots.fetch_failed", url=robots_url, error=str(e))
        return True

    parser = RobotFileParser()
    if r.status_code == 200:
        parser.parse(r.text.splitlines())
    else:
        return True

    return parser.can_fetch(USER_AGENT, url)
