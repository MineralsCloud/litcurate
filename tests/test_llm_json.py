"""Tests for LLM JSON parsing helpers."""

from __future__ import annotations

import pytest

from litcurate.llm_json import (
    filter_decisions_from_llm,
    parse_filter_decisions,
    parse_llm_json,
    parse_llm_json_object,
)


def test_parse_llm_json_with_trailing_prose() -> None:
    text = """Here are the results:
{"decisions": [{"paper_id": "10.1_a", "keep": true, "reason": "primary data"}]}
Hope that helps!"""
    payload = parse_llm_json(text)
    assert payload["decisions"][0]["paper_id"] == "10.1_a"


def test_parse_llm_json_with_markdown_fence() -> None:
    text = """```json
{"decisions": [{"paper_id": "10.1_a", "keep": false, "reason": "review only"}]}
```"""
    payload = parse_llm_json(text)
    assert payload["decisions"][0]["keep"] is False


def test_parse_llm_json_ignores_second_object() -> None:
    text = (
        '{"decisions": [{"paper_id": "a", "keep": true, "reason": "ok"}]}\n'
        '{"decisions": [{"paper_id": "b", "keep": false, "reason": "duplicate"}]}'
    )
    payload = parse_llm_json(text)
    assert len(payload["decisions"]) == 1
    assert payload["decisions"][0]["paper_id"] == "a"


def test_parse_llm_json_raises_when_missing() -> None:
    with pytest.raises(ValueError, match="did not contain valid JSON"):
        parse_llm_json("no json here")


def test_filter_decisions_from_object() -> None:
    payload = {"decisions": [{"paper_id": "10.1_a", "keep": True, "reason": "relevant"}]}
    assert filter_decisions_from_llm(payload)[0]["paper_id"] == "10.1_a"


def test_filter_decisions_from_list() -> None:
    payload = [{"paper_id": "10.1_a", "keep": "true", "reason": "relevant"}]
    item = filter_decisions_from_llm(payload)[0]
    assert item["keep"] is True


def test_filter_decisions_from_single_object() -> None:
    payload = {"paper_id": "10.1_a", "keep": True, "reason": "relevant"}
    item = filter_decisions_from_llm(payload)[0]
    assert item["paper_id"] == "10.1_a"


def test_parse_filter_decisions_recovers_truncated_json() -> None:
    # Truncated mid-array after first complete decision object.
    text = (
        '{"decisions": ['
        '{"paper_id": "p1", "keep": true, "reason": "primary fit"},'
        '{"paper_id": "p2", "keep": false, "reason": "rev'
    )
    decisions = parse_filter_decisions(text)
    assert len(decisions) == 1
    assert decisions[0]["paper_id"] == "p1"
    assert decisions[0]["keep"] is True


def test_parse_llm_json_object_with_nested_braces_in_strings() -> None:
    text = (
        'Prefix text\n{"records": [{"evidence": {"quote": "value with } brace"}}]}'
        "\nTrailing note"
    )
    payload = parse_llm_json_object(text)
    assert payload["records"][0]["evidence"]["quote"] == "value with } brace"


def test_parse_llm_json_object_with_unclosed_fence() -> None:
    text = '```json\n{"records": [{"title": "Example"}]}'
    payload = parse_llm_json_object(text)
    assert payload["records"][0]["title"] == "Example"


def test_parse_llm_json_object_raises_for_invalid_payload() -> None:
    with pytest.raises(ValueError, match="valid JSON object"):
        parse_llm_json_object("not json")


def test_parse_llm_json_object_raises_for_none() -> None:
    with pytest.raises(ValueError, match="text was None"):
        parse_llm_json_object(None)
