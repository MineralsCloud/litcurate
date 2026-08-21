"""Tests for clean_markdown stage manifest flags."""

from __future__ import annotations

from pathlib import Path

from litcurate.config import load_config
from litcurate.pipeline import PipelineRunner
from litcurate.run_store import open_run_store
from litcurate.stages.base import StageContext
from litcurate.stages.clean_markdown import CleanMarkdownStage
from litcurate.stages.utils import read_json, write_json


def _make_ctx(tmp_path: Path, config_path: Path) -> StageContext:
    runner = PipelineRunner(config_path, runs_dir=tmp_path / "runs")
    run_id = runner.init_run()
    run_dir = tmp_path / "runs" / run_id
    config = load_config(config_path)
    return StageContext(
        run_id=run_id,
        run_dir=run_dir,
        artifacts_dir=run_dir / "artifacts",
        config=config,
        store=open_run_store(run_dir),
        force=True,
    )


def test_clean_manifest_flags_heavy_strip(tmp_path: Path) -> None:
    config_path = Path(__file__).resolve().parents[1] / "configs" / "config.yaml"
    ctx = _make_ctx(tmp_path, config_path)

    md_dir = ctx.artifact("markdown")
    md_dir.mkdir(parents=True, exist_ok=True)

    source = "x" * 40 + "\n\n## References\n\n" + ("Smith et al. (2020).\n" * 20)
    (md_dir / "10.1038_nature00000.md").write_text(source, encoding="utf-8")
    write_json(
        ctx.artifact("convert_manifest.json"),
        {
            "conversions": [
                {
                    "paper_id": "10.1038_nature00000",
                    "status": "success",
                    "path": "artifacts/markdown/10.1038_nature00000.md",
                }
            ]
        },
    )

    CleanMarkdownStage().run(ctx)
    payload = read_json(ctx.artifact("clean_manifest.json"))
    entry = payload["cleaned"][0]
    assert entry["heavy_strip"] is True
    assert entry["strip_fraction"] > 0.5
    assert "warning" in entry
    assert payload["heavy_strip_count"] == 1
