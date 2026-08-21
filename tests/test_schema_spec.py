"""Tests for schema loading and validation."""

from __future__ import annotations

from pathlib import Path

import yaml

from litcurate.config import ExtractionSchemaRef, load_config
from litcurate.schema_spec import SchemaFormat, load_schema_spec


def test_load_json_schema_spec() -> None:
    root = Path(__file__).resolve().parents[1]
    ref = ExtractionSchemaRef(
        name="record",
        path=str(root / "schemas/example/record.json"),
            prompt=str(root / "prompts/example/prompt.md"),
        version="2.1",
    )
    spec = load_schema_spec(ref)
    assert spec.format == SchemaFormat.JSON_SCHEMA
    assert spec.version == "2.1"
    assert spec.json_schema["required"] == ["eos_entries"]


def test_load_yaml_schema_spec(tmp_path: Path) -> None:
    schema = {
        "type": "object",
        "required": ["title"],
        "properties": {"title": {"type": "string"}},
    }
    path = tmp_path / "record.yaml"
    path.write_text(yaml.safe_dump(schema), encoding="utf-8")
    ref = ExtractionSchemaRef(
        name="record",
        format="yaml_schema",
        path=str(path),
        prompt=str(path),
    )
    spec = load_schema_spec(ref)
    assert spec.format == SchemaFormat.YAML_SCHEMA
    result = spec.validate_payload({"title": "Example"})
    assert result.valid is True


def test_load_pydantic_schema_spec() -> None:
    ref = ExtractionSchemaRef(
        name="record_list",
        format="pydantic",
        path="tests.fixtures.pydantic_models:ExampleRecordList",
        prompt="prompts/example/prompt.md",
    )
    spec = load_schema_spec(ref)
    assert spec.format == SchemaFormat.PYDANTIC
    assert spec.pydantic_model is not None
    result = spec.validate_payload({"records": []})
    assert result.valid is True


def test_validate_payload_rejects_invalid_sample() -> None:
    root = Path(__file__).resolve().parents[1]
    ref = ExtractionSchemaRef(
        name="record",
        path=str(root / "schemas/example/record.json"),
        prompt=str(root / "prompts/example/prompt.md"),
    )
    spec = load_schema_spec(ref)
    result = spec.validate_payload({"eos_entries": [{"phase": "MgO"}]})
    assert result.valid is False
    assert result.errors


def test_config_resolves_schema_paths() -> None:
    config_path = Path(__file__).resolve().parents[1] / "configs" / "config.yaml"
    config = load_config(config_path)
    record = next(s for s in config.extraction.schemas if s.name == "record")
    assert Path(record.path).is_absolute()
    assert record.path.endswith("record.json")
    assert Path(record.prompt).is_absolute()
    assert record.prompt.endswith("prompt.md")
