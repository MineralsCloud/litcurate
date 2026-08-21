"""Optional Pydantic models for format: pydantic schema refs in tests/examples."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExampleRecord(BaseModel):
    title: str
    evidence_text: str
    confidence: float | None = None


class ExampleRecordList(BaseModel):
    records: list[ExampleRecord] = Field(default_factory=list)
