"""Cost estimation from recorded token usage and the editable price table in config/pricing.yaml."""

from __future__ import annotations

from functools import lru_cache

import yaml

from .settings import CONFIG_DIR


@lru_cache(maxsize=1)
def load_pricing() -> dict:
    return yaml.safe_load((CONFIG_DIR / "pricing.yaml").read_text())


def estimate_cost_usd(model: str | None, input_tokens: int | None, output_tokens: int | None) -> float | None:
    """Return None ("unavailable") when usage or pricing is missing. Never infer zero."""
    if model is None or input_tokens is None or output_tokens is None:
        return None
    price = load_pricing().get("models", {}).get(model)
    if not price:
        return None
    return round(input_tokens / 1e6 * price["input_per_mtok"] + output_tokens / 1e6 * price["output_per_mtok"], 6)
