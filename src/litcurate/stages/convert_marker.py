"""Stage 7: Convert PDFs to Markdown using Marker."""

from __future__ import annotations

from pathlib import Path

from litcurate.constants import PaperStageStatus
from litcurate.stages.base import StageContext, StageResult
from litcurate.stages.utils import read_json, write_json


class ConvertMarkerStage:
    name = "convert_marker"
    description = "Convert downloaded PDFs to Markdown with Marker"

    def should_skip(self, ctx: StageContext) -> bool:
        manifest = ctx.artifact("convert_manifest.json")
        return manifest.exists() and ctx.store.is_stage_completed(ctx.run_id, self.name)

    def run(self, ctx: StageContext) -> StageResult:
        download_manifest = ctx.artifact("download_manifest.json")
        if not download_manifest.exists():
            raise FileNotFoundError("download_manifest.json not found")

        payload = read_json(download_manifest)
        markdown_dir = ctx.artifact("markdown")
        markdown_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = ctx.artifact("convert_manifest.json")
        manifest: list[dict] = []
        success = 0

        for item in payload.get("downloads", []):
            if item.get("status") != "success":
                continue
            paper_id = item["paper_id"]
            pdf_path = _resolve_pdf_path(ctx, paper_id, item.get("path"))
            md_path = markdown_dir / f"{paper_id}.md"

            if md_path.exists() and md_path.stat().st_size > 0:
                manifest.append(
                    {
                        "paper_id": paper_id,
                        "status": "success",
                        "source": "cached",
                        "path": ctx.store_path(md_path),
                    }
                )
                ctx.store.update_paper_stage(
                    ctx.run_id, paper_id, "convert_status", PaperStageStatus.SUCCESS
                )
                success += 1
                continue

            ctx.store.update_paper_stage(
                ctx.run_id, paper_id, "convert_status", PaperStageStatus.RUNNING
            )

            if ctx.dry_run:
                md_path.write_text(
                    f"# Dry-run markdown for {paper_id}\n\n"
                    "## Abstract\nExample measurements for the user goal.\n\n"
                    "## Results\nparameter = 42 units.\n",
                    encoding="utf-8",
                )
                manifest.append(
                    {
                        "paper_id": paper_id,
                        "status": "success",
                        "source": "dry_run",
                        "path": ctx.store_path(md_path),
                    }
                )
                ctx.store.update_paper_stage(
                    ctx.run_id, paper_id, "convert_status", PaperStageStatus.SUCCESS
                )
                success += 1
                continue

            try:
                _convert_with_marker(pdf_path, md_path, ctx.config.conversion.device)
                manifest.append(
                    {
                        "paper_id": paper_id,
                        "status": "success",
                        "source": "marker",
                        "path": ctx.store_path(md_path),
                    }
                )
                ctx.store.update_paper_stage(
                    ctx.run_id, paper_id, "convert_status", PaperStageStatus.SUCCESS
                )
                success += 1
            except Exception as exc:
                manifest.append(
                    {"paper_id": paper_id, "status": "failed", "error": str(exc)}
                )
                ctx.store.update_paper_stage(
                    ctx.run_id,
                    paper_id,
                    "convert_status",
                    PaperStageStatus.FAILED,
                    error=str(exc),
                )

        write_json(manifest_path, {"conversions": manifest})
        return StageResult(
            artifact_path=manifest_path,
            message=f"Converted {success} PDFs to markdown",
            papers_touched=success,
        )


def _resolve_pdf_path(ctx: StageContext, paper_id: str, stored_path: str | None) -> Path:
    """Resolve PDF location from manifest, falling back to the standard artifact path."""
    default = ctx.artifact("pdfs", f"{paper_id}.pdf")
    if not stored_path:
        return default
    resolved = ctx.resolve_path(stored_path)
    if resolved.exists():
        return resolved
    return default


def _convert_with_marker(pdf_path: Path, md_path: Path, device: str) -> None:
    import os

    from marker.converters.pdf import PdfConverter
    from marker.models import create_model_dict
    from marker.output import text_from_rendered

    if device and device != "auto":
        os.environ["TORCH_DEVICE"] = device

    config = {"pdftext_workers": 1}
    artifact_dict = create_model_dict()
    converter = PdfConverter(artifact_dict=artifact_dict, config=config)
    rendered = converter(str(pdf_path))
    text, _, _ = text_from_rendered(rendered)
    md_path.write_text(text, encoding="utf-8")
