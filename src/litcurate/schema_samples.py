"""Generate placeholder extraction payloads for dry-run mode."""

from __future__ import annotations

from typing import Any


def dry_run_sample_from_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Build a minimal JSON object that reflects the schema shape."""
    schema_type = schema.get("type")
    if schema_type == "object":
        return _sample_object(schema)
    if schema_type == "array":
        return _sample_array(schema)
    return {"dry_run": True}


def _sample_object(schema: dict[str, Any]) -> dict[str, Any]:
    props = schema.get("properties", {})
    required = schema.get("required", list(props.keys()))
    result: dict[str, Any] = {}
    for key in required:
        prop = props.get(key, {})
        result[key] = _sample_value(prop, key=key)
    return result


def _sample_array(schema: dict[str, Any]) -> list[Any]:
    items = schema.get("items", {})
    if items.get("type") == "object":
        return [_sample_object(items)]
    return []


def _sample_value(prop: dict[str, Any], *, key: str) -> Any:
    prop_type = prop.get("type")
    if prop_type == "string":
        return f"dry_run_{key}"
    if prop_type == "number":
        return 0.0
    if prop_type == "integer":
        return 0
    if prop_type == "boolean":
        return False
    if prop_type == "array":
        return _sample_array(prop)
    if prop_type == "object":
        return _sample_object(prop)
    return None


def is_empty_list_field(payload: dict[str, Any], field_name: str | None) -> bool:
    if not field_name:
        return False
    value = payload.get(field_name)
    return isinstance(value, list) and len(value) == 0
