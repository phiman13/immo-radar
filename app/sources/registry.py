from __future__ import annotations

from app.sources.base import SourceAdapter
from app.sources.immoscout24 import ImmoScout24Source
from app.sources.immowelt import ImmoweltSource
from app.sources.kleinanzeigen import KleinanzeigenSource
from app.sources.makler_bsimmo import BsImmoSource
from app.sources.makler_riedel import RiedelSource
from app.sources.makler_starnberg_immo import StarnbergImmoSource
from app.sources.sparkasse_immo import SparkasseImmoSource
from app.sources.tutzing24 import Tutzing24Source

REGISTRY: dict[str, type[SourceAdapter]] = {
    # Disabled — bot-protected (captcha / 403). Re-enable via paid scraping service.
    # "immoscout24": ImmoScout24Source,
    # "immowelt": ImmoweltSource,
    # "sparkasse_immo": SparkasseImmoSource,
    "kleinanzeigen": KleinanzeigenSource,
    "riedel": RiedelSource,
    "starnberg_bader": StarnbergImmoSource,
    "bs_immo": BsImmoSource,
    "tutzing24": Tutzing24Source,
}


def get_all_adapters() -> list[SourceAdapter]:
    return [cls() for cls in REGISTRY.values()]
