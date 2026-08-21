"""Tests for extract_schema logging and failure artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from litcurate.config import ExtractionSchemaRef, load_config
from litcurate.schema_spec import load_schema_spec
from litcurate.source_from_meta import load_papers_meta_index
from litcurate.stages.base import StageContext
from litcurate.stages.extract_schema import (
    ExtractSchemaStage,
    _dump_low_input_prompt,
    _extract_from_fill_source,
    _extract_with_llm,
    _write_failure_record,
)
from litcurate.stages.utils import read_json


def test_extract_schema_writes_empty_manifest_when_no_papers_are_eligible(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "configs" / "config.yaml")
    run_dir = tmp_path / "run"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "clean_manifest.json").write_text(
        json.dumps({"cleaned": []}),
        encoding="utf-8",
    )
    (artifacts / "fulltext_filter_manifest.json").write_text(
        json.dumps({"papers": []}),
        encoding="utf-8",
    )
    ctx = StageContext(
        run_id="testrun",
        run_dir=run_dir,
        artifacts_dir=artifacts,
        config=config,
        store=MagicMock(),
        dry_run=True,
        force=True,
    )

    result = ExtractSchemaStage().run(ctx)

    manifest_path = artifacts / "extract_manifest.json"
    assert result.artifact_path == manifest_path
    assert read_json(manifest_path) == {"extractions": []}


def test_write_failure_record_includes_validation_errors(tmp_path: Path) -> None:
    path = _write_failure_record(
        tmp_path,
        paper_id="10.1000_test",
        schema_name="record",
        error="validation failed",
        raw_response='{"title": "x"}',
        payload={"title": "x"},
        validation_errors=["'evidence_text' is a required property"],
    )
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["schema"] == "record"
    assert record["validation_errors"]
    assert "title" in record["raw_response_preview"]


def test_dump_low_input_prompt_writes_debug_artifact(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    ctx = StageContext(
        run_id="testrun",
        run_dir=run_dir,
        artifacts_dir=artifacts,
        config=MagicMock(),
        store=MagicMock(),
        dry_run=False,
        force=True,
    )
    path = _dump_low_input_prompt(
        ctx,
        paper_id="10.1000_test",
        schema_name="record",
        input_tokens=1436,
        raw_markdown_chars=78000,
        prepared_markdown_chars=1200,
        user_prompt="PROMPT BODY HERE",
    )
    text = path.read_text(encoding="utf-8")
    assert "input_tokens=1436" in text
    assert "raw_markdown_chars=78000" in text
    assert "prepared_markdown_chars=1200" in text
    assert "PROMPT BODY HERE" in text
    assert path.name == "10.1000_test_record_prompt.txt"


def test_extract_with_llm_dumps_prompt_for_low_input(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "configs" / "config.yaml")
    run_dir = tmp_path / "run"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    ctx = StageContext(
        run_id="testrun",
        run_dir=run_dir,
        artifacts_dir=artifacts,
        config=config,
        store=MagicMock(),
        dry_run=False,
        force=True,
    )
    schema_ref = ExtractionSchemaRef(
        name="record",
        format="declarative_yaml",
        path=str(root / "schemas/example/record.yaml"),
        prompt=str(root / "prompts/example/prompt.md"),
        version="2.1",
        empty_list_field="eos_entries",
    )
    spec = load_schema_spec(schema_ref)

    with patch("litcurate.stages.extract_schema.llm_require_configured"):
        with patch("litcurate.stages.extract_schema.llm_chat") as mock_chat:
            mock_chat.return_value = MagicMock(
                text='{"eos_entries": []}',
                input_tokens=1500,
            )
            _extract_with_llm(
                ctx=ctx,
                markdown="# big paper\n" + ("x" * 50_000),
                spec=spec,
                schema_ref=schema_ref,
                model="claude-sonnet-4-6",
                paper_id="10.1000_rec",
            )

    dump = artifacts / "extract_prompt_debug" / "10.1000_rec_record_prompt.txt"
    assert dump.exists()
    assert "input_tokens=1500" in dump.read_text(encoding="utf-8")


def test_extract_from_fill_source_writes_source_without_llm(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "configs" / "config.yaml")
    run_dir = tmp_path / "run"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "paper_id": "10.1000_src",
                "doi": "10.1000/src",
                "title": "Src Paper",
                "year": 2019,
                "authors_json": '["A Author"]',
                "journal": "Nature",
                "source_type": "journal",
            }
        ]
    ).to_parquet(artifacts / "papers_filtered.parquet")

    ctx = StageContext(
        run_id="testrun",
        run_dir=run_dir,
        artifacts_dir=artifacts,
        config=config,
        store=MagicMock(),
        dry_run=False,
        force=True,
    )
    schema_ref = ExtractionSchemaRef(
        name="source",
        path=str(root / "schemas/example/source.json"),
        fill_from="papers_meta",
    )
    spec = load_schema_spec(schema_ref)
    papers_meta = load_papers_meta_index(ctx)
    out_path = artifacts / "source.json"

    with patch("litcurate.stages.extract_schema.llm_chat") as mock_chat:
        envelope = _extract_from_fill_source(
            ctx=ctx,
            schema_ref=schema_ref,
            spec=spec,
            paper_id="10.1000_src",
            papers_meta=papers_meta,
            out_path=out_path,
        )
        mock_chat.assert_not_called()

    assert envelope.model == "papers_meta"
    assert envelope.payload["doi"] == "10.1000/src"
    assert envelope.payload["title"] == "Src Paper"
    assert out_path.exists()
    assert not (artifacts / "extract_prompt_debug").exists()


def test_extract_schema_writes_incremental_manifest_on_failure(tmp_path: Path) -> None:
    config_path = Path(__file__).resolve().parents[1] / "configs" / "config.yaml"
    config = load_config(config_path)
    config.dry_run = False

    run_dir = tmp_path / "run"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "markdown_clean").mkdir()
    (artifacts / "fulltext_filter_manifest.json").write_text(
        json.dumps({"papers": []}), encoding="utf-8"
    )
    (artifacts / "clean_manifest.json").write_text(
        json.dumps(
            {
                "cleaned": [
                    {
                        "paper_id": "10.1000_test",
                        "status": "success",
                        "path": "artifacts/markdown_clean/10.1000_test.md",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (artifacts / "markdown_clean" / "10.1000_test.md").write_text(
        "# Test\nSome markdown.", encoding="utf-8"
    )
    (artifacts / "pre_extract_manifest.json").write_text(
        json.dumps({"papers": [{"paper_id": "10.1000_test", "status": "pass"}]}),
        encoding="utf-8",
    )
    (artifacts / "fulltext_filter_manifest.json").write_text(
        json.dumps({"papers": [{"paper_id": "10.1000_test", "keep": True}]}),
        encoding="utf-8",
    )

    store = MagicMock()
    store.is_stage_completed.return_value = False
    ctx = StageContext(
        run_id="testrun",
        run_dir=run_dir,
        artifacts_dir=artifacts,
        config=config,
        store=store,
        dry_run=False,
        force=True,
    )

    spec = load_schema_spec(
        ExtractionSchemaRef(
            name="record",
            path=str(Path(__file__).resolve().parents[1] / "schemas" / "example" / "record.json"),
            prompt=str(Path(__file__).resolve().parents[1] / "prompts" / "example" / "record.md"),
        )
    )
    invalid_payload = {"eos_entries": [{"phase": "MgO"}]}  # missing eos_model, evidence

    with patch("litcurate.stages.extract_schema.llm_require_configured"):
        with patch("litcurate.stages.extract_schema.llm_chat") as mock_chat:
            mock_chat.return_value = MagicMock(text=json.dumps(invalid_payload))
            with patch("litcurate.stages.extract_schema.load_schema_spec", return_value=spec):
                ExtractSchemaStage().run(ctx)

    manifest = read_json(artifacts / "extract_manifest.json")
    assert len(manifest["extractions"]) == 1
    assert manifest["extractions"][0]["status"] == "failed"
    assert "failed validation" in manifest["extractions"][0]["error"]

    failure = read_json(artifacts / "extraction_failures" / "10.1000_test" / "record.json")
    assert failure["validation_errors"]
