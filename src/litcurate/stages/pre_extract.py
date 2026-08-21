"""Stage 8b: Regex gate on cleaned markdown before LLM extraction."""

from __future__ import annotations

from litcurate.pre_extract_gate import passes_pre_extract, score_regex_signals
from litcurate.stages.base import StageContext, StageResult
from litcurate.stages.utils import read_json, write_json


class PreExtractStage:
    name = "pre_extract"
    description = "Free regex gate on cleaned markdown before extraction"

    def should_skip(self, ctx: StageContext) -> bool:
        manifest = ctx.artifact("pre_extract_manifest.json")
        return manifest.exists() and ctx.store.is_stage_completed(ctx.run_id, self.name)

    def run(self, ctx: StageContext) -> StageResult:
        clean_manifest = ctx.artifact("clean_manifest.json")
        if not clean_manifest.exists():
            raise FileNotFoundError("clean_manifest.json not found")

        payload = read_json(clean_manifest)
        manifest_path = ctx.artifact("pre_extract_manifest.json")
        cfg = ctx.config.pre_extract
        papers: list[dict] = []
        passed = 0
        skipped = 0

        for item in payload.get("cleaned", []):
            if item.get("status") != "success":
                continue
            paper_id = item["paper_id"]
            md_path = ctx.resolve_manifest_path(
                item["path"],
                ctx.artifact("markdown_clean", f"{paper_id}.md"),
            )

            if not cfg.enabled:
                papers.append(
                    {
                        "paper_id": paper_id,
                        "status": "pass",
                        "reason": "pre_extract disabled",
                        "signal_hits": 0,
                    }
                )
                passed += 1
                continue

            markdown = md_path.read_text(encoding="utf-8")
            ok, reason = passes_pre_extract(markdown, cfg)
            hits, _ = score_regex_signals(markdown, cfg)
            status = "pass" if ok else "skip"
            papers.append(
                {
                    "paper_id": paper_id,
                    "status": status,
                    "reason": reason,
                    "signal_hits": hits,
                }
            )
            if ok:
                passed += 1
            else:
                skipped += 1

        write_json(manifest_path, {"papers": papers})
        if cfg.enabled:
            message = f"Pre-extract: {passed} pass, {skipped} skip"
        else:
            message = f"Pre-extract passthrough for {passed} papers"
        return StageResult(
            artifact_path=manifest_path,
            message=message,
            papers_touched=passed,
        )
