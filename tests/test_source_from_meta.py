"""Tests for filling source schema from OpenAlex / papers parquet."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from litcurate.config import ExtractionSchemaRef
from litcurate.source_from_meta import (
    load_papers_meta_index,
    source_payload_from_paper_meta,
)
from litcurate.stages.base import StageContext
from unittest.mock import MagicMock


def test_source_payload_from_paper_meta() -> None:
    payload = source_payload_from_paper_meta(
        {
            "doi": "10.1029/2000jb900457",
            "title": "Example Title",
            "year": 2001.0,
            "journal": "JGR",
            "authors_json": json.dumps(["Ada Lovelace", "Alan Turing"]),
            "source_type": "journal",
        }
    )
    assert payload["doi"] == "10.1029/2000jb900457"
    assert payload["title"] == "Example Title"
    assert payload["year"] == 2001
    assert payload["journal"] == "JGR"
    assert payload["authors"] == ["Ada Lovelace", "Alan Turing"]
    assert payload["source_type"] == "journal"
    assert payload["confidence"] == 1.0


def test_load_papers_meta_index_prefers_filtered(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "paper_id": "10.1000_a",
                "doi": "10.1000/a",
                "title": "A",
                "year": 2020,
                "authors_json": "[]",
                "journal": "J",
                "source_type": "journal",
            }
        ]
    ).to_parquet(artifacts / "papers_filtered.parquet")

    ctx = StageContext(
        run_id="r",
        run_dir=run_dir,
        artifacts_dir=artifacts,
        config=MagicMock(),
        store=MagicMock(),
    )
    index = load_papers_meta_index(ctx)
    assert "10.1000_a" in index
    assert index["10.1000_a"]["doi"] == "10.1000/a"


def test_source_schema_ref_allows_fill_from_without_prompt() -> None:
    root = Path(__file__).resolve().parents[1]
    source = ExtractionSchemaRef(
        name="source",
        path=str(root / "schemas/example/source.json"),
        fill_from="papers_meta",
    )
    assert source.fill_from == "papers_meta"
    assert source.prompt is None


def test_extraction_schema_ref_requires_prompt_without_fill_from() -> None:
    try:
        ExtractionSchemaRef(name="x", path="schemas/x.json")
        raised = False
    except Exception:
        raised = True
    assert raised
