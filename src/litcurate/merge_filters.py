"""Post-merge filters for ranked paper tables."""

from __future__ import annotations

import pandas as pd

from litcurate.config import MergeConfig
from litcurate.constants import DEFAULT_EXCLUDE_JOURNAL_SUBSTRINGS, EXCLUDED_WORK_TYPES


def filter_ranked_papers(
    frame: pd.DataFrame,
    merge_cfg: MergeConfig,
    *,
    full_papers_only: bool = True,
) -> pd.DataFrame:
    """Drop rows that fail pipeline or user-configured quality gates."""
    if frame.empty or not full_papers_only:
        return frame

    mask = pd.Series(True, index=frame.index)

    if "doi" in frame.columns:
        doi = frame["doi"]
        mask &= doi.notna() & (doi.astype(str).str.strip() != "")

    if "abstract" in frame.columns:
        abstract = frame["abstract"]
        mask &= abstract.notna() & (abstract.astype(str).str.strip() != "")

    if "work_type" in frame.columns:
        work_type = frame["work_type"].fillna("").astype(str)
        mask &= ~work_type.isin(EXCLUDED_WORK_TYPES)
        mask &= (work_type == "") | (work_type == "article")

    if "source_type" in frame.columns:
        source_type = frame["source_type"].fillna("").astype(str)
        mask &= (source_type == "") | (source_type == "journal")

    if "journal" in frame.columns:
        journal = frame["journal"].fillna("").astype(str)
        blocklist = [
            *DEFAULT_EXCLUDE_JOURNAL_SUBSTRINGS,
            *merge_cfg.extra_exclude_journal_substrings,
        ]
        for pattern in blocklist:
            if pattern:
                mask &= ~journal.str.contains(pattern, case=False, regex=False)

    return frame[mask].reset_index(drop=True)
