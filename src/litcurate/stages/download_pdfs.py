"""Stage 6: Download PDFs via metadata APIs and direct HTTP."""

from __future__ import annotations

import logging
import time
from contextlib import nullcontext
from pathlib import Path
from typing import Any

from litcurate.clients.pdf_download import download_pdf_bytes, save_pdf
from litcurate.constants import PaperStageStatus
from litcurate.env import get_env
from litcurate.stages.base import StageContext, StageResult
from litcurate.stages.utils import read_json_if_valid, read_parquet, write_json

CHECKPOINT_NAME = "download_manifest.checkpoint.json"
logger = logging.getLogger(__name__)


class DownloadPdfsStage:
    name = "download_pdfs"
    description = "Download PDFs for filtered papers"

    def should_skip(self, ctx: StageContext) -> bool:
        manifest = ctx.artifact("download_manifest.json")
        return manifest.exists() and ctx.store.is_stage_completed(ctx.run_id, self.name)

    def run(self, ctx: StageContext) -> StageResult:
        filtered_path = ctx.artifact("papers_filtered.parquet")
        if not filtered_path.exists():
            raise FileNotFoundError("papers_filtered.parquet not found")

        papers = read_parquet(filtered_path).to_dict(orient="records")
        pdf_dir = ctx.artifact("pdfs")
        pdf_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = ctx.artifact("download_manifest.json")
        checkpoint_path = ctx.artifact(CHECKPOINT_NAME)

        if ctx.force:
            _clear_checkpoint(checkpoint_path)

        manifest = _load_checkpoint(checkpoint_path, papers)
        completed_ids = {entry["paper_id"] for entry in manifest if entry.get("status") == "success"}
        skipped_ids = {entry["paper_id"] for entry in manifest if entry.get("status") == "skipped"}
        success_count = sum(1 for entry in manifest if entry.get("status") == "success")

        unpaywalled_only = ctx.config.download.unpaywalled_only
        unpaywall_email = get_env("UNPAYWALL_EMAIL")

        with nullcontext():
            for paper in papers:
                paper_id = paper["paper_id"]
                doi = paper.get("doi")
                pdf_path = pdf_dir / f"{paper_id}.pdf"

                if paper_id in completed_ids and pdf_path.exists() and pdf_path.stat().st_size > 0:
                    continue

                if unpaywalled_only and paper_id in skipped_ids:
                    continue

                if unpaywalled_only and not paper.get("is_oa"):
                    entry = {
                        "paper_id": paper_id,
                        "doi": doi,
                        "status": "skipped",
                        "reason": "not_open_access",
                    }
                    manifest = _upsert_manifest_entry(manifest, entry)
                    _save_checkpoint(checkpoint_path, papers, manifest)
                    ctx.store.update_paper_stage(
                        ctx.run_id, paper_id, "download_status", PaperStageStatus.SKIPPED
                    )
                    continue

                existing = _manifest_entry_for(manifest, paper_id)
                if pdf_path.exists() and pdf_path.stat().st_size > 0:
                    entry = {
                        "paper_id": paper_id,
                        "doi": doi,
                        "status": "success",
                        "source": "cached",
                        "path": ctx.store_path(pdf_path),
                    }
                    manifest = _upsert_manifest_entry(manifest, entry)
                    _save_checkpoint(checkpoint_path, papers, manifest)
                    ctx.store.update_paper_stage(
                        ctx.run_id, paper_id, "download_status", PaperStageStatus.SUCCESS
                    )
                    if existing is None or existing.get("status") != "success":
                        success_count += 1
                    continue

                ctx.store.update_paper_stage(
                    ctx.run_id, paper_id, "download_status", PaperStageStatus.RUNNING
                )

                if ctx.dry_run:
                    pdf_path.write_bytes(b"%PDF-1.4 dry-run placeholder")
                    entry = {
                        "paper_id": paper_id,
                        "doi": doi,
                        "status": "success",
                        "source": "dry_run",
                        "path": ctx.store_path(pdf_path),
                    }
                    manifest = _upsert_manifest_entry(manifest, entry)
                    _save_checkpoint(checkpoint_path, papers, manifest)
                    ctx.store.update_paper_stage(
                        ctx.run_id, paper_id, "download_status", PaperStageStatus.SUCCESS
                    )
                    success_count += 1
                    continue

                try:
                    outcome = download_pdf_bytes(
                        doi or "",
                        unpaywall_email=unpaywall_email,
                        oa_only=unpaywalled_only,
                    )
                    if outcome.succeeded and outcome.pdf_bytes is not None:
                        save_pdf(pdf_path, outcome.pdf_bytes)
                        entry = {
                            "paper_id": paper_id,
                            "doi": doi,
                            "status": "success",
                            "source": outcome.source,
                            "path": ctx.store_path(pdf_path),
                        }
                        manifest = _upsert_manifest_entry(manifest, entry)
                        ctx.store.update_paper_stage(
                            ctx.run_id, paper_id, "download_status", PaperStageStatus.SUCCESS
                        )
                        success_count += 1
                    else:
                        entry = {
                            "paper_id": paper_id,
                            "doi": doi,
                            "status": "failed",
                            "error": outcome.error or "download failed",
                        }
                        manifest = _upsert_manifest_entry(manifest, entry)
                        ctx.store.update_paper_stage(
                            ctx.run_id,
                            paper_id,
                            "download_status",
                            PaperStageStatus.FAILED,
                            error=entry.get("error"),
                        )
                except Exception as exc:
                    entry = {
                        "paper_id": paper_id,
                        "doi": doi,
                        "status": "failed",
                        "error": str(exc),
                    }
                    manifest = _upsert_manifest_entry(manifest, entry)
                    ctx.store.update_paper_stage(
                        ctx.run_id,
                        paper_id,
                        "download_status",
                        PaperStageStatus.FAILED,
                        error=str(exc),
                    )

                _save_checkpoint(checkpoint_path, papers, manifest)
                time.sleep(ctx.config.download.request_delay_seconds)

        write_json(manifest_path, {"downloads": manifest})
        _clear_checkpoint(checkpoint_path)
        return StageResult(
            artifact_path=manifest_path,
            message=f"Downloaded {success_count}/{len(papers)} PDFs",
            papers_touched=len(papers),
        )


def _paper_ids(papers: list[dict[str, Any]]) -> list[str]:
    return [paper["paper_id"] for paper in papers]


def _load_checkpoint(path: Path, papers: list[dict[str, Any]]) -> list[dict]:
    payload = read_json_if_valid(path)
    if payload is None:
        if path.exists():
            logger.warning("Ignoring corrupt or empty checkpoint: %s", path)
            path.unlink(missing_ok=True)
        return []
    if payload.get("paper_ids") != _paper_ids(papers):
        return []
    downloads = payload.get("downloads", [])
    return downloads if isinstance(downloads, list) else []


def _save_checkpoint(path: Path, papers: list[dict[str, Any]], manifest: list[dict]) -> None:
    write_json(
        path,
        {
            "paper_ids": _paper_ids(papers),
            "downloads": manifest,
        },
    )


def _clear_checkpoint(path: Path) -> None:
    if path.exists():
        path.unlink()


def _manifest_entry_for(manifest: list[dict], paper_id: str) -> dict | None:
    for entry in manifest:
        if entry.get("paper_id") == paper_id:
            return entry
    return None


def _upsert_manifest_entry(manifest: list[dict], entry: dict) -> list[dict]:
    paper_id = entry["paper_id"]
    updated = [item for item in manifest if item.get("paper_id") != paper_id]
    updated.append(entry)
    return updated
