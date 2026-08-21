"""Tests for Anthropic API cost estimation."""

from litcurate.api_costs import estimate_cost_usd, usage_from_response


class _Usage:
    input_tokens = 1000
    output_tokens = 500


class _Response:
    usage = _Usage()


def test_estimate_cost_usd_known_model() -> None:
    usage = estimate_cost_usd("claude-sonnet-4-6", 1_000_000, 1_000_000)
    assert usage.pricing_known is True
    assert usage.cost_usd == 18.0


def test_usage_from_response() -> None:
    usage = usage_from_response(_Response(), model="claude-sonnet-4-6")
    assert usage.input_tokens == 1000
    assert usage.output_tokens == 500
    assert usage.cost_usd > 0
