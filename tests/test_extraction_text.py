"""Tests for extraction markdown path selection."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from litcurate.extraction_text import markdown_path_for_extraction, prepare_extraction_markdown


class _FakeCtx:
    def __init__(self, run_dir: Path, section_mode: str) -> None:
        self.run_dir = run_dir
        self.config = SimpleNamespace(
            extraction=SimpleNamespace(
                section_mode=section_mode,
                markdown_max_chars=100,
            )
        )

    def artifact(self, *parts: str) -> Path:
        path = self.run_dir.joinpath(*parts)
        return path

    def resolve_manifest_path(self, stored: str | None, default: Path) -> Path:
        if not stored:
            return default
        candidate = self.run_dir / stored
        return candidate if candidate.exists() else default


def test_markdown_path_full_document(tmp_path: Path) -> None:
    ctx = _FakeCtx(tmp_path, "full_document")
    path = markdown_path_for_extraction(ctx, "10.1_test", clean_manifest_path=None)
    assert path == tmp_path / "markdown" / "10.1_test.md"


def test_markdown_path_cleaned_markdown(tmp_path: Path) -> None:
    ctx = _FakeCtx(tmp_path, "cleaned_markdown")
    path = markdown_path_for_extraction(
        ctx,
        "10.1_test",
        clean_manifest_path="markdown_clean/10.1_test.md",
    )
    assert path == tmp_path / "markdown_clean" / "10.1_test.md"


def test_prepare_extraction_markdown_truncates() -> None:
    text = "x" * 200
    cfg = SimpleNamespace(markdown_max_chars=50)
    assert prepare_extraction_markdown(text, extraction_cfg=cfg) == "x" * 50
