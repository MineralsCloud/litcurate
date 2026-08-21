"""Helpers for parsing and normalizing Consensus API responses."""

from __future__ import annotations

import json
from typing import Any

from litcurate.doi import normalize_doi


def extract_papers_from_response(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return paper dicts from a Consensus quick_search response."""
    papers = payload.get("results")
    if papers is None:
        papers = payload.get("papers")
    return papers or []


def _clean_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "none":
        return None
    return text


def normalize_consensus_paper(paper: dict[str, Any]) -> dict[str, Any]:
    """Map Consensus API fields to litcurate columns while keeping the full record."""
    doi = _clean_optional_str(paper.get("doi"))
    authors = paper.get("authors") or []
    if not isinstance(authors, list):
        authors = [authors]

    year = paper.get("publish_year")
    if year is None:
        year = paper.get("year")

    relevance = paper.get("relevance_score")
    if relevance is not None:
        relevance = float(relevance)

    citation_count = paper.get("citation_count")
    if citation_count is None:
        citation_count = 0

    abstract = _clean_optional_str(paper.get("abstract"))

    return {
        "doi": normalize_doi(doi) if doi else None,
        "title": _clean_optional_str(paper.get("title")),
        "abstract": abstract,
        "abstract_source": "consensus" if abstract else None,
        "authors": authors,
        "authors_json": json.dumps(authors, ensure_ascii=False),
        "year": year,
        "journal": _clean_optional_str(paper.get("journal_name") or paper.get("journal")),
        "pages": _clean_optional_str(paper.get("pages")),
        "volume": _clean_optional_str(paper.get("volume")),
        "citation_count": citation_count,
        "consensus_url": _clean_optional_str(paper.get("url")),
        "study_type": _clean_optional_str(paper.get("study_type")),
        "takeaway": _clean_optional_str(paper.get("takeaway")),
        "publisher_name": _clean_optional_str(paper.get("publisher_name")),
        "relevance_score": relevance,
        "consensus_raw_json": json.dumps(paper, ensure_ascii=False),
    }


def paper_dedupe_key(paper: dict[str, Any]) -> str | None:
    """Primary dedupe key: normalized DOI, else normalized title."""
    normalized = normalize_consensus_paper(paper)
    if normalized["doi"]:
        return normalized["doi"]
    title = normalized.get("title")
    if title:
        return title.strip().lower()
    return None


def merge_paper_records(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Prefer the record with more populated fields when deduping."""
    if _record_richness(incoming) > _record_richness(existing):
        merged = dict(incoming)
    else:
        merged = dict(existing)

    for field in ("abstract", "takeaway", "study_type", "journal", "publisher_name"):
        if not merged.get(field) and incoming.get(field):
            merged[field] = incoming[field]

    if not merged.get("doi") and incoming.get("doi"):
        merged["doi"] = incoming["doi"]

    if incoming.get("relevance_score") is not None:
        scores = [
            s
            for s in (existing.get("relevance_score"), incoming.get("relevance_score"))
            if s is not None
        ]
        merged["relevance_score"] = max(scores) if scores else None

    return merged


def _record_richness(record: dict[str, Any]) -> int:
    skip = {"consensus_raw_json", "authors_json"}
    count = 0
    for key, value in record.items():
        if key in skip:
            continue
        if value is None:
            continue
        if value == "" or value == []:
            continue
        count += 1
    return count
