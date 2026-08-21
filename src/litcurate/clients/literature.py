"""Provider-agnostic literature search result normalization."""

from __future__ import annotations

import json
from typing import Any

from litcurate.clients.consensus import normalize_consensus_paper
from litcurate.clients.openalex import reconstruct_abstract
from litcurate.doi import normalize_doi


def extract_papers_from_response(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return paper/work dicts from a saved search response."""
    papers = payload.get("results")
    if papers is None:
        papers = payload.get("papers")
    return papers or []


def detect_provider(paper: dict[str, Any]) -> str:
    paper_id = str(paper.get("id") or "")
    if paper.get("display_name") or paper.get("abstract_inverted_index") or paper_id.startswith(
        "https://openalex.org"
    ):
        return "openalex"
    return "consensus"


def normalize_openalex_paper(paper: dict[str, Any]) -> dict[str, Any]:
    """Map an OpenAlex work object to litcurate columns."""
    doi_raw = paper.get("doi")
    doi = normalize_doi(doi_raw) if doi_raw else None

    authors = [
        auth.get("author", {}).get("display_name", "")
        for auth in paper.get("authorships") or []
        if auth.get("author", {}).get("display_name")
    ]

    primary_location = paper.get("primary_location") or {}
    source = primary_location.get("source") or {}
    journal = source.get("display_name")
    open_access = paper.get("open_access") or {}

    rank = paper.get("_relevance_rank") or paper.get("relevance_rank")
    relevance_score = None
    if rank is not None:
        relevance_score = max(0.0, 1.0 - (int(rank) - 1) / 50.0)

    abstract = reconstruct_abstract(paper.get("abstract_inverted_index"))

    return {
        "doi": doi,
        "title": paper.get("display_name") or paper.get("title"),
        "abstract": abstract,
        "abstract_source": "openalex" if abstract else None,
        "authors": authors,
        "authors_json": json.dumps(authors, ensure_ascii=False),
        "year": paper.get("publication_year"),
        "journal": journal,
        "pages": primary_location.get("raw_source_name"),
        "volume": None,
        "citation_count": paper.get("cited_by_count") or 0,
        "consensus_url": paper.get("id") or paper.get("doi") or primary_location.get("landing_page_url"),
        "study_type": None,
        "takeaway": None,
        "publisher_name": source.get("host_organization_name"),
        "relevance_score": relevance_score,
        "is_oa": open_access.get("is_oa", False),
        "openalex_id": paper.get("id"),
        "work_type": paper.get("type"),
        "source_type": source.get("type"),
        "search_provider": "openalex",
        "consensus_raw_json": json.dumps(paper, ensure_ascii=False),
    }


def normalize_search_paper(paper: dict[str, Any]) -> dict[str, Any]:
    if detect_provider(paper) == "openalex":
        return normalize_openalex_paper(paper)
    normalized = normalize_consensus_paper(paper)
    normalized["search_provider"] = "consensus"
    return normalized


def paper_dedupe_key(paper: dict[str, Any]) -> str | None:
    normalized = normalize_search_paper(paper)
    if normalized["doi"]:
        return normalized["doi"]
    title = normalized.get("title")
    if title:
        return str(title).strip().lower()
    openalex_id = normalized.get("openalex_id")
    if openalex_id:
        return str(openalex_id).strip().lower()
    return None


def merge_paper_records(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    if _record_richness(incoming) > _record_richness(existing):
        merged = dict(incoming)
    else:
        merged = dict(existing)

    for field in ("abstract", "takeaway", "study_type", "journal", "publisher_name", "doi"):
        if not merged.get(field) and incoming.get(field):
            merged[field] = incoming[field]

    if not merged.get("abstract_source") and incoming.get("abstract_source"):
        merged["abstract_source"] = incoming.get("abstract_source")

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
        if value is None or value == "" or value == []:
            continue
        count += 1
    return count
