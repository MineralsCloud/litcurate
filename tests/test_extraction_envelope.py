"""Tests for extraction envelope helpers."""

from __future__ import annotations

from litcurate.extraction_envelope import (
    ValidationResult,
    build_extraction_envelope,
    envelope_to_dict,
    is_envelope,
    unwrap_payload,
)


def test_unwrap_legacy_flat_payload() -> None:
    payload = {"records": [{"title": "Example"}]}
    assert unwrap_payload(payload) == payload
    assert is_envelope(payload) is False


def test_unwrap_envelope_payload() -> None:
    envelope = build_extraction_envelope(
        schema_name="record",
        schema_version="1.0",
        schema_format="json_schema",
        paper_id="10.1000_test",
        model="claude-sonnet-4-6",
        payload={"records": []},
        validation=ValidationResult(valid=True),
    )
    data = envelope_to_dict(envelope)
    assert is_envelope(data) is True
    assert unwrap_payload(data) == {"records": []}
    assert data["schema_name"] == "record"
    assert data["validation"]["valid"] is True
