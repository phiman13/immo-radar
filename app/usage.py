from __future__ import annotations

from datetime import UTC, datetime

import app.db as db_module

# USD per million tokens — update wenn Anthropic Preise ändert
_PRICES: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-haiku-3-5-20241022": {"input": 0.80, "output": 4.00},
}
_DEFAULT_PRICE = {"input": 0.80, "output": 4.00}


def tokens_to_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    price = _PRICES.get(model, _DEFAULT_PRICE)
    return (input_tokens * price["input"] + output_tokens * price["output"]) / 1_000_000


def log_usage(model: str, input_tokens: int, output_tokens: int, purpose: str) -> None:
    """Persist API token usage to DB. Call after every messages.create() success."""
    try:
        with db_module.SessionLocal() as session:
            row = db_module.ApiUsage(
                ts=datetime.now(UTC),
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                purpose=purpose,
            )
            session.add(row)
            session.commit()
    except Exception:
        pass  # Never let usage logging break the main flow
