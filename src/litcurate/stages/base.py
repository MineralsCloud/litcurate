"""Stage base types and context."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from litcurate.config import PipelineConfig
from litcurate.paths import resolve_run_path, store_run_path
from litcurate.run_store import RunStore


@dataclass
class StageContext:
    run_id: str
    run_dir: Path
    artifacts_dir: Path
    config: PipelineConfig
    store: RunStore
    dry_run: bool = False
    force: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def artifact(self, *parts: str) -> Path:
        path = self.artifacts_dir.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def store_path(self, path: Path) -> str:
        """Store an artifact path relative to this run for portable manifests."""
        return store_run_path(self.run_dir, path)

    def resolve_path(self, stored: str | Path) -> Path:
        """Resolve a stored manifest path against this run directory."""
        return resolve_run_path(self.run_dir, stored)

    def resolve_manifest_path(self, stored: str | Path, fallback: Path | None = None) -> Path:
        """Resolve a manifest path, optionally falling back to a standard artifact location."""
        resolved = self.resolve_path(stored)
        if resolved.exists():
            return resolved
        if fallback is not None and fallback.exists():
            return fallback
        return resolved


@dataclass
class StageResult:
    artifact_path: Path | None = None
    message: str = ""
    papers_touched: int = 0


class Stage(ABC):
    name: str
    description: str

    @abstractmethod
    def run(self, ctx: StageContext) -> StageResult:
        """Execute the stage. Raise on unrecoverable failure."""

    def should_skip(self, ctx: StageContext) -> bool:
        return ctx.store.is_stage_completed(ctx.run_id, self.name)
