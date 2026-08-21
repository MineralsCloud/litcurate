"""Tests for post-merge paper filtering."""

import pandas as pd

from litcurate.config import MergeConfig
from litcurate.merge_filters import filter_ranked_papers


def _sample_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "doi": "10.1000/journal.1",
                "title": "Good paper",
                "abstract": "Primary experimental data for the topic.",
                "journal": "Nature",
                "work_type": "article",
                "source_type": "journal",
            },
            {
                "doi": None,
                "title": "Conference abstract",
                "abstract": None,
                "journal": "ConfAbs Digest",
                "work_type": "conference-abstract",
                "source_type": "journal",
            },
            {
                "doi": "10.1000/repo.1",
                "title": "Preprint",
                "abstract": "Some text",
                "journal": "arXiv (Cornell University)",
                "work_type": "article",
                "source_type": "repository",
            },
            {
                "doi": "10.1000/journal.2",
                "title": "No abstract",
                "abstract": None,
                "journal": "Journal of Geophysics",
                "work_type": "article",
                "source_type": "journal",
            },
        ]
    )


def test_full_papers_only_keeps_journal_records_with_doi_and_abstract() -> None:
    filtered = filter_ranked_papers(_sample_frame(), MergeConfig(), full_papers_only=True)
    assert len(filtered) == 1
    assert filtered.iloc[0]["title"] == "Good paper"


def test_full_papers_only_excludes_non_journal_and_blocklist() -> None:
    filtered = filter_ranked_papers(_sample_frame(), MergeConfig(), full_papers_only=True)
    journals = filtered["journal"].tolist()
    assert "ConfAbs Digest" not in journals
    assert not any("arXiv" in j for j in journals)


def test_full_papers_only_disabled_skips_filtering() -> None:
    filtered = filter_ranked_papers(_sample_frame(), MergeConfig(), full_papers_only=False)
    assert len(filtered) == len(_sample_frame())


def test_extra_exclude_journal_substrings() -> None:
    frame = pd.DataFrame(
        [
            {
                "doi": "10.1000/journal.3",
                "title": "Specialized journal paper",
                "abstract": "Data.",
                "journal": "Specialized Journal",
                "work_type": "article",
                "source_type": "journal",
            }
        ]
    )
    cfg = MergeConfig(extra_exclude_journal_substrings=["Specialized Journal"])
    filtered = filter_ranked_papers(frame, cfg, full_papers_only=True)
    assert filtered.empty
