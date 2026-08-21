"""Stage 3: Merge search results, dedupe by DOI, and rank."""

from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path

import pandas as pd

from litcurate.clients.literature import (
    extract_papers_from_response,
    merge_paper_records,
    normalize_search_paper,
    paper_dedupe_key,
)
from litcurate.merge_filters import filter_ranked_papers
from litcurate.stages.base import StageContext, StageResult
from litcurate.stages.utils import (
    SAMPLE_PAPERS,
    paper_id_from_doi,
    read_json,
    write_parquet,
)

SEARCH_RAW_DIRS = ("openalex_raw", "consensus_raw")


class MergeRankStage:
    name = "merge_rank"
    description = "Union, dedupe, and rank papers from literature searches"

    def should_skip(self, ctx: StageContext) -> bool:
        output = ctx.artifact("papers_ranked.parquet")
        return output.exists() and ctx.store.is_stage_completed(ctx.run_id, self.name)

    def run(self, ctx: StageContext) -> StageResult:
        output = ctx.artifact("papers_ranked.parquet")
        merge_cfg = ctx.config.search.merge

        if ctx.dry_run:
            frame = pd.DataFrame(SAMPLE_PAPERS)
            write_parquet(output, frame)
            return StageResult(artifact_path=output, message=f"Ranked {len(frame)} dry-run papers")

        raw_files = _collect_raw_search_files(ctx)
        if not raw_files:
            raise FileNotFoundError(
                "No search results found in openalex_raw/ or consensus_raw/"
            )

        buckets: dict[str, dict] = {}
        frequency: dict[str, int] = defaultdict(int)
        relevance_scores: dict[str, list[float]] = defaultdict(list)

        for path in raw_files:
            payload = read_json(path)
            for paper in extract_papers_from_response(payload):
                key = paper_dedupe_key(paper)
                if not key:
                    continue
                frequency[key] += 1
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
            if freq < merge_cfg.min_query_hits:
                continue
            rel = relevance_scores.get(key) or [0.0]
            mean_rel = sum(rel) / len(rel)
            citations = float(meta.get("citation_count") or 0)
            score = (
                freq * merge_cfg.frequency_weight
                + mean_rel * merge_cfg.relevance_weight
                + math.log1p(citations) * merge_cfg.citation_weight
            )
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
                    "pages": meta.get("pages"),
                    "volume": meta.get("volume"),
                    "citation_count": meta.get("citation_count"),
                    "consensus_url": meta.get("consensus_url"),
                    "study_type": meta.get("study_type"),
                    "takeaway": meta.get("takeaway"),
                    "publisher_name": meta.get("publisher_name"),
                    "relevance_score": meta.get("relevance_score"),
                    "is_oa": meta.get("is_oa"),
                    "openalex_id": meta.get("openalex_id"),
                    "work_type": meta.get("work_type"),
                    "source_type": meta.get("source_type"),
                    "search_provider": meta.get("search_provider"),
                    "consensus_raw_json": meta.get("consensus_raw_json"),
                    "frequency": freq,
                    "mean_relevance": mean_rel,
                    "score": score,
                }
            )

        frame = pd.DataFrame(rows)
        if frame.empty:
            write_parquet(output, frame)
            return StageResult(artifact_path=output, message="No papers after merge")

        before_filter = len(frame)
        frame = filter_ranked_papers(
            frame,
            merge_cfg,
            full_papers_only=ctx.config.search.full_papers_only,
        )
        if frame.empty:
            write_parquet(output, frame)
            return StageResult(artifact_path=output, message="No papers after merge filters")

        frame = frame.sort_values("score", ascending=False).head(merge_cfg.top_k)
        write_parquet(output, frame)
        dropped = before_filter - len(frame)
        suffix = f" ({dropped} excluded by merge filters)" if dropped else ""
        return StageResult(
            artifact_path=output,
            message=f"Ranked {len(frame)} papers{suffix}",
        )


def _collect_raw_search_files(ctx) -> list[Path]:
    files: list[Path] = []
    for dirname in SEARCH_RAW_DIRS:
        raw_dir = ctx.artifact(dirname)
        if raw_dir.exists():
            files.extend(sorted(raw_dir.glob("*.json")))
    return files
