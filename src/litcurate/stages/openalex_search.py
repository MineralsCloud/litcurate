"""Stage 2: Search OpenAlex semantic index for each generated query."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from litcurate.clients.openalex import (
    OpenAlexRequestError,
    build_filter,
    fetch_works_for_query,
)
from litcurate.config import YearSliceConfig
from litcurate.env import get_env
from litcurate.stages.base import StageContext, StageResult
from litcurate.stages.utils import read_json, write_json

logger = logging.getLogger(__name__)


class OpenAlexSearchStage:
    name = "openalex_search"
    description = "Query OpenAlex semantic search for each prompt"

    def should_skip(self, ctx: StageContext) -> bool:
        raw_dir = ctx.artifact("openalex_raw")
        return raw_dir.exists() and any(raw_dir.glob("*.json")) and ctx.store.is_stage_completed(
            ctx.run_id, self.name
        )

    def run(self, ctx: StageContext) -> StageResult:
        queries_path = ctx.artifact("queries.json")
        if not queries_path.exists():
            raise FileNotFoundError("queries.json not found — run query_generation first")

        queries_payload = read_json(queries_path)
        queries = queries_payload.get("queries", [])
        raw_dir = ctx.artifact("openalex_raw")
        raw_dir.mkdir(parents=True, exist_ok=True)

        openalex_cfg = ctx.config.search.openalex
        year_slices = openalex_cfg.search_year_slices()

        if ctx.dry_run:
            for item in queries:
                for slice_cfg in year_slices:
                    _write_dry_run_result(raw_dir, item, slice_cfg, openalex_cfg)
            search_count = len(queries) * len(year_slices)
            return StageResult(
                artifact_path=raw_dir,
                message=(
                    f"Wrote dry-run OpenAlex results for {len(queries)} queries"
                    f" × {len(year_slices)} year slice(s)"
                ),
            )

        _clear_raw_results(raw_dir)

        api_key = get_env("OPENALEX_API_KEY")
        if not api_key and not get_env("OPENALEX_EMAIL") and not get_env("OPENALEX_MAILTO"):
            raise RuntimeError(
                "Set OPENALEX_API_KEY or OPENALEX_EMAIL for OpenAlex search (or use dry_run: true)"
            )

        search_count = 0
        failed_count = 0
        for item in queries:
            query_id = item["id"]
            for slice_cfg in year_slices:
                extra_filter = build_filter(
                    year_min=slice_cfg.year_min,
                    year_max=slice_cfg.year_max,
                    extra_filter=openalex_cfg.extra_filter,
                    is_oa=openalex_cfg.is_oa,
                    full_papers_only=ctx.config.search.full_papers_only,
                )
                suffix = openalex_cfg.slice_result_suffix(slice_cfg)
                out_path = raw_dir / f"{query_id}{suffix}.json"
                try:
                    works = fetch_works_for_query(
                        item["query"],
                        max_results=openalex_cfg.max_results_per_query,
                        per_page=openalex_cfg.per_page,
                        extra_filter=extra_filter,
                        request_delay_seconds=openalex_cfg.request_delay_seconds,
                    )
                except OpenAlexRequestError as exc:
                    failed_count += 1
                    logger.warning(
                        "openalex_search %s%s failed after retries (%s); skipping",
                        query_id,
                        suffix,
                        exc,
                    )
                    write_json(
                        out_path,
                        {
                            "provider": "openalex",
                            "query_id": query_id,
                            "query": item["query"],
                            "year_min": slice_cfg.year_min,
                            "year_max": slice_cfg.year_max,
                            "filter": extra_filter,
                            "results": [],
                            "status": "failed",
                            "error": str(exc),
                        },
                    )
                    search_count += 1
                    time.sleep(openalex_cfg.request_delay_seconds)
                    continue

                write_json(
                    out_path,
                    {
                        "provider": "openalex",
                        "query_id": query_id,
                        "query": item["query"],
                        "year_min": slice_cfg.year_min,
                        "year_max": slice_cfg.year_max,
                        "filter": extra_filter,
                        "results": works,
                        "status": "success",
                    },
                )
                search_count += 1
                time.sleep(openalex_cfg.request_delay_seconds)

        slice_note = f" × {len(year_slices)} year slice(s)" if len(year_slices) > 1 else ""
        fail_note = f", {failed_count} failed/skipped" if failed_count else ""
        return StageResult(
            artifact_path=raw_dir,
            message=(
                f"Fetched OpenAlex results for {len(queries)} queries{slice_note}"
                f" ({search_count} searches{fail_note})"
            ),
        )


def _clear_raw_results(raw_dir: Path) -> None:
    for path in raw_dir.glob("*.json"):
        path.unlink()


def _write_dry_run_result(
    raw_dir: Path,
    item: dict,
    slice_cfg: YearSliceConfig,
    openalex_cfg,
) -> None:
    query_id = item["id"]
    suffix = openalex_cfg.slice_result_suffix(slice_cfg)
    write_json(
        raw_dir / f"{query_id}{suffix}.json",
        {
            "provider": "openalex",
            "query_id": query_id,
            "query": item["query"],
            "year_min": slice_cfg.year_min,
            "year_max": slice_cfg.year_max,
            "results": [
                {
                    "id": "https://openalex.org/W0000000000",
                    "display_name": "Example primary results from a peer-reviewed study",
                    "doi": "https://doi.org/10.1038/nature00000",
                    "publication_year": slice_cfg.year_min or 2020,
                    "cited_by_count": 120,
                    "abstract_inverted_index": {
                        "We": [0],
                        "report": [1],
                        "measurements.": [2],
                    },
                    "authorships": [
                        {"author": {"display_name": "A. Author"}},
                    ],
                    "primary_location": {
                        "source": {"display_name": "Nature"},
                    },
                    "open_access": {"is_oa": False},
                    "_relevance_rank": 1,
                }
            ],
            "dry_run": True,
        },
    )
