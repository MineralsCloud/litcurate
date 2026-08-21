"""Tests for pre-rank merged paper export."""

from __future__ import annotations

import json
from pathlib import Path

from litcurate.export_merged import build_merged_frame, export_merged_papers


def _write_openalex_raw(path: Path, query_id: str, dois: list[str]) -> None:
    results = [
        {
            "id": f"https://openalex.org/W{i}",
            "doi": f"https://doi.org/{doi}",
            "display_name": f"Paper {doi}",
            "publication_year": 2020,
            "type": "article",
            "cited_by_count": i,
            "abstract_inverted_index": {"Abstract": [0], "text": [1]},
            "primary_location": {
                "source": {"display_name": "Journal", "type": "journal"},
            },
            "open_access": {"is_oa": True},
            "_relevance_rank": i + 1,
        }
        for i, doi in enumerate(dois)
    ]
    path.write_text(
        json.dumps(
            {
                "provider": "openalex",
                "query_id": query_id,
                "query": "test query",
                "results": results,
            }
        ),
        encoding="utf-8",
    )


def test_build_merged_frame_dedupes_across_raw_files(tmp_path: Path) -> None:
    raw_dir = tmp_path / "openalex_raw"
    raw_dir.mkdir()
    _write_openalex_raw(raw_dir / "q1_y1990_1992.json", "q1", ["10.1000/a", "10.1000/b"])
    _write_openalex_raw(raw_dir / "q2_y1990_1992.json", "q2", ["10.1000/a", "10.1000/c"])

    frame = build_merged_frame([raw_dir / "q1_y1990_1992.json", raw_dir / "q2_y1990_1992.json"])

    assert len(frame) == 3
    by_doi = {row["doi"]: row for row in frame.to_dict(orient="records")}
    assert by_doi["10.1000/a"]["frequency"] == 2
    assert by_doi["10.1000/a"]["source_file_count"] == 2
    assert "q1_y1990_1992.json" in by_doi["10.1000/a"]["source_files"]


def test_export_merged_papers_writes_parquet(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    raw_dir = artifacts / "openalex_raw"
    raw_dir.mkdir(parents=True)
    _write_openalex_raw(raw_dir / "q1.json", "q1", ["10.1000/x"])

    frame, out = export_merged_papers(raw_dir=artifacts)
    assert len(frame) == 1
    assert out == artifacts / "papers_merged.parquet"
    assert out.exists()
