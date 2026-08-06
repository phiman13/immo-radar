from __future__ import annotations

from app.sources.agents_adapter import AgentSiteSource
from app.sources.base import SourceAdapter
from app.sources.immoscout24_rss import ImmoScout24RSSSource
from app.sources.kleinanzeigen import KleinanzeigenSource
from app.sources.makler_bsimmo import BsImmoSource
from app.sources.makler_riedel import RiedelSource
from app.sources.makler_starnberg_immo import StarnbergImmoSource
from app.sources.tutzing24 import Tutzing24Source

REGISTRY: dict[str, type[SourceAdapter]] = {
    "immoscout24": ImmoScout24RSSSource,
    "kleinanzeigen": KleinanzeigenSource,
    "riedel": RiedelSource,
    "starnberg_bader": StarnbergImmoSource,
    "bs_immo": BsImmoSource,
    "tutzing24": Tutzing24Source,
    "agents": AgentSiteSource,
}


def get_all_adapters() -> list[SourceAdapter]:
    return [cls() for cls in REGISTRY.values()]
