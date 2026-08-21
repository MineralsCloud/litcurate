"""Extraction result envelopes with validation metadata and provenance."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class ValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)


class ExtractionEnvelope(BaseModel):
    schema_name: str
    schema_version: str
    schema_format: str
    paper_id: str
    extracted_at: datetime
    model: str
    payload: dict[str, Any]
    validation: ValidationResult


def is_envelope(data: dict[str, Any]) -> bool:
    return isinstance(data.get("payload"), dict) and "schema_name" in data


def unwrap_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Return the reported extraction payload from an envelope or legacy flat JSON."""
    if is_envelope(data):
        return data["payload"]
    return data


def build_extraction_envelope(
    *,
    schema_name: str,
    schema_version: str,
    schema_format: str,
    paper_id: str,
    model: str,
    payload: dict[str, Any],
    validation: ValidationResult,
    extracted_at: datetime | None = None,
) -> ExtractionEnvelope:
    return ExtractionEnvelope(
        schema_name=schema_name,
        schema_version=schema_version,
        schema_format=schema_format,
        paper_id=paper_id,
        extracted_at=extracted_at or datetime.now(timezone.utc),
        model=model,
        payload=payload,
        validation=validation,
    )


def envelope_to_dict(envelope: ExtractionEnvelope) -> dict[str, Any]:
    return envelope.model_dump(mode="json")
