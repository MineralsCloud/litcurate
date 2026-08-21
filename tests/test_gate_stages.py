"""Tests for pre_extract and filter_fulltext gate stages."""

from __future__ import annotations

from pathlib import Path

from litcurate.config import load_config
from litcurate.pipeline import PipelineRunner
from litcurate.run_store import open_run_store
from litcurate.stages.base import StageContext
from litcurate.stages.filter_fulltext import FilterFulltextStage
from litcurate.stages.pre_extract import PreExtractStage
from litcurate.stages.utils import write_json


def _make_ctx(tmp_path: Path, config_path: Path) -> StageContext:
    runner = PipelineRunner(config_path, runs_dir=tmp_path / "runs")
    run_id = runner.start_new_run()
    run_dir = tmp_path / "runs" / run_id
    config = load_config(config_path)
    return StageContext(
        run_id=run_id,
        run_dir=run_dir,
        artifacts_dir=run_dir / "artifacts",
        config=config,
        store=open_run_store(run_dir),
        dry_run=True,
    )


def test_gate_stages_passthrough_when_disabled(tmp_path: Path) -> None:
    config_path = Path(__file__).resolve().parents[1] / "configs" / "config.yaml"
    ctx = _make_ctx(tmp_path, config_path)
    ctx.config.pre_extract.enabled = False
    ctx.config.fulltext_filter.enabled = False

    clean_dir = ctx.artifact("markdown_clean")
    clean_dir.mkdir(parents=True, exist_ok=True)
    (clean_dir / "10.1038_nature00000.md").write_text(
        "## Results\n\nNo target data here.\n",
        encoding="utf-8",
    )
    write_json(
        ctx.artifact("clean_manifest.json"),
        {
            "cleaned": [
                {
                    "paper_id": "10.1038_nature00000",
                    "status": "success",
                    "path": "artifacts/markdown_clean/10.1038_nature00000.md",
                }
            ]
        },
    )

    pre = PreExtractStage().run(ctx)
    assert "passthrough" in pre.message

    ft = FilterFulltextStage().run(ctx)
    assert "passthrough" in ft.message

    pre_payload = ctx.artifact("pre_extract_manifest.json").read_text(encoding="utf-8")
    ft_payload = ctx.artifact("fulltext_filter_manifest.json").read_text(encoding="utf-8")
    assert '"status": "pass"' in pre_payload
    assert '"keep": true' in ft_payload
