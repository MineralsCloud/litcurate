"""Tests for declarative YAML schema compilation."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from litcurate.config import ExtractionSchemaRef
from litcurate.schema_declarative import compile_declarative_schema, is_declarative_schema
from litcurate.schema_spec import SchemaFormat, load_schema_spec


def test_is_declarative_schema() -> None:
    assert is_declarative_schema({"fields": {"title": "string"}}) is True
    assert is_declarative_schema({"type": "object", "properties": {}}) is False


def test_compile_simple_object() -> None:
    compiled = compile_declarative_schema(
        {
            "title": "Record",
            "fields": {
                "title": "string",
                "notes": "string?",
            },
        }
    )
    assert compiled["type"] == "object"
    assert compiled["required"] == ["title"]
    assert compiled["properties"]["title"] == {"type": "string"}
    assert "notes" in compiled["properties"]


def test_compile_array_object_and_enum() -> None:
    compiled = compile_declarative_schema(
        {
            "fields": {
                "items": {
                    "array": {
                        "required": ["name", "status"],
                        "fields": {
                            "name": "string",
                            "status": "enum(open, closed)",
                            "value": "string|number?",
                        },
                    }
                }
            }
        }
    )
    item_schema = compiled["properties"]["items"]["items"]
    assert item_schema["required"] == ["name", "status"]
    assert item_schema["properties"]["status"]["enum"] == ["open", "closed"]
    assert item_schema["properties"]["value"]["type"] == ["string", "number"]


def test_declarative_yaml_matches_json_schema_validation() -> None:
    root = Path(__file__).resolve().parents[1]
    json_spec = load_schema_spec(
        ExtractionSchemaRef(
            name="record",
            format="json_schema",
            path=str(root / "schemas/example/record.json"),
            prompt=str(root / "prompts/example/prompt.md"),
        )
    )
    yaml_spec = load_schema_spec(
        ExtractionSchemaRef(
            name="record",
            format="declarative_yaml",
            path=str(root / "schemas/example/record.yaml"),
            prompt=str(root / "prompts/example/prompt.md"),
        )
    )
    assert yaml_spec.format == SchemaFormat.DECLARATIVE_YAML

    sample = {
        "eos_entries": [
            {
                "phase": "ExamplePhase",
                "eos_model": "BM3",
                "K0": "106 (2)",
                "K0_unit": "GPa",
                "evidence": "Table 2 reports K0 = 106 (2) GPa.",
            }
        ]
    }
    assert json_spec.validate_payload(sample).valid is True
    assert yaml_spec.validate_payload(sample).valid is True


def test_load_declarative_yaml_from_file(tmp_path: Path) -> None:
    schema = {
        "title": "Widget",
        "fields": {"name": "string"},
    }
    path = tmp_path / "widget.yaml"
    path.write_text(yaml.safe_dump(schema), encoding="utf-8")
    spec = load_schema_spec(
        ExtractionSchemaRef(
            name="widget",
            format="declarative_yaml",
            path=str(path),
            prompt=str(path),
        )
    )
    assert spec.json_schema["title"] == "Widget"
    assert spec.validate_payload({"name": "x"}).valid is True


def test_example_record_yaml_compiles_with_metadata() -> None:
    root = Path(__file__).resolve().parents[1]
    raw = yaml.safe_load(
        (root / "schemas/example/record.yaml").read_text(encoding="utf-8")
    )
    compiled = compile_declarative_schema(raw)
    assert compiled["title"] == "RecordList"
    assert compiled["version"] == "2.1"
    assert compiled["required"] == ["eos_entries"]
    assert "$schema" in compiled
    json.loads(json.dumps(compiled))
