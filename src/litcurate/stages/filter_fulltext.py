"""Stage: LLM fulltext relevance gate before extraction."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from litcurate.clients.llm import llm_chat, llm_require_configured
from litcurate.config import resolve_stage_llm
from litcurate.gate_papers import load_cleaned_paper_ids
from litcurate.llm_json import parse_filter_decisions
from litcurate.stages.base import StageContext, StageResult
from litcurate.stages.utils import read_json, read_json_if_valid, write_json

logger = logging.getLogger(__name__)

CHECKPOINT_NAME = "fulltext_filter.checkpoint.json"


class FilterFulltextStage:
    name = "filter_fulltext"
    description = "LLM screening of cleaned markdown before extraction"

    def should_skip(self, ctx: StageContext) -> bool:
        manifest = ctx.artifact("fulltext_filter_manifest.json")
        return manifest.exists() and ctx.store.is_stage_completed(ctx.run_id, self.name)

    def run(self, ctx: StageContext) -> StageResult:
        cfg = ctx.config.fulltext_filter
        manifest_path = ctx.artifact("fulltext_filter_manifest.json")
        checkpoint_path = ctx.artifact(CHECKPOINT_NAME)

        pre_manifest = read_json_if_valid(ctx.artifact("pre_extract_manifest.json"))
        if pre_manifest is None:
            raise FileNotFoundError("pre_extract_manifest.json not found — run pre_extract first")

        eligible_ids = {
            item["paper_id"]
            for item in pre_manifest.get("papers", [])
            if item.get("status") == "pass"
        }

        papers: list[dict] = []
        for paper_id in load_cleaned_paper_ids(ctx):
            if paper_id not in eligible_ids:
                papers.append(
                    {
                        "paper_id": paper_id,
                        "keep": False,
                        "status": "skipped",
                        "reason": "skipped by pre_extract",
                    }
                )

        if not cfg.enabled:
            for paper_id in sorted(eligible_ids):
                papers.append(
                    {
                        "paper_id": paper_id,
                        "keep": True,
                        "status": "keep",
                        "reason": "fulltext_filter disabled",
                    }
                )
            write_json(manifest_path, {"papers": papers})
            _clear_checkpoint(checkpoint_path)
            return StageResult(
                artifact_path=manifest_path,
                message=f"Fulltext filter passthrough for {len(eligible_ids)} papers",
                papers_touched=len(eligible_ids),
            )

        if not cfg.criteria.strip():
            raise ValueError("fulltext_filter.criteria is required when fulltext_filter.enabled is true")

        if ctx.dry_run:
            for paper_id in sorted(eligible_ids):
                papers.append(
                    {
                        "paper_id": paper_id,
                        "keep": True,
                        "status": "keep",
                        "reason": "dry_run — kept all eligible",
                    }
                )
            write_json(manifest_path, {"papers": papers})
            _clear_checkpoint(checkpoint_path)
            return StageResult(
                artifact_path=manifest_path,
                message=f"Fulltext filter dry-run kept {len(eligible_ids)} papers",
                papers_touched=len(eligible_ids),
            )

        stage_llm = resolve_stage_llm(ctx.config.llm, cfg)
        llm_require_configured(stage_llm, stage=self.name)

        if ctx.force:
            _clear_checkpoint(checkpoint_path)

        records = _build_records(ctx, sorted(eligible_ids), cfg.input_max_chars)
        paper_ids = [row["paper_id"] for row in records]
        decisions = _load_checkpoint_decisions(checkpoint_path, paper_ids, cfg.criteria)
        decision_map = {item["paper_id"]: item for item in decisions}
        batches_run = 0
        batches_skipped = 0

        for start in range(0, len(records), cfg.batch_size):
            batch = records[start : start + cfg.batch_size]
            batch_num = start // cfg.batch_size + 1
            if _batch_is_complete(batch, decision_map):
                batches_skipped += 1
                continue

            pending = [row for row in batch if row["paper_id"] not in decision_map]
            for item in _filter_batch_with_retry(
                ctx=ctx,
                criteria=cfg.criteria,
                batch=pending,
                model=cfg.model,
                max_tokens=cfg.max_tokens,
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
                filter_criteria=cfg.criteria,
            )
            batches_run += 1

        pending_count = 0
        for row in records:
            decision = decision_map.get(
                row["paper_id"],
                _pending_decision(row["paper_id"], "no decision"),
            )
            status = str(decision.get("status") or "decided")
            keep_val = decision.get("keep")
            if status == "pending" or keep_val is None:
                papers.append(
                    {
                        "paper_id": row["paper_id"],
                        "keep": False,
                        "status": "pending",
                        "reason": str(decision.get("reason", "pending")),
                    }
                )
                pending_count += 1
            else:
                keep = bool(keep_val)
                papers.append(
                    {
                        "paper_id": row["paper_id"],
                        "keep": keep,
                        "status": "keep" if keep else "drop",
                        "reason": str(decision.get("reason", "")),
                    }
                )

        write_json(manifest_path, {"papers": papers})
        _clear_checkpoint(checkpoint_path)
        kept = sum(1 for item in papers if item.get("keep"))
        resume_note = f" ({batches_skipped} batches resumed)" if batches_skipped else ""
        pending_note = f", {pending_count} pending" if pending_count else ""
        return StageResult(
            artifact_path=manifest_path,
            message=(
                f"Fulltext filter kept {kept} / {len(papers)} papers"
                f"{pending_note}{resume_note}"
            ),
            papers_touched=kept,
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

    prompt = _build_fulltext_filter_prompt(criteria, batch)
    try:
        response = llm_chat(
            ctx,
            stage_name=FilterFulltextStage.name,
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
                "filter_fulltext %s failed for single paper %s (%s); marking pending",
                label_prefix,
                paper_id,
                exc,
            )
            return [_pending_decision(paper_id, f"llm failed: {exc}")]
        logger.warning(
            "filter_fulltext %s failed (%s); splitting batch of %d",
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
    for item in got.values():
        item.setdefault("status", "decided")
    missing = [row for row in batch if str(row["paper_id"]) not in got]

    if not missing:
        if response.truncated:
            logger.warning(
                "filter_fulltext %s reported truncated but all %d decisions parsed; accepting",
                label_prefix,
                len(got),
            )
        return list(got.values())

    logger.warning(
        "filter_fulltext %s incomplete (got %d/%d truncated=%s); retrying %d missing",
        label_prefix,
        len(got),
        len(batch),
        response.truncated,
        len(missing),
    )
    if len(missing) == 1 and len(batch) == 1:
        paper_id = str(batch[0].get("paper_id") or "")
        logger.warning(
            "filter_fulltext %s failed for single paper %s (truncated=%s); marking pending",
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


def _build_fulltext_filter_prompt(criteria: str, batch: list[dict[str, Any]]) -> str:
    return (
        f"Filter criteria:\n{criteria}\n\n"
        "For each paper excerpt, decide keep true/false with a short reason "
        "(under 20 words).\n"
        f"Papers JSON:\n{json.dumps(batch, indent=2)}\n\n"
        'Return JSON: {"decisions": [{"paper_id": "...", "keep": true, "reason": "..."}]}'
    )


def _build_records(
    ctx: StageContext,
    paper_ids: list[str],
    input_max_chars: int,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    clean_manifest = read_json(ctx.artifact("clean_manifest.json"))
    path_by_id = {
        item["paper_id"]: item["path"]
        for item in clean_manifest.get("cleaned", [])
        if item.get("status") == "success"
    }
    for paper_id in paper_ids:
        md_path = ctx.resolve_manifest_path(
            path_by_id[paper_id],
            ctx.artifact("markdown_clean", f"{paper_id}.md"),
        )
        excerpt = md_path.read_text(encoding="utf-8")[:input_max_chars]
        records.append({"paper_id": paper_id, "excerpt": excerpt})
    return records


def _clear_checkpoint(path: Path) -> None:
    if path.exists():
        path.unlink()


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


def _batch_is_complete(batch: list[dict[str, Any]], decision_map: dict[str, dict[str, Any]]) -> bool:
    return all(row["paper_id"] in decision_map for row in batch)
