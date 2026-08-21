"""Regex-based pre-extraction gate for cleaned markdown."""

from __future__ import annotations

import re

from litcurate.config import PreExtractConfig


def score_regex_signals(text: str, cfg: PreExtractConfig) -> tuple[int, list[str]]:
    """Return hit count and which signals matched."""
    if not cfg.regex_signals:
        return 0, []

    flags = re.IGNORECASE if cfg.case_insensitive else 0
    matched: list[str] = []
    for signal in cfg.regex_signals:
        pattern = signal.strip()
        if not pattern:
            continue
        if re.search(pattern, text, flags):
            matched.append(pattern)
    return len(matched), matched


def passes_pre_extract(text: str, cfg: PreExtractConfig) -> tuple[bool, str]:
    if not cfg.enabled:
        return True, "pre_extract disabled"
    if not cfg.regex_signals:
        return True, "no regex signals configured"

    hits, matched = score_regex_signals(text, cfg)
    if hits >= cfg.min_signal_hits:
        return True, f"matched {hits} signal(s): {', '.join(matched[:5])}"
    return False, f"only {hits} signal hit(s); need {cfg.min_signal_hits}"
