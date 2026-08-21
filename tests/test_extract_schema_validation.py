"""Tests for extraction validation behavior."""

from __future__ import annotations

from pathlib import Path

from litcurate.config import ExtractionSchemaRef
from litcurate.extraction_envelope import build_extraction_envelope, envelope_to_dict
from litcurate.schema_spec import load_schema_spec


def test_envelope_written_shape_matches_contract() -> None:
    spec = load_schema_spec(
        ExtractionSchemaRef(
            name="record",
            path=str(
                Path(__file__).resolve().parents[1] / "schemas" / "example" / "record.json"
            ),
            prompt=str(
                Path(__file__).resolve().parents[1] / "prompts" / "example" / "record.md"
            ),
        )
    )
    payload = {
        "eos_entries": [
            {
                "phase": "ExamplePhase",
                "eos_model": "BM3",
                "evidence": "K0 is 106 (2) GPa",
            }
        ]
    }
    validation = spec.validate_payload(payload)
    assert validation.valid is True

    envelope = build_extraction_envelope(
        schema_name="record",
        schema_version=spec.version,
        schema_format=spec.format.value,
        paper_id="10.1000_test",
        model="claude-sonnet-4-6",
        payload=payload,
        validation=validation,
    )
    data = envelope_to_dict(envelope)
    assert data["payload"] == payload
    assert data["schema_name"] == "record"
    assert "extracted_at" in data
