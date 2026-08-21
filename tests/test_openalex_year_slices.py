"""Tests for OpenAlex search stage with year slices."""

from pathlib import Path

from litcurate.config import (
    LlmConfig,
    OpenAlexConfig,
    PipelineConfig,
    RunConfig,
    SearchConfig,
    YearSliceConfig,
)
from litcurate.constants import RunStatus
from litcurate.paths import artifacts_directory, run_directory
from litcurate.run_store import open_run_store
from litcurate.stages.base import StageContext
from litcurate.stages.openalex_search import OpenAlexSearchStage
from litcurate.stages.utils import read_json, write_json


def test_openalex_search_dry_run_writes_year_slice_files(tmp_path: Path) -> None:
    run_id = "testyearslice01"
    run_dir = run_directory(tmp_path / "runs", run_id)
    artifacts = artifacts_directory(run_dir)
    artifacts.mkdir(parents=True)

    write_json(
        artifacts / "queries.json",
        {
            "queries": [
                {"id": "q1", "query": "example research topic", "rationale": "test"},
            ]
        },
    )

    config = PipelineConfig(
        run=RunConfig(name="test", user_goal="test goal"),
        llm=LlmConfig(provider="anthropic"),
        search=SearchConfig(
            openalex=OpenAlexConfig(
                year_slices=[
                    YearSliceConfig(year_min=1990, year_max=1999),
                    YearSliceConfig(year_min=2000, year_max=2009),
                ]
            )
        ),
        abstract_filter={"criteria": "keep relevant papers"},
        dry_run=True,
    )

    store = open_run_store(run_dir)
    store.create_run(
        config_path=tmp_path / "config.yaml",
        config_snapshot_path=tmp_path / "snapshot.yaml",
        name="test",
        run_dir=run_dir,
        run_id=run_id,
    )
    store.update_run_status(run_id, RunStatus.RUNNING)

    ctx = StageContext(
        run_id=run_id,
        run_dir=run_dir,
        artifacts_dir=artifacts,
        config=config,
        store=store,
        dry_run=True,
    )

    result = OpenAlexSearchStage().run(ctx)
    assert "2 year slice(s)" in (result.message or "")

    raw_dir = artifacts / "openalex_raw"
    assert (raw_dir / "q1_y1990_1999.json").exists()
    assert (raw_dir / "q1_y2000_2009.json").exists()
    assert not (raw_dir / "q1.json").exists()

    slice_payload = read_json(raw_dir / "q1_y1990_1999.json")
    assert slice_payload["year_min"] == 1990
    assert slice_payload["year_max"] == 1999


def test_openalex_search_skips_failed_query_after_retries(
    tmp_path: Path, monkeypatch
) -> None:
    from litcurate.clients.openalex import OpenAlexRequestError

    run_id = "testoaexclude01"
    run_dir = run_directory(tmp_path / "runs", run_id)
    artifacts = artifacts_directory(run_dir)
    artifacts.mkdir(parents=True)

    write_json(
        artifacts / "queries.json",
        {
            "queries": [
                {"id": "q1", "query": "bad query that fails", "rationale": "test"},
                {"id": "q2", "query": "example research topic", "rationale": "test"},
            ]
        },
    )

    config = PipelineConfig(
        run=RunConfig(name="test", user_goal="test goal"),
        llm=LlmConfig(provider="anthropic"),
        search=SearchConfig(openalex=OpenAlexConfig(year_slices=[])),
        abstract_filter={"criteria": "keep relevant papers"},
        dry_run=False,
    )

    store = open_run_store(run_dir)
    store.create_run(
        config_path=tmp_path / "config.yaml",
        config_snapshot_path=tmp_path / "snapshot.yaml",
        name="test",
        run_dir=run_dir,
        run_id=run_id,
    )
    store.update_run_status(run_id, RunStatus.RUNNING)

    ctx = StageContext(
        run_id=run_id,
        run_dir=run_dir,
        artifacts_dir=artifacts,
        config=config,
        store=store,
        dry_run=False,
    )

    monkeypatch.setenv("OPENALEX_EMAIL", "test@example.com")

    def fake_fetch(query: str, **kwargs):
        if "bad query" in query:
            raise OpenAlexRequestError("OpenAlex request failed after 8 retries")
        return [
            {
                "id": "https://openalex.org/W1",
                "display_name": "Example primary study",
                "doi": "https://doi.org/10.1000/test",
                "_relevance_rank": 1,
            }
        ]

    monkeypatch.setattr(
        "litcurate.stages.openalex_search.fetch_works_for_query",
        fake_fetch,
    )

    result = OpenAlexSearchStage().run(ctx)
    assert "1 failed/skipped" in (result.message or "")

    raw_dir = artifacts / "openalex_raw"
    failed = read_json(raw_dir / "q1.json")
    assert failed["status"] == "failed"
    assert failed["results"] == []

    ok = read_json(raw_dir / "q2.json")
    assert ok["status"] == "success"
    assert len(ok["results"]) == 1
