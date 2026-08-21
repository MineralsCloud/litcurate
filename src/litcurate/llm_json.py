"""Parse JSON objects from LLM responses with fences or trailing prose."""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL | re.IGNORECASE)
_OPEN_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*\n?(.*)$", re.DOTALL | re.IGNORECASE)


def parse_llm_json(text: str | None) -> Any:
    """Return the first JSON value embedded in an LLM response."""
    if text is None:
        raise ValueError("LLM response text was None")
    if not str(text).strip():
        raise ValueError("LLM response text was empty")
    cleaned = _strip_markdown_fences(str(text).strip())
    value = _decode_first_json_value(cleaned)
    if value is not None:
        return value
    raise ValueError("LLM response did not contain valid JSON")


def parse_llm_json_object(text: str | None) -> dict[str, Any]:
    """Return the first JSON object embedded in an LLM response."""
    if text is None:
        raise ValueError("LLM response text was None")
    if not str(text).strip():
        raise ValueError("LLM response text was empty")
    cleaned = _strip_markdown_fences(str(text).strip())
    value = _decode_first_json_value(cleaned)
    if isinstance(value, dict):
        return value

    outer = _extract_balanced_json_object(cleaned)
    if outer is not None:
        try:
            value = json.loads(outer)
        except json.JSONDecodeError:
            value = None
        if isinstance(value, dict):
            return value

    raise ValueError("LLM response did not contain a valid JSON object")


def _decode_first_json_value(text: str) -> Any | None:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char not in "{[":
            continue
        try:
            value, _end = decoder.raw_decode(text, index)
            return value
        except json.JSONDecodeError:
            continue
    return None


def _extract_balanced_json_object(text: str) -> str | None:
    """Extract the first top-level {...} block with string-aware brace matching."""
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def filter_decisions_from_llm(payload: Any) -> list[dict[str, Any]]:
    """Normalize batch filter responses from Claude or open-source models."""
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = None
        for key in ("decisions", "results", "papers"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                items = candidate
                break
        if items is None and "paper_id" in payload:
            # Single decision object (common when truncated or model omits wrapper).
            items = [payload]
        if items is None:
            raise ValueError(
                "Filter response object must include a decisions list; "
                f"got keys: {list(payload.keys())}"
            )
    else:
        raise ValueError(f"Filter response must be a list or object, got {type(payload).__name__}")

    decisions: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict) or "paper_id" not in item:
            continue
        keep = item.get("keep", False)
        if isinstance(keep, str):
            keep = keep.strip().lower() in {"true", "yes", "1"}
        decisions.append(
            {
                "paper_id": str(item["paper_id"]),
                "keep": bool(keep),
                "reason": str(item.get("reason", "")),
            }
        )
    if not decisions:
        raise ValueError("Filter response did not include any paper decisions")
    return decisions


def extract_complete_decision_objects(text: str) -> list[dict[str, Any]]:
    """Recover complete decision objects from truncated filter JSON text."""
    cleaned = _strip_markdown_fences(str(text).strip())
    decisions: list[dict[str, Any]] = []
    seen: set[str] = set()
    decoder = json.JSONDecoder()
    index = 0
    while index < len(cleaned):
        start = cleaned.find("{", index)
        if start == -1:
            break
        try:
            value, end = decoder.raw_decode(cleaned, start)
        except json.JSONDecodeError:
            index = start + 1
            continue
        index = end
        if not isinstance(value, dict):
            continue
        if "paper_id" in value and ("keep" in value or "reason" in value):
            paper_id = str(value["paper_id"])
            if paper_id in seen:
                continue
            seen.add(paper_id)
            keep = value.get("keep", False)
            if isinstance(keep, str):
                keep = keep.strip().lower() in {"true", "yes", "1"}
            decisions.append(
                {
                    "paper_id": paper_id,
                    "keep": bool(keep),
                    "reason": str(value.get("reason", "")),
                }
            )
            continue
        for key in ("decisions", "results", "papers"):
            nested = value.get(key)
            if not isinstance(nested, list):
                continue
            for item in filter_decisions_from_llm(nested):
                if item["paper_id"] not in seen:
                    seen.add(item["paper_id"])
                    decisions.append(item)
    return decisions


def parse_filter_decisions(text: str) -> list[dict[str, Any]]:
    """Parse filter decisions, recovering complete objects if JSON is truncated."""
    try:
        return filter_decisions_from_llm(parse_llm_json(text))
    except ValueError:
        recovered = extract_complete_decision_objects(text)
        if recovered:
            return recovered
        raise


def _strip_markdown_fences(text: str) -> str:
    match = _FENCE_PATTERN.match(text)
    if match:
        return match.group(1).strip()
    open_match = _OPEN_FENCE_PATTERN.match(text)
    if open_match:
        return open_match.group(1).strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text
