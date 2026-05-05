"""Run the web dashboard. Usage: python -m scripts.run_web"""
from __future__ import annotations

import uvicorn

from app.config import settings
from app.logging_setup import configure_logging


def main() -> None:
    configure_logging()
    uvicorn.run("app.web.server:app", host="0.0.0.0", port=settings.dashboard_port, log_level="info")


if __name__ == "__main__":
    main()
