"""Helpers for pre-extract and fulltext gate manifests."""

from __future__ import annotations

from litcurate.config import PipelineConfig
from litcurate.stages.base import StageContext
from litcurate.stages.utils import read_json_if_valid


def load_cleaned_paper_ids(ctx: StageContext) -> list[str]:
    payload = read_json_if_valid(ctx.artifact("clean_manifest.json"))
    if not payload:
        raise FileNotFoundError("clean_manifest.json not found")
    return [
        item["paper_id"]
        for item in payload.get("cleaned", [])
        if item.get("status") == "success"
    ]


def paper_passes_gates(ctx: StageContext, paper_id: str) -> tuple[bool, str]:
    """Return whether a paper should proceed to extraction."""
    config: PipelineConfig = ctx.config

    if config.pre_extract.enabled or _manifest_exists(ctx, "pre_extract_manifest.json"):
        pre = read_json_if_valid(ctx.artifact("pre_extract_manifest.json"))
        if pre:
            decision = _decision_map(pre.get("papers", [])).get(paper_id)
            if decision and decision.get("status") != "pass":
                return False, decision.get("reason", "failed pre_extract")

    if config.fulltext_filter.enabled or _manifest_exists(ctx, "fulltext_filter_manifest.json"):
        ft = read_json_if_valid(ctx.artifact("fulltext_filter_manifest.json"))
        if ft:
            decision = _decision_map(ft.get("papers", [])).get(paper_id)
            if decision and not decision.get("keep", False):
                return False, decision.get("reason", "failed fulltext_filter")

    return True, "passed gates"


def _manifest_exists(ctx: StageContext, name: str) -> bool:
    path = ctx.artifact(name)
    return path.exists() and path.stat().st_size > 0


def _decision_map(items: list[dict]) -> dict[str, dict]:
    return {item["paper_id"]: item for item in items if "paper_id" in item}
