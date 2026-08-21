"""Tests for unified LLM client."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from litcurate.clients.llm import (
    PROVIDER_ANTHROPIC,
    PROVIDER_OPENAI_COMPATIBLE,
    _anthropic_response_text,
    llm_chat,
    llm_is_configured,
    llm_require_configured,
)
from litcurate.config import (
    AbstractFilterConfig,
    FulltextFilterConfig,
    LlmConfig,
    PipelineConfig,
    RunConfig,
    SearchConfig,
    resolve_stage_llm,
)
from litcurate.run_store import open_run_store
from litcurate.stages.base import StageContext


def _minimal_config(**llm_overrides: object) -> PipelineConfig:
    overrides = {"provider": "anthropic", **llm_overrides}
    return PipelineConfig(
        run=RunConfig(name="t", user_goal="goal"),
        abstract_filter=AbstractFilterConfig(criteria="keep relevant"),
        llm=LlmConfig(**overrides),
    )


def test_llm_provider_is_required() -> None:
    with pytest.raises(Exception):
        LlmConfig()  # type: ignore[call-arg]


def test_pipeline_config_requires_llm_block() -> None:
    with pytest.raises(Exception):
        PipelineConfig(
            run=RunConfig(name="t", user_goal="goal"),
            abstract_filter=AbstractFilterConfig(criteria="keep"),
        )


def test_llm_is_configured_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    llm = LlmConfig(provider="anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert llm_is_configured(llm) is False
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert llm_is_configured(llm) is True


def test_llm_is_configured_openai_compatible() -> None:
    llm = LlmConfig(provider=PROVIDER_OPENAI_COMPATIBLE)
    assert llm_is_configured(llm) is False
    llm = LlmConfig(provider=PROVIDER_OPENAI_COMPATIBLE, base_url="http://localhost:11434/v1")
    assert llm_is_configured(llm) is True


def test_resolve_stage_llm_overrides_provider_only() -> None:
    global_llm = LlmConfig(provider=PROVIDER_ANTHROPIC)
    stage = FulltextFilterConfig(
        criteria="keep",
        provider=PROVIDER_OPENAI_COMPATIBLE,
        base_url="http://localhost:11434/v1",
        model="qwen3:14b",
    )
    resolved = resolve_stage_llm(global_llm, stage)
    assert resolved.provider == PROVIDER_OPENAI_COMPATIBLE
    assert resolved.base_url == "http://localhost:11434/v1"
    assert resolved.timeout_seconds == 600.0


def test_resolve_stage_llm_keeps_global_when_stage_unset() -> None:
    global_llm = LlmConfig(provider=PROVIDER_ANTHROPIC)
    stage = SearchConfig(model="claude-sonnet-4-6")
    resolved = resolve_stage_llm(global_llm, stage)
    assert resolved.provider == PROVIDER_ANTHROPIC


def test_openai_compatible_chat(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = _minimal_config(
        provider=PROVIDER_OPENAI_COMPATIBLE,
        base_url="http://localhost:11434/v1",
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    ctx = StageContext(
        run_id="test",
        run_dir=run_dir,
        artifacts_dir=run_dir / "artifacts",
        config=config,
        store=open_run_store(run_dir),
        dry_run=False,
    )

    def fake_post(url: str, **kwargs: object) -> MagicMock:
        assert url.endswith("/chat/completions")
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            "choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        return response

    monkeypatch.setattr(httpx, "post", fake_post)
    result = llm_chat(
        ctx,
        stage_name="filter_fulltext",
        model="qwen3:14b",
        max_tokens=100,
        messages=[{"role": "user", "content": "hi"}],
        llm=config.llm,
    )
    assert result.text == '{"ok": true}'
    assert result.finish_reason == "stop"
    assert result.truncated is False
    summary = ctx.store.get_api_cost_summary("test")
    assert summary["call_count"] == 1
    assert summary["by_stage"]["filter_fulltext"]["cost_usd"] == 0.0


def test_openai_compatible_marks_truncated(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = _minimal_config(
        provider=PROVIDER_OPENAI_COMPATIBLE,
        base_url="http://localhost:11434/v1",
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    ctx = StageContext(
        run_id="test",
        run_dir=run_dir,
        artifacts_dir=run_dir / "artifacts",
        config=config,
        store=open_run_store(run_dir),
        dry_run=False,
    )

    def fake_post(url: str, **kwargs: object) -> MagicMock:
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            "choices": [{"message": {"content": '{"partial": true}'}, "finish_reason": "length"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 100},
        }
        return response

    monkeypatch.setattr(httpx, "post", fake_post)
    result = llm_chat(
        ctx,
        stage_name="filter_abstracts",
        model="qwen3:14b",
        max_tokens=100,
        messages=[{"role": "user", "content": "hi"}],
        llm=config.llm,
    )
    assert result.truncated is True
    assert result.finish_reason == "length"


def test_per_stage_provider_override_in_chat(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = _minimal_config(provider=PROVIDER_ANTHROPIC)
    config.fulltext_filter = FulltextFilterConfig(
        criteria="keep",
        provider=PROVIDER_OPENAI_COMPATIBLE,
        base_url="http://localhost:11434/v1",
        model="qwen3:14b",
    )
    stage_llm = resolve_stage_llm(config.llm, config.fulltext_filter)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    ctx = StageContext(
        run_id="test",
        run_dir=run_dir,
        artifacts_dir=run_dir / "artifacts",
        config=config,
        store=open_run_store(run_dir),
        dry_run=False,
    )

    def fake_post(url: str, **kwargs: object) -> MagicMock:
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            "choices": [{"message": {"content": "yes"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
        return response

    monkeypatch.setattr(httpx, "post", fake_post)
    result = llm_chat(
        ctx,
        stage_name="filter_fulltext",
        model="qwen3:14b",
        max_tokens=50,
        messages=[{"role": "user", "content": "hi"}],
        llm=stage_llm,
    )
    assert result.text == "yes"


def test_llm_require_configured_raises() -> None:
    llm = LlmConfig(provider=PROVIDER_OPENAI_COMPATIBLE)
    with pytest.raises(RuntimeError, match="base_url"):
        llm_require_configured(llm, stage="extract_schema")


def test_anthropic_response_text_skips_thinking_blocks() -> None:
    thinking = MagicMock(type="thinking", text=None, thinking="internal reasoning")
    text_block = MagicMock(type="text", text='{"records": []}')
    response = MagicMock(content=[thinking, text_block])
    assert _anthropic_response_text(response) == '{"records": []}'


def test_anthropic_response_text_joins_multiple_text_blocks() -> None:
    first = MagicMock(type="text", text='{"records": [')
    second = MagicMock(type="text", text=']}')
    response = MagicMock(content=[first, second])
    assert _anthropic_response_text(response) == '{"records": [\n]}'
