from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    search_center_lat: float = 47.9095
    search_center_lon: float = 11.2783
    search_radius_km: float = 5.0
    price_min: int = 0
    price_max: int = 10_000_000
    qm_min: int = 0
    qm_max: int = 1000
    rooms_min: float = 0.0
    property_types: str = "wohnung,haus,doppelhaushaelfte,reihenhaus"
    year_built_min: int = 1900

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    anthropic_api_key: str = ""
    ai_model: str = "claude-haiku-4-5-20251001"

    poll_interval_minutes: int = 10
    detail_fetch_interval_minutes: int = 60
    score_threshold: float = 0.0

    dashboard_user: str = "admin"
    dashboard_password: str = "changeme"
    dashboard_port: int = 8000

    db_path: str = Field(
        default_factory=lambda: str(Path(__file__).resolve().parent.parent / "data" / "immo.db")
    )

    log_level: str = "INFO"

    @property
    def property_type_list(self) -> list[str]:
        return [p.strip().lower() for p in self.property_types.split(",") if p.strip()]


settings = Settings()
