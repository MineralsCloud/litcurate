"""Tests for SQLite run ledger."""

from pathlib import Path

from litcurate.constants import STAGE_ORDER, PaperStageStatus, RunStatus, StageStatus
from litcurate.run_store import RunStore


def test_create_run_and_stages(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "run.db")
    record = store.create_run(
        config_path=tmp_path / "config.yaml",
        config_snapshot_path=tmp_path / "snapshot.yaml",
        name="test_run",
        run_dir=tmp_path / "run_dir",
        run_id="test123",
    )
    assert record.id == "test123"
    stages = store.list_stages("test123")
    assert len(stages) == len(STAGE_ORDER)
    assert [s.stage_name for s in stages] == list(STAGE_ORDER)
    assert all(stage.status == StageStatus.PENDING.value for stage in stages)


def test_stage_lifecycle(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "run.db")
    store.create_run(
        config_path=tmp_path / "config.yaml",
        config_snapshot_path=tmp_path / "snapshot.yaml",
        name="test_run",
        run_dir=tmp_path / "run_dir",
        run_id="abc",
    )
    store.start_stage("abc", "query_generation")
    store.complete_stage("abc", "query_generation", artifact_path=tmp_path / "queries.json")
    assert store.is_stage_completed("abc", "query_generation")
    store.update_run_status("abc", RunStatus.COMPLETED)
    run = store.get_run("abc")
    assert run is not None
    assert run.status == RunStatus.COMPLETED.value


def test_paper_tracking(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "run.db")
    store.create_run(
        config_path=tmp_path / "config.yaml",
        config_snapshot_path=tmp_path / "snapshot.yaml",
        name="test_run",
        run_dir=tmp_path / "run_dir",
        run_id="abc",
    )
    store.upsert_paper("abc", "10.1038_nature00000", doi="10.1038/nature00000", title="Test")
    store.update_paper_stage(
        "abc", "10.1038_nature00000", "download_status", PaperStageStatus.SUCCESS
    )
    counts = store.count_papers_by_status("abc", "download_status")
    assert counts["success"] == 1


def test_api_usage_tracking(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "run.db")
    store.create_run(
        config_path=tmp_path / "config.yaml",
        config_snapshot_path=tmp_path / "snapshot.yaml",
        name="test_run",
        run_dir=tmp_path / "run_dir",
        run_id="abc",
    )
    store.record_api_usage(
        "abc",
        stage_name="query_generation",
        provider="anthropic",
        model="claude-sonnet-4-6",
        input_tokens=1000,
        output_tokens=200,
        cost_usd=0.006,
        label="generate_queries",
    )
    store.record_api_usage(
        "abc",
        stage_name="filter_abstracts",
        provider="anthropic",
        model="claude-sonnet-4-6",
        input_tokens=5000,
        output_tokens=800,
        cost_usd=0.027,
        label="batch_1",
    )

    summary = store.get_api_cost_summary("abc")
    assert summary["call_count"] == 2
    assert summary["total_input_tokens"] == 6000
    assert summary["total_output_tokens"] == 1000
    assert summary["total_cost_usd"] == 0.033
    assert summary["by_stage"]["query_generation"]["calls"] == 1
    assert summary["by_stage"]["filter_abstracts"]["cost_usd"] == 0.027
