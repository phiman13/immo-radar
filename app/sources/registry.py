from __future__ import annotations

import app.db as db_module
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
    """Instanziiert jeden REGISTRY-Adapter, dessen `sources`-DB-Zeile nicht
    explizit `enabled=False` gesetzt hat (HER-805: der "Aktiv"-Schalter im
    Dashboard schrieb dieses Feld bisher nur, ohne dass irgendein Crawl-Code
    es je gelesen hätte). Ein REGISTRY-Eintrag ohne zugehörige `sources`-Zeile
    (z.B. `agents`, das über eine eigene Coverage-Tabelle läuft) gilt als
    aktiv — nur eine explizite `False` deaktiviert."""
    with db_module.SessionLocal() as session:
        rows = session.query(db_module.Source.name, db_module.Source.enabled).all()
    disabled = {name for name, enabled in rows if not enabled}
    return [cls() for name, cls in REGISTRY.items() if name not in disabled]
