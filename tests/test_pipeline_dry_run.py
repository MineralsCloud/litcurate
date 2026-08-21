"""End-to-end dry-run pipeline test."""

from pathlib import Path

from litcurate.pipeline import PipelineRunner


def test_dry_run_pipeline(tmp_path: Path) -> None:
    config_path = Path(__file__).resolve().parents[1] / "configs" / "config.yaml"
    runner = PipelineRunner(config_path, runs_dir=tmp_path / "runs")
    run_id = runner.start_new_run()

    run_dir = tmp_path / "runs" / run_id
    assert (run_dir / "run.db").exists()
    assert (run_dir / "artifacts" / "output" / "database.json").exists()
    assert (run_dir / "config.snapshot.yaml").exists()
