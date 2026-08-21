"""Reset pipeline stage outputs and ledger state for a run."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from litcurate.constants import STAGE_ORDER, PaperStageStatus
from litcurate.run_store import open_run_store
from litcurate.stage_info import STAGE_PAPER_STATUS_FIELDS, STAGE_RESET_ARTIFACTS


@dataclass
class StageResetReport:
    stages: list[str] = field(default_factory=list)
    deleted_paths: list[str] = field(default_factory=list)
    papers: list[str] | None = None
    dry_run: bool = False


def stages_from(stage_name: str, *, and_downstream: bool) -> list[str]:
    if stage_name not in STAGE_ORDER:
        raise ValueError(f"Unknown stage: {stage_name}")
    start = STAGE_ORDER.index(stage_name)
    if and_downstream:
        return list(STAGE_ORDER[start:])
    return [stage_name]


def reset_stage(
    run_dir: Path,
    stage_name: str,
    *,
    and_downstream: bool = False,
    paper_ids: list[str] | None = None,
    dry_run: bool = False,
) -> StageResetReport:
    """Clear stage artifacts and mark stage(s) pending in the run ledger.

    When ``paper_ids`` is set, only paper-scoped files under reset directories
    are removed (manifests for that stage are still removed so the stage can
    rebuild them). Without ``paper_ids``, directories/files are cleared fully.
    """
    if not run_dir.exists():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")
    if stage_name not in STAGE_ORDER:
        raise ValueError(f"Unknown stage: {stage_name}")

    targets = stages_from(stage_name, and_downstream=and_downstream)
    report = StageResetReport(stages=targets, papers=paper_ids, dry_run=dry_run)
    store = open_run_store(run_dir)
    run_id = run_dir.name

    for name in targets:
        for rel in STAGE_RESET_ARTIFACTS.get(name, []):
            deleted = _clear_artifact(
                run_dir,
                rel,
                paper_ids=paper_ids,
                dry_run=dry_run,
            )
            report.deleted_paths.extend(deleted)

        if not dry_run:
            store.reset_stage(run_id, name)
            paper_field = STAGE_PAPER_STATUS_FIELDS.get(name)
            if paper_field:
                store.reset_paper_stage_field(
                    run_id,
                    paper_field,
                    paper_ids=paper_ids,
                    status=PaperStageStatus.PENDING,
                )

    return report


def _clear_artifact(
    run_dir: Path,
    rel: str,
    *,
    paper_ids: list[str] | None,
    dry_run: bool,
) -> list[str]:
    is_dir = rel.endswith("/")
    path = run_dir / rel.rstrip("/")
    deleted: list[str] = []

    if not path.exists():
        return deleted

    if is_dir:
        if paper_ids is None:
            deleted.append(_rel(run_dir, path) + "/")
            if not dry_run:
                shutil.rmtree(path)
            return deleted

        for paper_id in paper_ids:
            deleted.extend(
                _clear_paper_scoped(run_dir, path, paper_id, dry_run=dry_run)
            )
        return deleted

    # File target: always remove (including manifests) so the stage rebuilds.
    deleted.append(_rel(run_dir, path))
    if not dry_run:
        path.unlink()
    return deleted


def _clear_paper_scoped(
    run_dir: Path,
    directory: Path,
    paper_id: str,
    *,
    dry_run: bool,
) -> list[str]:
    deleted: list[str] = []
    if not directory.is_dir():
        return deleted

    # Common layouts: <dir>/<paper_id>.ext and <dir>/<paper_id>/
    candidates: list[Path] = [directory / paper_id]
    for child in directory.iterdir():
        if child.is_file() and child.stem == paper_id:
            candidates.append(child)

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen or not candidate.exists():
            continue
        seen.add(candidate)
        deleted.append(_rel(run_dir, candidate) + ("/" if candidate.is_dir() else ""))
        if dry_run:
            continue
        if candidate.is_dir():
            shutil.rmtree(candidate)
        else:
            candidate.unlink()
    return deleted


def _rel(run_dir: Path, path: Path) -> str:
    try:
        return str(path.relative_to(run_dir))
    except ValueError:
        return str(path)
