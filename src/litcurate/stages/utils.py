"""Shared stage utilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from litcurate.doi import paper_id_from_doi as paper_id_from_doi


def write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
    tmp.replace(path)
    return path


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def read_json_if_valid(path: Path) -> Any | None:
    """Return parsed JSON or None if the file is missing, empty, or corrupt."""
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        return read_json(path)
    except json.JSONDecodeError:
        return None


def write_parquet(path: Path, frame: pd.DataFrame) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return path


def read_parquet(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)


SAMPLE_PAPERS = [
    {
        "paper_id": "10.1038_nature00000",
        "doi": "10.1038/nature00000",
        "title": "Example primary results from a peer-reviewed study",
        "abstract": "We report measured quantities and fitted parameters relevant to the user goal.",
        "abstract_source": "openalex",
        "year": 2020,
        "frequency": 5,
        "mean_relevance": 0.92,
        "citation_count": 120,
        "score": 6.2,
        "keep": True,
        "filter_reason": "dry_run sample",
    }
]
