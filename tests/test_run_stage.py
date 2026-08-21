"""Tests for modular single-stage runs."""

from pathlib import Path

from litcurate.pipeline import PipelineRunner


def test_run_stage_query_generation_dry_run(tmp_path: Path) -> None:
    config_path = Path(__file__).resolve().parents[1] / "configs" / "config.yaml"
    runner = PipelineRunner(config_path, runs_dir=tmp_path / "runs", force=True)
    run_id = runner.run_stage("query_generation")

    queries_path = tmp_path / "runs" / run_id / "artifacts" / "queries.json"
    assert queries_path.exists()
    payload = queries_path.read_text(encoding="utf-8")
    assert "queries" in payload


def test_run_stage_openalex_requires_queries(tmp_path: Path) -> None:
    config_path = Path(__file__).resolve().parents[1] / "configs" / "config.yaml"
    runner = PipelineRunner(config_path, runs_dir=tmp_path / "runs")
    run_id = runner.init_run()

    try:
        runner.run_stage("openalex_search", run_id=run_id)
        raise AssertionError("expected FileNotFoundError")
    except FileNotFoundError as exc:
        assert "queries.json" in str(exc)
