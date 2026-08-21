"""Export deduplicated papers from search raw JSON before merge_rank filters."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pandas as pd

from litcurate.clients.literature import (
    extract_papers_from_response,
    merge_paper_records,
    normalize_search_paper,
    paper_dedupe_key,
)
from litcurate.paths import project_runs_dir, run_directory
from litcurate.doi import paper_id_from_doi

SEARCH_RAW_DIRS = ("openalex_raw", "consensus_raw")


def collect_raw_search_files(artifacts_dir: Path) -> list[Path]:
    files: list[Path] = []
    for dirname in SEARCH_RAW_DIRS:
        raw_dir = artifacts_dir / dirname
        if raw_dir.exists():
            files.extend(sorted(raw_dir.glob("*.json")))
    return files


def build_merged_frame(raw_files: list[Path], *, min_query_hits: int = 1) -> pd.DataFrame:
    """Dedupe search hits by DOI/title before merge filters and ranking."""
    buckets: dict[str, dict] = {}
    frequency: dict[str, int] = defaultdict(int)
    relevance_scores: dict[str, list[float]] = defaultdict(list)
    source_files: dict[str, set[str]] = defaultdict(set)

    for path in raw_files:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)

        for paper in extract_papers_from_response(payload):
            key = paper_dedupe_key(paper)
            if not key:
                continue

            frequency[key] += 1
            source_files[key].add(path.name)

            normalized = normalize_search_paper(paper)
            if normalized.get("relevance_score") is not None:
                relevance_scores[key].append(float(normalized["relevance_score"]))

            if key in buckets:
                buckets[key] = merge_paper_records(buckets[key], normalized)
            else:
                buckets[key] = normalized

    rows = []
    for key, meta in buckets.items():
        freq = frequency[key]
        if freq < min_query_hits:
            continue

        rel = relevance_scores.get(key) or [0.0]
        mean_rel = sum(rel) / len(rel)

        rows.append(
            {
                "paper_id": paper_id_from_doi(meta.get("doi"), meta.get("title")),
                "doi": meta.get("doi"),
                "title": meta.get("title"),
                "abstract": meta.get("abstract"),
                "abstract_source": meta.get("abstract_source"),
                "authors_json": meta.get("authors_json"),
                "year": meta.get("year"),
                "journal": meta.get("journal"),
                "citation_count": meta.get("citation_count"),
                "is_oa": meta.get("is_oa"),
                "openalex_id": meta.get("openalex_id"),
                "work_type": meta.get("work_type"),
                "source_type": meta.get("source_type"),
                "search_provider": meta.get("search_provider"),
                "frequency": freq,
                "mean_relevance": mean_rel,
                "source_file_count": len(source_files[key]),
                "source_files": ";".join(sorted(source_files[key])),
            }
        )

    return pd.DataFrame(rows)


def resolve_artifacts_dir(*, run_id: str | None, raw_dir: Path | None, runs_dir: Path | None) -> Path:
    if raw_dir is not None:
        if raw_dir.name in SEARCH_RAW_DIRS:
            return raw_dir.parent
        if (raw_dir / "openalex_raw").exists() or (raw_dir / "consensus_raw").exists():
            return raw_dir
        return raw_dir

    if not run_id:
        raise ValueError("Provide run_id or raw_dir")

    base_runs = runs_dir or project_runs_dir()
    return run_directory(base_runs, run_id) / "artifacts"


def export_merged_papers(
    *,
    run_id: str | None = None,
    raw_dir: Path | None = None,
    runs_dir: Path | None = None,
    min_query_hits: int = 1,
    output: Path | None = None,
    write_csv: bool = False,
) -> tuple[pd.DataFrame, Path]:
    artifacts_dir = resolve_artifacts_dir(run_id=run_id, raw_dir=raw_dir, runs_dir=runs_dir)
    raw_files = collect_raw_search_files(artifacts_dir)
    if not raw_files:
        raise FileNotFoundError(f"No raw search JSON files under {artifacts_dir}")

    frame = build_merged_frame(raw_files, min_query_hits=min_query_hits)
    out = output or (artifacts_dir / "papers_merged.parquet")
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(out, index=False)

    if write_csv:
        frame.to_csv(out.with_suffix(".csv"), index=False)

    return frame, out
