"""Tests for generic dry-run schema samples."""

from __future__ import annotations

import json
from pathlib import Path

from litcurate.schema_samples import dry_run_sample_from_schema, is_empty_list_field


def test_dry_run_sample_from_list_schema() -> None:
    schema_path = Path(__file__).resolve().parents[1] / "schemas" / "example" / "record.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    sample = dry_run_sample_from_schema(schema)
    assert "eos_entries" in sample
    assert isinstance(sample["eos_entries"], list)


def test_is_empty_list_field() -> None:
    assert is_empty_list_field({"records": []}, "records")
    assert not is_empty_list_field({"records": [{"x": 1}]}, "records")
