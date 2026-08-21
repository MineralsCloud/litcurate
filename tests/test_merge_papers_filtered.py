"""Tests for merge_papers_filtered / litcurate merge-filtered."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from litcurate.merge_papers_filtered import merge_papers_filtered
from litcurate.paths import artifacts_directory, run_directory


def _write_filtered(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


def test_merge_papers_filtered_dedupes(tmp_path: Path) -> None:
    into = tmp_path / "into.parquet"
    source = tmp_path / "from.parquet"
    _write_filtered(
        into,
        [
            {"paper_id": "10.1_a", "doi": "10.1/a", "title": "A", "keep": True},
            {"paper_id": "10.1_b", "doi": "10.1/b", "title": "B", "keep": True},
        ],
    )
    _write_filtered(
        source,
        [
            {"paper_id": "10.1_b", "doi": "10.1/b", "title": "B dup", "keep": True},
            {"paper_id": "10.1_c", "doi": "10.1/c", "title": "C", "keep": True},
        ],
    )

    report = merge_papers_filtered(into, source, dry_run=False)
    assert report.before_count == 2
    assert report.added_count == 1
    assert report.already_present_count == 1
    assert report.added_paper_ids == ["10.1_c"]
    assert report.backup_path is not None and report.backup_path.exists()

    merged = pd.read_parquet(into)
    assert set(merged["paper_id"]) == {"10.1_a", "10.1_b", "10.1_c"}


def test_merge_filtered_cli(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from litcurate.cli import app

    runs = tmp_path / "runs"
    into_id, from_id = "targetrun0001", "sourcerun0001"
    into_dir = artifacts_directory(run_directory(runs, into_id))
    from_dir = artifacts_directory(run_directory(runs, from_id))
    _write_filtered(
        into_dir / "papers_filtered.parquet",
        [{"paper_id": "10.1_a", "doi": "10.1/a", "keep": True}],
    )
    _write_filtered(
        from_dir / "papers_filtered.parquet",
        [
            {"paper_id": "10.1_a", "doi": "10.1/a", "keep": True},
            {"paper_id": "10.1_z", "doi": "10.1/z", "keep": True},
        ],
    )
    # run dirs must exist for filtered_parquet_for_run
    run_directory(runs, into_id).mkdir(parents=True, exist_ok=True)
    run_directory(runs, from_id).mkdir(parents=True, exist_ok=True)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "merge-filtered",
            "--into-run-id",
            into_id,
            "--from-run-id",
            from_id,
            "--runs-dir",
            str(runs),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "added=1" in result.output
    merged = pd.read_parquet(into_dir / "papers_filtered.parquet")
    assert "10.1_z" in set(merged["paper_id"])
