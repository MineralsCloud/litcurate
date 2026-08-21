"""Stage 5: Filter papers by abstract relevance using LLM criteria."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from litcurate.clients.llm import llm_chat, llm_require_configured
from litcurate.config import resolve_stage_llm
from litcurate.llm_json import parse_filter_decisions
from litcurate.stages.base import StageContext, StageResult
from litcurate.stages.utils import read_json, read_parquet, write_json, write_parquet

logger = logging.getLogger(__name__)

CHECKPOINT_NAME = "filter_abstracts.checkpoint.json"


class FilterAbstractsStage:
    name = "filter_abstracts"
    description = "Keep papers whose abstracts match config criteria"

    def should_skip(self, ctx: StageContext) -> bool:
        output = ctx.artifact("papers_filtered.parquet")
        return output.exists() and ctx.store.is_stage_completed(ctx.run_id, self.name)

    def run(self, ctx: StageContext) -> StageResult:
        ranked_path = ctx.artifact("papers_ranked.parquet")
        if not ranked_path.exists():
            raise FileNotFoundError("papers_ranked.parquet not found")

        frame = read_parquet(ranked_path)
        output = ctx.artifact("papers_filtered.parquet")
        checkpoint_path = ctx.artifact(CHECKPOINT_NAME)
        criteria = ctx.config.abstract_filter.criteria

        if ctx.dry_run:
            frame = frame.copy()
            frame["keep"] = True
            frame["filter_reason"] = "dry_run — kept all"
            write_parquet(output, frame)
            _register_papers(ctx, frame)
            _clear_checkpoint(checkpoint_path)
            return StageResult(
                artifact_path=output,
                message=f"Filtered to {len(frame)} papers (dry run)",
                papers_touched=len(frame),
            )

        stage_llm = resolve_stage_llm(ctx.config.llm, ctx.config.abstract_filter)
        llm_require_configured(stage_llm, stage=self.name)

        model = ctx.config.abstract_filter.model
        batch_size = ctx.config.abstract_filter.batch_size
        max_tokens = ctx.config.abstract_filter.max_tokens
        records = frame.to_dict(orient="records")
        paper_ids = [row["paper_id"] for row in records]

        if ctx.force:
            _clear_checkpoint(checkpoint_path)

        decisions = _load_checkpoint_decisions(checkpoint_path, paper_ids, criteria)
        decision_map = {item["paper_id"]: item for item in decisions}
        batches_run = 0
        batches_skipped = 0

        for start in range(0, len(records), batch_size):
            batch = records[start : start + batch_size]
            batch_num = start // batch_size + 1
            if _batch_is_complete(batch, decision_map):
                batches_skipped += 1
                continue

            pending = [row for row in batch if row["paper_id"] not in decision_map]
            for item in _filter_batch_with_retry(
                ctx=ctx,
                criteria=criteria,
                batch=pending,
                model=model,
                max_tokens=max_tokens,
                stage_llm=stage_llm,
                label_prefix=f"batch_{batch_num}",
            ):
                decision_map[item["paper_id"]] = item

            decisions = list(decision_map.values())
            _save_checkpoint(
                checkpoint_path,
                paper_ids,
                decisions,
                batch_num,
                filter_criteria=criteria,
            )
            batches_run += 1

        keep_flags: list[bool | None] = []
        statuses: list[str] = []
        reasons: list[str] = []
        pending_count = 0
        for row in records:
            decision = decision_map.get(
                row["paper_id"],
                _pending_decision(row["paper_id"], "no decision"),
            )
            status = str(decision.get("status") or "decided")
            keep_val = decision.get("keep")
            if status == "pending" or keep_val is None:
                keep_flags.append(None)
                statuses.append("pending")
                pending_count += 1
            else:
                keep_flags.append(bool(keep_val))
                statuses.append("keep" if keep_val else "drop")
            reasons.append(str(decision.get("reason", "")))

        frame = frame.copy()
        frame["keep"] = keep_flags
        frame["filter_status"] = statuses
        frame["filter_reason"] = reasons
        filtered = frame[frame["keep"] == True].reset_index(drop=True)
        write_parquet(output, filtered)
        write_json(
            ctx.artifact("filter_abstracts_decisions.json"),
            {
                "filter_criteria": criteria,
                "decisions": list(decision_map.values()),
                "pending_count": pending_count,
                "kept_count": int((frame["keep"] == True).sum()),
                "dropped_count": int((frame["keep"] == False).sum()),
            },
        )
        _register_papers(ctx, filtered)
        _clear_checkpoint(checkpoint_path)

        resume_note = f" ({batches_skipped} batches resumed from checkpoint)" if batches_skipped else ""
        pending_note = f", {pending_count} pending" if pending_count else ""
        return StageResult(
            artifact_path=output,
            message=(
                f"Kept {len(filtered)} / {len(records)} papers"
                f"{pending_note}{resume_note}"
            ),
            papers_touched=len(filtered),
        )


def _filter_batch_with_retry(
    *,
    ctx: StageContext,
    criteria: str,
    batch: list[dict[str, Any]],
    model: str,
    max_tokens: int,
    stage_llm,
    label_prefix: str,
) -> list[dict[str, Any]]:
    """Filter a batch; on truncation/incomplete coverage, split and retry."""
    if not batch:
        return []

    prompt = _build_abstract_filter_prompt(criteria, batch)
    try:
        response = llm_chat(
            ctx,
            stage_name=FilterAbstractsStage.name,
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            label=label_prefix,
            llm=stage_llm,
        )
        decisions = parse_filter_decisions(response.text)
    except Exception as exc:
        if len(batch) == 1:
            paper_id = str(batch[0].get("paper_id") or "")
            logger.warning(
                "filter_abstracts %s failed for single paper %s (%s); marking pending",
                label_prefix,
                paper_id,
                exc,
            )
            return [_pending_decision(paper_id, f"llm failed: {exc}")]
        logger.warning(
            "filter_abstracts %s failed (%s); splitting batch of %d",
            label_prefix,
            exc,
            len(batch),
        )
        return _split_and_retry(
            ctx=ctx,
            criteria=criteria,
            batch=batch,
            model=model,
            max_tokens=max_tokens,
            stage_llm=stage_llm,
            label_prefix=label_prefix,
        )

    expected_ids = {str(row["paper_id"]) for row in batch}
    got = {
        item["paper_id"]: item
        for item in decisions
        if item["paper_id"] in expected_ids and item.get("status") != "pending"
    }
    # Normalize decided items
    for item in got.values():
        item.setdefault("status", "decided")
    missing = [row for row in batch if str(row["paper_id"]) not in got]

    if not missing:
        if response.truncated:
            logger.warning(
                "filter_abstracts %s reported truncated but all %d decisions parsed; accepting",
                label_prefix,
                len(got),
            )
        return list(got.values())

    logger.warning(
        "filter_abstracts %s incomplete (got %d/%d truncated=%s); retrying %d missing",
        label_prefix,
        len(got),
        len(batch),
        response.truncated,
        len(missing),
    )
    if len(missing) == 1 and len(batch) == 1:
        paper_id = str(batch[0].get("paper_id") or "")
        logger.warning(
            "filter_abstracts %s failed for single paper %s (truncated=%s); marking pending",
            label_prefix,
            paper_id,
            response.truncated,
        )
        return [
            _pending_decision(
                paper_id,
                f"llm returned no usable decision (truncated={response.truncated})",
            )
        ]

    recovered = list(got.values())
    recovered.extend(
        _split_and_retry(
            ctx=ctx,
            criteria=criteria,
            batch=missing,
            model=model,
            max_tokens=max_tokens,
            stage_llm=stage_llm,
            label_prefix=label_prefix,
        )
    )
    by_id = {item["paper_id"]: item for item in recovered}
    return [by_id[str(row["paper_id"])] for row in batch if str(row["paper_id"]) in by_id]


def _pending_decision(paper_id: str, reason: str) -> dict[str, Any]:
    return {
        "paper_id": str(paper_id),
        "keep": None,
        "status": "pending",
        "reason": reason,
    }


def _split_and_retry(
    *,
    ctx: StageContext,
    criteria: str,
    batch: list[dict[str, Any]],
    model: str,
    max_tokens: int,
    stage_llm,
    label_prefix: str,
) -> list[dict[str, Any]]:
    mid = max(1, len(batch) // 2)
    left = batch[:mid]
    right = batch[mid:]
    results: list[dict[str, Any]] = []
    results.extend(
        _filter_batch_with_retry(
            ctx=ctx,
            criteria=criteria,
            batch=left,
            model=model,
            max_tokens=max_tokens,
            stage_llm=stage_llm,
            label_prefix=f"{label_prefix}a",
        )
    )
    if right:
        results.extend(
            _filter_batch_with_retry(
                ctx=ctx,
                criteria=criteria,
                batch=right,
                model=model,
                max_tokens=max_tokens,
                stage_llm=stage_llm,
                label_prefix=f"{label_prefix}b",
            )
        )
    return results


def _abstract_batch_for_llm(batch: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Send only paper_id + abstract so the model cannot use OA/score/citations."""
    slim: list[dict[str, str]] = []
    for row in batch:
        abstract = row.get("abstract")
        slim.append(
            {
                "paper_id": str(row.get("paper_id") or ""),
                "abstract": "" if abstract is None else str(abstract),
            }
        )
    return slim


def _build_abstract_filter_prompt(criteria: str, batch: list[dict[str, Any]]) -> str:
    papers = _abstract_batch_for_llm(batch)
    return (
        f"Filter criteria:\n{criteria}\n\n"
        "Decide keep true/false using only each paper's abstract and the criteria above. "
        "Ignore any metadata not shown. Do not use open access, citation count, "
        "relevance score, journal prestige, or similar signals. "
        "Keep each reason under 20 words.\n"
        f"Papers JSON:\n{json.dumps(papers, indent=2)}\n\n"
        'Return JSON: {"decisions": [{"paper_id": "...", "keep": true, "reason": "..."}]}'
    )


def _load_checkpoint_decisions(
    path: Path,
    paper_ids: list[str],
    filter_criteria: str | None = None,
) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = read_json(path)
    if payload.get("paper_ids") != paper_ids:
        return []
    if filter_criteria is not None and payload.get("filter_criteria") != filter_criteria:
        return []
    decisions = payload.get("decisions", [])
    if not isinstance(decisions, list):
        return []
    return decisions


def _save_checkpoint(
    path: Path,
    paper_ids: list[str],
    decisions: list[dict[str, Any]],
    last_completed_batch: int,
    *,
    filter_criteria: str = "",
) -> None:
    write_json(
        path,
        {
            "filter_criteria": filter_criteria,
            "paper_ids": paper_ids,
            "decisions": decisions,
            "last_completed_batch": last_completed_batch,
        },
    )


def _clear_checkpoint(path: Path) -> None:
    if path.exists():
        path.unlink()


def _batch_is_complete(batch: list[dict[str, Any]], decision_map: dict[str, dict[str, Any]]) -> bool:
    return all(row["paper_id"] in decision_map for row in batch)


def _register_papers(ctx, frame: pd.DataFrame) -> None:
    for row in frame.to_dict(orient="records"):
        ctx.store.upsert_paper(
            ctx.run_id,
            row["paper_id"],
            doi=row.get("doi"),
            title=row.get("title"),
            metadata={
                "year": row.get("year"),
                "score": row.get("score"),
                "journal": row.get("journal"),
                "study_type": row.get("study_type"),
                "citation_count": row.get("citation_count"),
                "consensus_url": row.get("consensus_url"),
                "abstract_source": row.get("abstract_source"),
            },
        )
