"""Ingest manually downloaded PDFs into an existing pipeline run."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from litcurate.constants import PaperStageStatus
from litcurate.doi import normalize_doi, paper_id_from_doi
from litcurate.paths import artifacts_directory, store_run_path
from litcurate.run_store import RunStore, open_run_store
from litcurate.stages.utils import read_json_if_valid, read_parquet, write_json


@dataclass
class IngestReport:
    ingested: list[dict[str, str]] = field(default_factory=list)
    already_success: list[str] = field(default_factory=list)
    unknown_files: list[str] = field(default_factory=list)
    invalid_files: list[str] = field(default_factory=list)
    dry_run: bool = False

    @property
    def ingested_count(self) -> int:
        return len(self.ingested)


def ingest_pdfs(
    run_dir: Path,
    *,
    from_dir: Path | None = None,
    dry_run: bool = False,
) -> IngestReport:
    """Register manually provided PDFs for papers in this run."""
    run_dir = run_dir.resolve()
    run_id = run_dir.name
    artifacts_dir = artifacts_directory(run_dir)
    filtered_path = artifacts_dir / "papers_filtered.parquet"
    if not filtered_path.exists():
        raise FileNotFoundError("papers_filtered.parquet not found — run filter_abstracts first")

    papers = read_parquet(filtered_path).to_dict(orient="records")
    paper_by_id = {paper["paper_id"]: paper for paper in papers}
    store = open_run_store(run_dir)

    manifest_path = artifacts_dir / "download_manifest.json"
    manifest_payload = read_json_if_valid(manifest_path) or {"downloads": []}
    manifest: list[dict] = list(manifest_payload.get("downloads", []))
    manifest_by_id = {
        entry["paper_id"]: entry for entry in manifest if entry.get("paper_id")
    }

    pdf_dir = artifacts_dir / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)

    source_dir = from_dir.resolve() if from_dir is not None else pdf_dir
    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")

    report = IngestReport(dry_run=dry_run)

    for source_path in sorted(source_path for source_path in source_dir.glob("*.pdf")):
        paper_id = _match_paper_id(source_path.name, paper_by_id)
        if paper_id is None:
            report.unknown_files.append(source_path.name)
            continue

        if not _is_valid_pdf(source_path):
            report.invalid_files.append(source_path.name)
            continue

        paper = paper_by_id[paper_id]
        existing = manifest_by_id.get(paper_id)
        if existing and existing.get("status") == "success":
            report.already_success.append(paper_id)
            continue

        dest_path = pdf_dir / f"{paper_id}.pdf"
        if not dry_run:
            _ensure_paper_record(store, run_id, paper)
            if source_path.resolve() != dest_path.resolve():
                shutil.copy2(source_path, dest_path)
            entry = {
                "paper_id": paper_id,
                "doi": paper.get("doi"),
                "status": "success",
                "source": "manual",
                "path": store_run_path(run_dir, dest_path),
            }
            manifest = _upsert_manifest_entry(manifest, entry)
            manifest_by_id[paper_id] = entry
            store.update_paper_stage(
                run_id,
                paper_id,
                "download_status",
                PaperStageStatus.SUCCESS,
            )

        report.ingested.append(
            {
                "paper_id": paper_id,
                "source_file": str(source_path),
                "dest": str(dest_path),
            }
        )

    if not dry_run and report.ingested:
        write_json(manifest_path, {"downloads": manifest})

    return report


def _match_paper_id(filename: str, paper_by_id: dict[str, dict]) -> str | None:
    stem = Path(filename).stem
    if stem in paper_by_id:
        return stem

    doi_candidate = normalize_doi(stem.replace("_", "/"))
    if doi_candidate:
        paper_id = paper_id_from_doi(doi_candidate)
        if paper_id in paper_by_id:
            return paper_id

    for paper_id, paper in paper_by_id.items():
        doi = normalize_doi(paper.get("doi"))
        if doi and paper_id_from_doi(doi) == stem:
            return paper_id

    return None


def _is_valid_pdf(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    with path.open("rb") as handle:
        header = handle.read(5)
    return header.startswith(b"%PDF")


def _ensure_paper_record(store: RunStore, run_id: str, paper: dict) -> None:
    store.upsert_paper(
        run_id,
        paper["paper_id"],
        doi=paper.get("doi"),
        title=paper.get("title"),
        metadata={
            "year": paper.get("year"),
            "score": paper.get("score"),
            "journal": paper.get("journal"),
        },
    )


def _upsert_manifest_entry(manifest: list[dict], entry: dict) -> list[dict]:
    paper_id = entry["paper_id"]
    updated = [item for item in manifest if item.get("paper_id") != paper_id]
    updated.append(entry)
    return updated
