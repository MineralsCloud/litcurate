"""Load extraction schemas from JSON Schema, YAML, or Pydantic model references."""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from pydantic import BaseModel

from litcurate.config import ExtractionSchemaRef
from litcurate.extraction_envelope import ValidationResult
from litcurate.schema_declarative import compile_declarative_schema


class SchemaFormat(str, Enum):
    JSON_SCHEMA = "json_schema"
    YAML_SCHEMA = "yaml_schema"
    DECLARATIVE_YAML = "declarative_yaml"
    PYDANTIC = "pydantic"


@dataclass(frozen=True)
class LoadedSchemaSpec:
    name: str
    format: SchemaFormat
    version: str
    json_schema: dict[str, Any]
    pydantic_model: type[BaseModel] | None = None

    def validate_payload(self, payload: dict[str, Any]) -> ValidationResult:
        if self.pydantic_model is not None:
            try:
                self.pydantic_model.model_validate(payload)
            except Exception as exc:
                return ValidationResult(valid=False, errors=[str(exc)])
            return ValidationResult(valid=True)

        validator = Draft202012Validator(self.json_schema)
        errors = sorted(validator.iter_errors(payload), key=lambda err: err.path)
        if errors:
            return ValidationResult(
                valid=False,
                errors=[err.message for err in errors],
            )
        return ValidationResult(valid=True)


def load_schema_spec(ref: ExtractionSchemaRef) -> LoadedSchemaSpec:
    """Load and normalize a configured extraction schema reference."""
    schema_format = SchemaFormat(ref.format)
    if schema_format == SchemaFormat.PYDANTIC:
        model = _import_pydantic_model(ref.path)
        json_schema = model.model_json_schema()
        version = ref.version or _schema_version_from_dict(json_schema)
        return LoadedSchemaSpec(
            name=ref.name,
            format=schema_format,
            version=version,
            json_schema=json_schema,
            pydantic_model=model,
        )

    path = Path(ref.path)
    raw = _load_schema_file(path, schema_format)
    if not isinstance(raw, dict):
        raise ValueError(f"Schema file must define an object: {path}")
    json_schema = (
        compile_declarative_schema(raw)
        if schema_format == SchemaFormat.DECLARATIVE_YAML
        else raw
    )
    version = ref.version or _schema_version_from_dict(json_schema)
    return LoadedSchemaSpec(
        name=ref.name,
        format=schema_format,
        version=version,
        json_schema=json_schema,
    )


def _load_schema_file(path: Path, schema_format: SchemaFormat) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if schema_format in {SchemaFormat.YAML_SCHEMA, SchemaFormat.DECLARATIVE_YAML}:
        loaded = yaml.safe_load(text)
    else:
        loaded = json.loads(text)
    if not isinstance(loaded, dict):
        raise ValueError(f"Schema file must define an object: {path}")
    return loaded


def _import_pydantic_model(path: str) -> type[BaseModel]:
    if ":" not in path:
        raise ValueError(
            "Pydantic schema path must be 'module.path:ClassName', "
            f"got {path!r}"
        )
    module_name, class_name = path.rsplit(":", 1)
    module = importlib.import_module(module_name)
    model = getattr(module, class_name, None)
    if model is None:
        raise AttributeError(f"Module {module_name!r} has no attribute {class_name!r}")
    if not isinstance(model, type) or not issubclass(model, BaseModel):
        raise TypeError(f"{path!r} is not a Pydantic BaseModel subclass")
    return model


def _schema_version_from_dict(schema: dict[str, Any]) -> str:
    for key in ("version", "$id"):
        value = schema.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    title = schema.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    return "1.0"
