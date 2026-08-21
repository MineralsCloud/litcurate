"""Build source-schema payloads from OpenAlex / ranked parquet metadata."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

_PAPERS_META_CANDIDATES = (
    "papers_filtered.parquet",
    "papers_ranked.parquet",
)

_SOURCE_TYPE_ENUM = frozenset({"journal", "database", "book", "thesis", "other"})


class _ArtifactLookup(Protocol):
    def artifact(self, *parts: str) -> Path: ...


def load_papers_meta_index(ctx: _ArtifactLookup) -> dict[str, dict[str, Any]]:
    """Load paper_id -> metadata row from the best available parquet."""
    for name in _PAPERS_META_CANDIDATES:
        path = ctx.artifact(name)
        if path.exists():
            frame = pd.read_parquet(path)
            if "paper_id" not in frame.columns:
                continue
            return {
                str(row["paper_id"]): row.to_dict()
                for _, row in frame.iterrows()
            }
    return {}


def source_payload_from_paper_meta(meta: dict[str, Any]) -> dict[str, Any]:
    """Map a parquet/OpenAlex paper row into a bibliographic source schema shape."""
    authors = _parse_authors(meta.get("authors_json"))
    year = _coerce_year(meta.get("year"))
    doi = _as_str(meta.get("doi")) or ""
    title = _as_str(meta.get("title")) or ""
    journal = _as_str(meta.get("journal")) or None
    source_type = _map_source_type(meta.get("source_type"), meta.get("work_type"))

    payload: dict[str, Any] = {
        "doi": doi,
        "title": title,
        "year": year if year is not None else 0,
        "source_type": source_type,
        "authors": authors,
        "evidence_text": "Filled from OpenAlex / papers parquet metadata (no LLM).",
        "confidence": 1.0,
    }
    if journal:
        payload["journal"] = journal
    return payload


def _parse_authors(raw: Any) -> list[str]:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return []
    if isinstance(raw, list):
        return [str(a) for a in raw if a]
    text = str(raw).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return [text]
    if isinstance(parsed, list):
        return [str(a) for a in parsed if a]
    return [str(parsed)]


def _coerce_year(raw: Any) -> int | None:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _as_str(raw: Any) -> str | None:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    text = str(raw).strip()
    return text or None


def _map_source_type(source_type: Any, work_type: Any) -> str:
    for candidate in (source_type, work_type):
        text = _as_str(candidate)
        if not text:
            continue
        lowered = text.lower()
        if "journal" in lowered or lowered in {"article", "review"}:
            return "journal"
        if "book" in lowered:
            return "book"
        if "thesis" in lowered or "dissertation" in lowered:
            return "thesis"
        if "repository" in lowered or "database" in lowered or "dataset" in lowered:
            return "database"
        if lowered in _SOURCE_TYPE_ENUM:
            return lowered
    return "journal"
