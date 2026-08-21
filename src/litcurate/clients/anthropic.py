"""Anthropic client helpers — prefer litcurate.clients.llm.llm_chat."""

from __future__ import annotations

from typing import Any

from litcurate.clients.llm import LlmResponse, llm_chat
from litcurate.stages.base import StageContext


def claude_messages_create(
    ctx: StageContext,
    *,
    stage_name: str,
    model: str,
    max_tokens: int,
    messages: list[dict[str, Any]],
    label: str | None = None,
) -> LlmResponse:
    """Backward-compatible wrapper around the unified LLM client."""
    return llm_chat(
        ctx,
        stage_name=stage_name,
        model=model,
        max_tokens=max_tokens,
        messages=messages,
        label=label,
    )
