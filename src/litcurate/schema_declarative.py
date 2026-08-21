"""Compile simplified declarative YAML schemas into JSON Schema."""

from __future__ import annotations

import re
from typing import Any

_SCALAR_TYPES = frozenset({"string", "number", "integer", "boolean"})
_ENUM_PATTERN = re.compile(r"^enum\((.+)\)$")


def compile_declarative_schema(doc: dict[str, Any]) -> dict[str, Any]:
    """Compile a declarative schema document to JSON Schema draft 2020-12."""
    if "fields" not in doc:
        raise ValueError("Declarative schema must include a top-level 'fields' mapping")

    object_schema = _compile_object_schema(doc["fields"], doc.get("required"))
    schema: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        **object_schema,
    }
    for key in ("title", "version", "$id", "description"):
        if key in doc:
            schema[key] = doc[key]
    return schema


def is_declarative_schema(doc: dict[str, Any]) -> bool:
    """Return True when a loaded YAML dict uses the declarative DSL."""
    return "fields" in doc and "properties" not in doc and "type" not in doc


def _compile_object_schema(
    fields: dict[str, Any],
    required_override: list[str] | None,
) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    optional: set[str] = set()

    for name, spec in fields.items():
        prop_schema, is_optional = _compile_field_spec(spec)
        properties[name] = prop_schema
        if is_optional:
            optional.add(name)

    if required_override is not None:
        required = list(required_override)
    else:
        required = [name for name in fields if name not in optional]

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _compile_field_spec(spec: Any) -> tuple[dict[str, Any], bool]:
    if isinstance(spec, str):
        return _parse_type_shorthand(spec)

    if not isinstance(spec, dict):
        raise ValueError(f"Unsupported field spec: {spec!r}")

    if "array" in spec:
        return {"type": "array", "items": _compile_array_items(spec["array"])}, False

    if "object" in spec:
        return _compile_object_block(spec["object"]), False

    if "fields" in spec:
        return _compile_object_schema(spec["fields"], spec.get("required")), False

    if "type" in spec:
        schema = dict(spec)
        return schema, bool(spec.get("optional", False))

    if "enum" in spec:
        enum_type = spec.get("type", "string")
        return {"type": enum_type, "enum": list(spec["enum"])}, bool(spec.get("optional", False))

    raise ValueError(f"Unsupported field spec object: {spec!r}")


def _compile_array_items(inner: Any) -> dict[str, Any]:
    if isinstance(inner, str):
        schema, _optional = _parse_type_shorthand(inner)
        return schema
    if not isinstance(inner, dict):
        raise ValueError(f"Unsupported array item spec: {inner!r}")
    return _compile_object_block(inner)


def _compile_object_block(inner: dict[str, Any]) -> dict[str, Any]:
    if "fields" in inner:
        return _compile_object_schema(inner["fields"], inner.get("required"))
    fields = {key: value for key, value in inner.items() if key != "required"}
    return _compile_object_schema(fields, inner.get("required"))


def _parse_type_shorthand(value: str) -> tuple[dict[str, Any], bool]:
    optional = value.endswith("?")
    if optional:
        value = value[:-1].strip()

    enum_match = _ENUM_PATTERN.match(value)
    if enum_match:
        enum_values = [part.strip() for part in enum_match.group(1).split(",") if part.strip()]
        return {"type": "string", "enum": enum_values}, optional

    if "|" in value:
        types = [part.strip() for part in value.split("|") if part.strip()]
        for item in types:
            if item not in _SCALAR_TYPES:
                raise ValueError(f"Unsupported union type: {item!r}")
        return {"type": types}, optional

    if value not in _SCALAR_TYPES:
        raise ValueError(f"Unsupported type shorthand: {value!r}")

    schema: dict[str, Any] = {"type": value}
    return schema, optional
