"""Anthropic API usage and cost estimation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# USD per 1M tokens. Update when Anthropic changes list prices.
MODEL_PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-sonnet-4-0": (3.0, 15.0),
    "claude-opus-4-6": (15.0, 75.0),
    "claude-opus-4-5": (15.0, 75.0),
    "claude-opus-4-0": (15.0, 75.0),
    "claude-3-5-sonnet-latest": (3.0, 15.0),
    "claude-3-5-haiku-latest": (0.8, 4.0),
    "claude-3-opus-latest": (15.0, 75.0),
}


@dataclass(frozen=True)
class TokenUsage:
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    pricing_known: bool


def get_model_pricing(model: str) -> tuple[float, float, bool]:
    """Return (input_usd_per_mtok, output_usd_per_mtok, exact_match)."""
    if model in MODEL_PRICING_PER_MTOK:
        input_rate, output_rate = MODEL_PRICING_PER_MTOK[model]
        return input_rate, output_rate, True

    lowered = model.lower()
    if "opus" in lowered:
        return 15.0, 75.0, False
    if "haiku" in lowered:
        return 0.8, 4.0, False
    if "sonnet" in lowered:
        return 3.0, 15.0, False
    return 3.0, 15.0, False


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> TokenUsage:
    input_rate, output_rate, pricing_known = get_model_pricing(model)
    cost = (input_tokens / 1_000_000) * input_rate + (output_tokens / 1_000_000) * output_rate
    return TokenUsage(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=round(cost, 6),
        pricing_known=pricing_known,
    )


def usage_from_response(response: Any, *, model: str) -> TokenUsage:
    usage = getattr(response, "usage", None)
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    return estimate_cost_usd(model, input_tokens, output_tokens)


def usage_from_openai_dict(payload: dict[str, Any], *, model: str) -> TokenUsage:
    """Token usage from an OpenAI-compatible /chat/completions JSON body."""
    usage = payload.get("usage") or {}
    input_tokens = int(usage.get("prompt_tokens", 0) or 0)
    output_tokens = int(usage.get("completion_tokens", 0) or 0)
    return TokenUsage(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=0.0,
        pricing_known=False,
    )
