"""Unified LLM client: Anthropic or OpenAI-compatible APIs (Ollama, vLLM, OpenRouter)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx

from litcurate.api_costs import TokenUsage, usage_from_openai_dict, usage_from_response
from litcurate.config import LlmConfig
from litcurate.env import get_env

if TYPE_CHECKING:
    from litcurate.stages.base import StageContext

logger = logging.getLogger(__name__)

PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OPENAI_COMPATIBLE = "openai_compatible"

_TRUNCATION_FINISH_REASONS = frozenset(
    {
        "length",
        "max_tokens",
        "max_token",
    }
)


@dataclass(frozen=True)
class LlmResponse:
    text: str
    finish_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    truncated: bool = False


def llm_is_configured(llm: LlmConfig) -> bool:
    """Return True when an LLM config is ready to call."""
    if llm.provider == PROVIDER_ANTHROPIC:
        return bool(get_env(llm.resolved_api_key_env()))
    if llm.provider == PROVIDER_OPENAI_COMPATIBLE:
        return bool(llm.base_url and llm.base_url.strip())
    return False


def llm_require_configured(llm: LlmConfig, *, stage: str) -> None:
    if llm_is_configured(llm):
        return
    if llm.provider == PROVIDER_OPENAI_COMPATIBLE:
        raise RuntimeError(
            f"{stage} requires base_url for provider openai_compatible "
            "(set llm.base_url or a per-stage base_url, e.g. http://localhost:11434/v1)"
        )
    raise RuntimeError(
        f"{stage} requires {llm.resolved_api_key_env()} "
        f"(or set dry_run: true, or configure a per-stage provider)"
    )


def llm_chat(
    ctx: StageContext,
    *,
    stage_name: str,
    model: str,
    max_tokens: int,
    messages: list[dict[str, Any]],
    label: str | None = None,
    llm: LlmConfig | None = None,
) -> LlmResponse:
    """Call the LLM provider and record token usage for this run."""
    resolved = llm or ctx.config.llm
    llm_require_configured(resolved, stage=stage_name)

    if resolved.provider == PROVIDER_ANTHROPIC:
        text, usage, finish_reason = _anthropic_chat(
            resolved, model=model, max_tokens=max_tokens, messages=messages
        )
        provider = PROVIDER_ANTHROPIC
    elif resolved.provider == PROVIDER_OPENAI_COMPATIBLE:
        text, usage, finish_reason = _openai_compatible_chat(
            resolved,
            model=model,
            max_tokens=max_tokens,
            messages=messages,
        )
        provider = PROVIDER_OPENAI_COMPATIBLE
    else:
        raise ValueError(f"Unknown llm.provider: {resolved.provider!r}")

    truncated = _is_truncated(
        finish_reason=finish_reason,
        output_tokens=usage.output_tokens,
        max_tokens=max_tokens,
    )
    if truncated:
        logger.warning(
            "LLM %s/%s (%s): truncated response (finish_reason=%s out=%s max_tokens=%s)",
            provider,
            stage_name,
            label or model,
            finish_reason,
            usage.output_tokens,
            max_tokens,
        )

    ctx.store.record_api_usage(
        ctx.run_id,
        stage_name=stage_name,
        provider=provider,
        model=usage.model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cost_usd=usage.cost_usd,
        label=label,
        pricing_known=usage.pricing_known,
    )
    logger.info(
        "LLM %s/%s (%s): in=%s out=%s est_cost=$%.4f%s",
        provider,
        stage_name,
        label or model,
        usage.input_tokens,
        usage.output_tokens,
        usage.cost_usd,
        " truncated=true" if truncated else "",
    )
    return LlmResponse(
        text=text,
        finish_reason=finish_reason,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        truncated=truncated,
    )


def _is_truncated(
    *,
    finish_reason: str | None,
    output_tokens: int | None,
    max_tokens: int,
) -> bool:
    if finish_reason and finish_reason.lower() in _TRUNCATION_FINISH_REASONS:
        return True
    if output_tokens is not None and max_tokens > 0 and output_tokens >= max_tokens:
        return True
    return False


def _anthropic_chat(
    llm: LlmConfig,
    *,
    model: str,
    max_tokens: int,
    messages: list[dict[str, Any]],
) -> tuple[str, TokenUsage, str | None]:
    api_key = get_env(llm.resolved_api_key_env())
    if not api_key:
        raise RuntimeError(f"{llm.resolved_api_key_env()} is required for Anthropic")

    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=messages,
    )
    usage = usage_from_response(response, model=model)
    finish_reason = getattr(response, "stop_reason", None)
    return _anthropic_response_text(response), usage, finish_reason


def _anthropic_response_text(response: Any) -> str:
    """Collect text from Anthropic content blocks (skips thinking/tool blocks)."""
    chunks: list[str] = []
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) != "text":
            continue
        text = getattr(block, "text", None)
        if isinstance(text, str) and text.strip():
            chunks.append(text)

    if chunks:
        return "\n".join(chunks)

    content_types = [
        getattr(block, "type", type(block).__name__)
        for block in getattr(response, "content", []) or []
    ]
    raise ValueError(
        "Anthropic response did not include text content blocks "
        f"(content types: {content_types or 'none'})"
    )


def _openai_compatible_chat(
    llm: LlmConfig,
    *,
    model: str,
    max_tokens: int,
    messages: list[dict[str, Any]],
) -> tuple[str, TokenUsage, str | None]:
    if not llm.base_url:
        raise RuntimeError("base_url is required for openai_compatible provider")

    base_url = llm.base_url.rstrip("/")
    api_key = get_env(llm.resolved_api_key_env()) or "ollama"
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    response = httpx.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=llm.timeout_seconds,
    )
    response.raise_for_status()
    data = response.json()
    try:
        choice = data["choices"][0]
        text = choice["message"]["content"]
        finish_reason = choice.get("finish_reason")
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"Unexpected OpenAI-compatible response: {data!r}") from exc
    if not text:
        raise ValueError("OpenAI-compatible model returned empty content")
    usage = usage_from_openai_dict(data, model=model)
    return text, usage, finish_reason
