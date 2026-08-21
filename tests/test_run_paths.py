"""Tests for portable run-relative artifact paths."""

from __future__ import annotations

import json
from pathlib import Path

from litcurate.config import load_config
from litcurate.paths import (
    normalize_run_manifests,
    normalize_stored_path,
    resolve_run_path,
    rewrite_manifest_paths,
    store_run_path,
)
from litcurate.run_store import open_run_store
from litcurate.stages.base import StageContext
from litcurate.stages.convert_marker import _resolve_pdf_path


def test_store_and_resolve_relative_path(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "abc123"
    artifact = run_dir / "artifacts" / "pdfs" / "paper.pdf"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"%PDF")

    stored = store_run_path(run_dir, artifact)
    assert stored == "artifacts/pdfs/paper.pdf"
    assert resolve_run_path(run_dir, stored) == artifact.resolve()


def test_resolve_absolute_path_falls_back_to_run_relative(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "abc123"
    artifact = run_dir / "artifacts" / "pdfs" / "paper.pdf"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"%PDF")

    stale = "/other/machine/runs/abc123/artifacts/pdfs/paper.pdf"
    assert resolve_run_path(run_dir, stale) == artifact.resolve()


def test_normalize_stored_path_extracts_artifacts_suffix(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "abc123"
    stored = "/Users/me/old/LitCurate/runs/abc123/artifacts/markdown/paper.md"
    assert normalize_stored_path(run_dir, stored) == "artifacts/markdown/paper.md"


def test_rewrite_manifest_paths(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "abc123"
    payload = {
        "conversions": [
            {
                "paper_id": "paper",
                "path": "/Users/me/runs/abc123/artifacts/markdown/paper.md",
            }
        ]
    }
    changed = rewrite_manifest_paths(run_dir, payload)
    assert changed == 1
    assert payload["conversions"][0]["path"] == "artifacts/markdown/paper.md"


def test_normalize_run_manifests_writes_files(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "abc123"
    manifest = run_dir / "artifacts" / "convert_manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "conversions": [
                    {
                        "paper_id": "paper",
                        "path": "/old/path/runs/abc123/artifacts/markdown/paper.md",
                    }
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    results = normalize_run_manifests(run_dir)
    assert results["convert_manifest.json"] == 1
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["conversions"][0]["path"] == "artifacts/markdown/paper.md"


def test_resolve_absolute_path_without_local_file(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "abc123"
    absolute = "/other/machine/runs/abc123/artifacts/pdfs/paper.pdf"
    assert resolve_run_path(run_dir, absolute) == (run_dir / "artifacts/pdfs/paper.pdf").resolve()


def test_resolve_pdf_path_falls_back_to_standard_location(tmp_path: Path) -> None:
    config_path = Path(__file__).resolve().parents[1] / "configs" / "config.yaml"
    config = load_config(config_path)
    run_dir = tmp_path / "runs" / "abc123"
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True)
    store = open_run_store(run_dir)
    ctx = StageContext(
        run_id="abc123",
        run_dir=run_dir,
        artifacts_dir=artifacts_dir,
        config=config,
        store=store,
    )

    pdf_path = ctx.artifact("pdfs", "10.1000_example.pdf")
    pdf_path.write_bytes(b"%PDF")

    stale_absolute = "/Users/me/old/runs/abc123/artifacts/pdfs/10.1000_example.pdf"
    resolved = _resolve_pdf_path(ctx, "10.1000_example", stale_absolute)
    assert resolved == pdf_path


def test_dry_run_manifest_uses_relative_paths(tmp_path: Path) -> None:
    from litcurate.pipeline import PipelineRunner

    config_path = Path(__file__).resolve().parents[1] / "configs" / "config.yaml"
    runner = PipelineRunner(config_path, runs_dir=tmp_path / "runs")
    run_id = runner.start_new_run()

    run_dir = tmp_path / "runs" / run_id
    download_manifest = json.loads((run_dir / "artifacts" / "download_manifest.json").read_text())
    for entry in download_manifest["downloads"]:
        if entry.get("status") == "success" and "path" in entry:
            assert not Path(entry["path"]).is_absolute()
            assert entry["path"].startswith("artifacts/")
