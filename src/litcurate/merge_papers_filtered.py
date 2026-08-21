"""Merge papers_filtered.parquet from one run into another."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from litcurate.doi import normalize_doi, paper_id_from_doi
from litcurate.paths import artifacts_directory, run_directory


@dataclass
class MergeFilteredReport:
    into_path: Path
    from_path: Path
    before_count: int
    added_count: int
    already_present_count: int
    after_count: int
    added_paper_ids: list[str] = field(default_factory=list)
    backup_path: Path | None = None
    dry_run: bool = False


def filtered_parquet_for_run(runs_dir: Path, run_id: str) -> Path:
    run_dir = run_directory(runs_dir, run_id)
    if not run_dir.exists():
        raise FileNotFoundError(f"Unknown run ID: {run_id}")
    path = artifacts_directory(run_dir) / "papers_filtered.parquet"
    if not path.exists():
        raise FileNotFoundError(f"papers_filtered.parquet not found for run {run_id}: {path}")
    return path


def _normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    if "doi" in frame.columns:
        frame["doi"] = frame["doi"].map(
            lambda v: normalize_doi(str(v))
            if v is not None and not (isinstance(v, float) and pd.isna(v))
            else None
        )
    if "paper_id" not in frame.columns:
        if "doi" not in frame.columns:
            raise ValueError("Input parquet needs paper_id or doi")
        frame["paper_id"] = frame["doi"].map(lambda d: paper_id_from_doi(d))
    elif "doi" in frame.columns:
        missing = frame["paper_id"].isna() | (frame["paper_id"].astype(str).str.len() == 0)
        frame.loc[missing, "paper_id"] = frame.loc[missing, "doi"].map(
            lambda d: paper_id_from_doi(d) if d else None
        )
    frame["paper_id"] = frame["paper_id"].astype(str)
    if "keep" not in frame.columns:
        frame["keep"] = True
    else:
        frame["keep"] = frame["keep"].fillna(True)
    if "filter_reason" not in frame.columns:
        frame["filter_reason"] = "merged_from_other_run"
    else:
        frame["filter_reason"] = frame["filter_reason"].fillna("merged_from_other_run")
    if "filter_status" not in frame.columns:
        frame["filter_status"] = "keep"
    return frame


def merge_papers_filtered(
    into_path: Path,
    from_path: Path,
    *,
    dry_run: bool = False,
) -> MergeFilteredReport:
    """Append rows from ``from_path`` into ``into_path``, deduping by paper_id."""
    into_path = into_path.resolve()
    from_path = from_path.resolve()
    if not into_path.exists():
        raise FileNotFoundError(f"Target not found: {into_path}")
    if not from_path.exists():
        raise FileNotFoundError(f"Source not found: {from_path}")

    into = _normalize_frame(pd.read_parquet(into_path))
    extra = _normalize_frame(pd.read_parquet(from_path))

    before = len(into)
    existing = set(into["paper_id"].astype(str))
    new_rows = extra[~extra["paper_id"].astype(str).isin(existing)].copy()
    added_ids = new_rows["paper_id"].astype(str).tolist()

    all_cols = list(dict.fromkeys([*into.columns.tolist(), *new_rows.columns.tolist()]))
    into = into.reindex(columns=all_cols)
    new_rows = new_rows.reindex(columns=all_cols)
    merged = pd.concat([into, new_rows], ignore_index=True)

    added = len(new_rows)
    skipped = len(extra) - added
    backup: Path | None = None

    if not dry_run and added:
        backup = into_path.with_suffix(".parquet.bak")
        shutil.copy2(into_path, backup)
        merged.to_parquet(into_path, index=False)

    return MergeFilteredReport(
        into_path=into_path,
        from_path=from_path,
        before_count=before,
        added_count=added,
        already_present_count=skipped,
        after_count=before + added,
        added_paper_ids=added_ids,
        backup_path=backup,
        dry_run=dry_run,
    )
