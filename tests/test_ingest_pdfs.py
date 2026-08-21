"""Tests for manual PDF ingestion."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from litcurate.constants import PaperStageStatus
from litcurate.ingest_pdfs import ingest_pdfs
from litcurate.run_store import open_run_store
from litcurate.stages.utils import write_json, write_parquet


def _setup_run(tmp_path: Path, *, papers: list[dict], manifest: list[dict]) -> Path:
    run_dir = tmp_path / "runs" / "testrun"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    write_parquet(artifacts / "papers_filtered.parquet", pd.DataFrame(papers))
    write_json(artifacts / "download_manifest.json", {"downloads": manifest})

    store = open_run_store(run_dir)
    config_path = tmp_path / "config.yaml"
    config_path.write_text("run:\n  name: test\n  user_goal: test\n", encoding="utf-8")
    snapshot_path = run_dir / "config.snapshot.yaml"
    snapshot_path.write_text("run:\n  name: test\n  user_goal: test\n", encoding="utf-8")
    store.create_run(
        run_id="testrun",
        config_path=config_path,
        config_snapshot_path=snapshot_path,
        name="test",
        run_dir=run_dir,
    )
    for paper in papers:
        store.upsert_paper(
            "testrun",
            paper["paper_id"],
            doi=paper.get("doi"),
            title=paper.get("title"),
        )
        store.update_paper_stage(
            "testrun",
            paper["paper_id"],
            "download_status",
            PaperStageStatus.FAILED,
        )
    return run_dir


def test_ingest_from_external_dir_updates_manifest_and_db(tmp_path: Path) -> None:
    papers = [
        {
            "paper_id": "10.1029_2011jb008988",
            "doi": "10.1029/2011jb008988",
            "title": "Example paper",
            "keep": True,
        }
    ]
    manifest = [
        {
            "paper_id": "10.1029_2011jb008988",
            "doi": "10.1029/2011jb008988",
            "status": "failed",
            "error": "no OA PDF via HTTP",
        }
    ]
    run_dir = _setup_run(tmp_path, papers=papers, manifest=manifest)

    manual_dir = tmp_path / "manual"
    manual_dir.mkdir()
    (manual_dir / "10.1029_2011jb008988.pdf").write_bytes(b"%PDF-1.4 manual")

    report = ingest_pdfs(run_dir, from_dir=manual_dir)
    assert report.ingested_count == 1

    payload = json.loads((run_dir / "artifacts" / "download_manifest.json").read_text())
    entry = next(item for item in payload["downloads"] if item["paper_id"] == papers[0]["paper_id"])
    assert entry["status"] == "success"
    assert entry["source"] == "manual"
    assert entry["path"] == "artifacts/pdfs/10.1029_2011jb008988.pdf"
    assert (run_dir / "artifacts" / "pdfs" / "10.1029_2011jb008988.pdf").exists()

    store = open_run_store(run_dir)
    paper = next(p for p in store.list_papers("testrun") if p.paper_id == papers[0]["paper_id"])
    assert paper.download_status == PaperStageStatus.SUCCESS.value


def test_ingest_skipped_paper_from_pdfs_dir(tmp_path: Path) -> None:
    papers = [
        {
            "paper_id": "10.2138_am-1997-5-623",
            "doi": "10.2138/am-1997-5-623",
            "title": "Paywalled paper",
            "keep": True,
        }
    ]
    manifest = [
        {
            "paper_id": "10.2138_am-1997-5-623",
            "doi": "10.2138/am-1997-5-623",
            "status": "skipped",
            "reason": "not_open_access",
        }
    ]
    run_dir = _setup_run(tmp_path, papers=papers, manifest=manifest)
    pdf_dir = run_dir / "artifacts" / "pdfs"
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "10.2138_am-1997-5-623.pdf").write_bytes(b"%PDF-1.4 manual")

    report = ingest_pdfs(run_dir)
    assert report.ingested_count == 1

    payload = json.loads((run_dir / "artifacts" / "download_manifest.json").read_text())
    entry = payload["downloads"][0]
    assert entry["status"] == "success"
    assert entry["source"] == "manual"


def test_ingest_dry_run_does_not_modify_manifest(tmp_path: Path) -> None:
    papers = [
        {
            "paper_id": "10.1029_2011jb008988",
            "doi": "10.1029/2011jb008988",
            "title": "Example paper",
            "keep": True,
        }
    ]
    manifest = [
        {
            "paper_id": "10.1029_2011jb008988",
            "status": "failed",
            "error": "no OA PDF via HTTP",
        }
    ]
    run_dir = _setup_run(tmp_path, papers=papers, manifest=manifest)
    manual_dir = tmp_path / "manual"
    manual_dir.mkdir()
    (manual_dir / "10.1029_2011jb008988.pdf").write_bytes(b"%PDF-1.4 manual")

    before = (run_dir / "artifacts" / "download_manifest.json").read_text()
    report = ingest_pdfs(run_dir, from_dir=manual_dir, dry_run=True)
    after = (run_dir / "artifacts" / "download_manifest.json").read_text()

    assert report.ingested_count == 1
    assert before == after
    assert not (run_dir / "artifacts" / "pdfs" / "10.1029_2011jb008988.pdf").exists()


def test_ingest_matches_doi_style_filename(tmp_path: Path) -> None:
    papers = [
        {
            "paper_id": "10.1029_2011jb008988",
            "doi": "10.1029/2011jb008988",
            "title": "Example paper",
            "keep": True,
        }
    ]
    run_dir = _setup_run(tmp_path, papers=papers, manifest=[])
    manual_dir = tmp_path / "manual"
    manual_dir.mkdir()
    (manual_dir / "10.1029_2011jb008988.pdf").write_bytes(b"%PDF-1.4 manual")

    report = ingest_pdfs(run_dir, from_dir=manual_dir)
    assert report.ingested_count == 1
