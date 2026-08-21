"""Stage 8: Strip irrelevant sections from Markdown."""

from __future__ import annotations

from litcurate.constants import PaperStageStatus
from litcurate.markdown_clean import clean_markdown, markdown_strip_stats
from litcurate.stages.base import StageContext, StageResult
from litcurate.stages.utils import read_json, write_json


class CleanMarkdownStage:
    name = "clean_markdown"
    description = "Remove references and other low-value sections from markdown"

    def should_skip(self, ctx: StageContext) -> bool:
        manifest = ctx.artifact("clean_manifest.json")
        return manifest.exists() and ctx.store.is_stage_completed(ctx.run_id, self.name)

    def run(self, ctx: StageContext) -> StageResult:
        convert_manifest = ctx.artifact("convert_manifest.json")
        if not convert_manifest.exists():
            raise FileNotFoundError("convert_manifest.json not found")

        payload = read_json(convert_manifest)
        clean_dir = ctx.artifact("markdown_clean")
        clean_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = ctx.artifact("clean_manifest.json")
        cfg = ctx.config.markdown_clean
        manifest: list[dict] = []
        success = 0
        heavy_strip_count = 0

        for item in payload.get("conversions", []):
            if item.get("status") != "success":
                continue
            paper_id = item["paper_id"]
            source_path = ctx.resolve_manifest_path(
                item["path"],
                ctx.artifact("markdown", f"{paper_id}.md"),
            )
            dest_path = clean_dir / f"{paper_id}.md"

            if (
                not ctx.force
                and dest_path.exists()
                and dest_path.stat().st_size > 0
            ):
                entry = _manifest_entry_from_files(
                    paper_id=paper_id,
                    source_path=source_path,
                    dest_path=dest_path,
                    ctx=ctx,
                    heavy_strip_fraction=cfg.heavy_strip_fraction,
                    cached=True,
                )
                manifest.append(entry)
                ctx.store.update_paper_stage(
                    ctx.run_id, paper_id, "clean_status", PaperStageStatus.SUCCESS
                )
                success += 1
                if entry.get("heavy_strip"):
                    heavy_strip_count += 1
                continue

            ctx.store.update_paper_stage(
                ctx.run_id, paper_id, "clean_status", PaperStageStatus.RUNNING
            )

            try:
                raw = source_path.read_text(encoding="utf-8")
                cleaned = clean_markdown(raw, cfg)
                dest_path.write_text(cleaned, encoding="utf-8")
                entry = _manifest_entry_from_text(
                    paper_id=paper_id,
                    raw=raw,
                    cleaned=cleaned,
                    dest_path=dest_path,
                    ctx=ctx,
                    heavy_strip_fraction=cfg.heavy_strip_fraction,
                )
                manifest.append(entry)
                ctx.store.update_paper_stage(
                    ctx.run_id, paper_id, "clean_status", PaperStageStatus.SUCCESS
                )
                success += 1
                if entry.get("heavy_strip"):
                    heavy_strip_count += 1
            except Exception as exc:
                manifest.append(
                    {"paper_id": paper_id, "status": "failed", "error": str(exc)}
                )
                ctx.store.update_paper_stage(
                    ctx.run_id,
                    paper_id,
                    "clean_status",
                    PaperStageStatus.FAILED,
                    error=str(exc),
                )

        write_json(
            manifest_path,
            {
                "cleaned": manifest,
                "heavy_strip_fraction": cfg.heavy_strip_fraction,
                "heavy_strip_count": heavy_strip_count,
            },
        )
        suffix = f", {heavy_strip_count} heavy strip flags" if heavy_strip_count else ""
        return StageResult(
            artifact_path=manifest_path,
            message=f"Cleaned markdown for {success} papers{suffix}",
            papers_touched=success,
        )


def _manifest_entry_from_text(
    *,
    paper_id: str,
    raw: str,
    cleaned: str,
    dest_path,
    ctx: StageContext,
    heavy_strip_fraction: float,
) -> dict:
    stats = markdown_strip_stats(
        raw,
        cleaned,
        heavy_strip_fraction=heavy_strip_fraction,
    )
    entry = {
        "paper_id": paper_id,
        "status": "success",
        "path": ctx.store_path(dest_path),
        **stats,
    }
    if stats["heavy_strip"]:
        entry["warning"] = (
            f"stripped {stats['strip_fraction']:.0%} of content "
            f"(>{heavy_strip_fraction:.0%} threshold)"
        )
    return entry


def _manifest_entry_from_files(
    *,
    paper_id: str,
    source_path,
    dest_path,
    ctx: StageContext,
    heavy_strip_fraction: float,
    cached: bool,
) -> dict:
    raw = source_path.read_text(encoding="utf-8")
    cleaned = dest_path.read_text(encoding="utf-8")
    entry = _manifest_entry_from_text(
        paper_id=paper_id,
        raw=raw,
        cleaned=cleaned,
        dest_path=dest_path,
        ctx=ctx,
        heavy_strip_fraction=heavy_strip_fraction,
    )
    if cached:
        entry["source"] = "cached"
    return entry
