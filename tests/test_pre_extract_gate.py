"""Tests for regex pre-extract gate."""

from __future__ import annotations

from litcurate.config import PreExtractConfig
from litcurate.pre_extract_gate import passes_pre_extract, score_regex_signals


def test_regex_signals_match_configured_terms() -> None:
    cfg = PreExtractConfig(
        enabled=True,
        regex_signals=[r"parameter", r"table"],
        min_signal_hits=1,
    )
    text = "We report a fitted parameter in Table 2."
    hits, matched = score_regex_signals(text, cfg)
    assert hits >= 2
    assert matched
    ok, _ = passes_pre_extract(text, cfg)
    assert ok


def test_regex_gate_fails_when_below_threshold() -> None:
    cfg = PreExtractConfig(
        enabled=True,
        regex_signals=[r"parameter"],
        min_signal_hits=2,
    )
    text = "Only one parameter mention."
    ok, reason = passes_pre_extract(text, cfg)
    assert not ok
    assert "need 2" in reason
