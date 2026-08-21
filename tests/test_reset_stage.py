"""Tests for resetting pipeline stage outputs."""

from __future__ import annotations

from pathlib import Path

from litcurate.constants import PaperStageStatus, StageStatus
from litcurate.reset_stage import reset_stage
from litcurate.run_store import open_run_store
from litcurate.stages.utils import write_json


def _setup_convert_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "runs" / "testrun"
    artifacts = run_dir / "artifacts"
    md_dir = artifacts / "markdown"
    clean_dir = artifacts / "markdown_clean"
    md_dir.mkdir(parents=True)
    clean_dir.mkdir(parents=True)

    (md_dir / "10.1002_2016gl067970.md").write_text("# Paper A\n", encoding="utf-8")
    (md_dir / "10.1002_2016jb013543.md").write_text("# Paper B\n", encoding="utf-8")
    (clean_dir / "10.1002_2016gl067970.md").write_text("clean A\n", encoding="utf-8")
    write_json(artifacts / "convert_manifest.json", {"conversions": [{"status": "success"}]})
    write_json(artifacts / "clean_manifest.json", {"cleaned": [{"status": "success"}]})

    store = open_run_store(run_dir)
    config_path = tmp_path / "config.yaml"
    config_path.write_text("run:\n  name: test\n  user_goal: test\n", encoding="utf-8")
    snapshot_path = run_dir / "config.snapshot.yaml"
    snapshot_path.write_text(config_path.read_text(encoding="utf-8"), encoding="utf-8")
    store.create_run(
        run_id="testrun",
        config_path=config_path,
        config_snapshot_path=snapshot_path,
        name="test",
        run_dir=run_dir,
    )
    for paper_id in ("10.1002_2016gl067970", "10.1002_2016jb013543"):
        store.upsert_paper("testrun", paper_id, doi=paper_id.replace("_", "/"))
        store.update_paper_stage(
            "testrun", paper_id, "convert_status", PaperStageStatus.SUCCESS
        )
        store.update_paper_stage(
            "testrun", paper_id, "clean_status", PaperStageStatus.SUCCESS
        )
    store.start_stage("testrun", "convert_marker")
    store.complete_stage(
        "testrun",
        "convert_marker",
        artifact_path=artifacts / "convert_manifest.json",
    )
    store.start_stage("testrun", "clean_markdown")
    store.complete_stage(
        "testrun",
        "clean_markdown",
        artifact_path=artifacts / "clean_manifest.json",
    )
    return run_dir


def test_reset_convert_marker_clears_markdown_and_status(tmp_path: Path) -> None:
    run_dir = _setup_convert_run(tmp_path)

    report = reset_stage(run_dir, "convert_marker")
    assert "convert_marker" in report.stages
    assert any(path.endswith("convert_manifest.json") for path in report.deleted_paths)
    assert any("markdown/" in path for path in report.deleted_paths)

    assert not (run_dir / "artifacts" / "convert_manifest.json").exists()
    assert not (run_dir / "artifacts" / "markdown").exists()
    # Downstream artifacts are left alone unless --and-downstream
    assert (run_dir / "artifacts" / "clean_manifest.json").exists()

    store = open_run_store(run_dir)
    assert store.get_stage("testrun", "convert_marker").status == StageStatus.PENDING.value
    assert store.get_stage("testrun", "clean_markdown").status == StageStatus.COMPLETED.value
    papers = {p.paper_id: p for p in store.list_papers("testrun")}
    assert papers["10.1002_2016gl067970"].convert_status == PaperStageStatus.PENDING.value
    assert papers["10.1002_2016gl067970"].clean_status == PaperStageStatus.SUCCESS.value


def test_reset_convert_and_downstream(tmp_path: Path) -> None:
    run_dir = _setup_convert_run(tmp_path)

    report = reset_stage(run_dir, "convert_marker", and_downstream=True)
    assert report.stages[0] == "convert_marker"
    assert "clean_markdown" in report.stages
    assert "export" in report.stages

    assert not (run_dir / "artifacts" / "markdown").exists()
    assert not (run_dir / "artifacts" / "markdown_clean").exists()
    assert not (run_dir / "artifacts" / "clean_manifest.json").exists()

    store = open_run_store(run_dir)
    assert store.get_stage("testrun", "clean_markdown").status == StageStatus.PENDING.value
    papers = {p.paper_id: p for p in store.list_papers("testrun")}
    assert papers["10.1002_2016gl067970"].clean_status == PaperStageStatus.PENDING.value


def test_reset_single_paper_keeps_other_markdown(tmp_path: Path) -> None:
    run_dir = _setup_convert_run(tmp_path)
    paper_id = "10.1002_2016gl067970"

    report = reset_stage(run_dir, "convert_marker", paper_ids=[paper_id])
    assert any(paper_id in path for path in report.deleted_paths)

    md_dir = run_dir / "artifacts" / "markdown"
    assert not (md_dir / f"{paper_id}.md").exists()
    assert (md_dir / "10.1002_2016jb013543.md").exists()
    # Manifest removed so convert_marker rebuilds it
    assert not (run_dir / "artifacts" / "convert_manifest.json").exists()

    store = open_run_store(run_dir)
    papers = {p.paper_id: p for p in store.list_papers("testrun")}
    assert papers[paper_id].convert_status == PaperStageStatus.PENDING.value
    assert papers["10.1002_2016jb013543"].convert_status == PaperStageStatus.SUCCESS.value


def test_reset_dry_run_does_not_delete(tmp_path: Path) -> None:
    run_dir = _setup_convert_run(tmp_path)
    report = reset_stage(run_dir, "convert_marker", dry_run=True)
    assert report.dry_run
    assert report.deleted_paths
    assert (run_dir / "artifacts" / "convert_manifest.json").exists()
    assert (run_dir / "artifacts" / "markdown" / "10.1002_2016gl067970.md").exists()

    store = open_run_store(run_dir)
    assert store.get_stage("testrun", "convert_marker").status == StageStatus.COMPLETED.value
