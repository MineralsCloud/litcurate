"""Prepare markdown text for LLM extraction stages."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from litcurate.config import ExtractionConfig, ExtractionSchemaRef


class _ExtractionPathContext(Protocol):
    def artifact(self, *parts: str) -> Path: ...

    def resolve_manifest_path(
        self, stored: str | Path | None, fallback: Path | None = None
    ) -> Path: ...

    @property
    def config(self) -> Any: ...


def markdown_path_for_extraction(
    ctx: _ExtractionPathContext,
    paper_id: str,
    *,
    clean_manifest_path: str | None,
) -> Path:
    """Resolve which markdown file extract_schema should send to the model."""
    mode = ctx.config.extraction.section_mode
    if mode == "full_document":
        return ctx.artifact("markdown", f"{paper_id}.md")
    if mode != "cleaned_markdown":
        raise ValueError(
            f"extraction.section_mode must be 'full_document' or 'cleaned_markdown', got {mode!r}"
        )
    fallback = ctx.artifact("markdown_clean", f"{paper_id}.md")
    if not clean_manifest_path:
        return fallback
    return ctx.resolve_manifest_path(clean_manifest_path, fallback)


def prepare_extraction_markdown(
    markdown: str,
    *,
    extraction_cfg: ExtractionConfig,
    schema_ref: ExtractionSchemaRef | None = None,
) -> str:
    max_chars = extraction_cfg.markdown_max_chars
    if schema_ref and schema_ref.markdown_max_chars is not None:
        max_chars = schema_ref.markdown_max_chars
    return markdown[:max_chars]
