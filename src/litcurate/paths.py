"""Run directory layout helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from litcurate.constants import DEFAULT_RUNS_DIR

_MANIFEST_PATH_KEYS = frozenset({"path", "jsonl", "csv"})


def project_runs_dir(cwd: Path | None = None) -> Path:
    return (cwd or Path.cwd()) / DEFAULT_RUNS_DIR


def run_directory(runs_dir: Path, run_id: str) -> Path:
    return runs_dir / run_id


def artifacts_directory(run_dir: Path) -> Path:
    return run_dir / "artifacts"


def logs_directory(run_dir: Path) -> Path:
    return run_dir / "logs"


def normalize_stored_path(run_dir: Path, stored: str) -> str:
    """Convert a stored manifest path to a run-relative POSIX path when possible."""
    if not stored:
        return stored

    path = Path(stored)
    if not path.is_absolute():
        return path.as_posix()

    resolved_run = run_dir.resolve()
    try:
        return path.resolve().relative_to(resolved_run).as_posix()
    except ValueError:
        posix = path.as_posix()
        marker = "/artifacts/"
        if marker in posix:
            return "artifacts/" + posix.split(marker, 1)[1]
        run_marker = f"/runs/{run_dir.name}/artifacts/"
        if run_marker in posix:
            return "artifacts/" + posix.split(run_marker, 1)[1]
        return posix


def store_run_path(run_dir: Path, path: Path) -> str:
    """Serialize a path relative to the run directory for portable manifests."""
    return normalize_stored_path(run_dir, str(path.resolve()))


def resolve_run_path(run_dir: Path, stored: str | Path) -> Path:
    """Resolve a manifest path against the run directory."""
    normalized = normalize_stored_path(run_dir, str(stored))
    candidate = (run_dir / normalized).resolve()
    if candidate.exists():
        return candidate

    path = Path(stored)
    if path.is_absolute() and path.exists():
        return path.resolve()

    return candidate


def rewrite_manifest_paths(run_dir: Path, payload: Any) -> int:
    """Rewrite absolute manifest paths in-place; return number of paths changed."""
    changed = 0

    def _walk(obj: Any) -> None:
        nonlocal changed
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in _MANIFEST_PATH_KEYS and isinstance(value, str):
                    normalized = normalize_stored_path(run_dir, value)
                    if normalized != value:
                        obj[key] = normalized
                        changed += 1
                else:
                    _walk(value)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(payload)
    return changed


def list_manifest_json_files(run_dir: Path) -> list[Path]:
    """Return manifest-like JSON files under a run that may contain stored paths."""
    artifacts_dir = artifacts_directory(run_dir)
    if not artifacts_dir.exists():
        return []

    files = sorted(artifacts_dir.glob("*manifest*.json"))
    summary_path = artifacts_dir / "output" / "export_summary.json"
    if summary_path.exists():
        files.append(summary_path)
    return files


def normalize_run_manifests(run_dir: Path) -> dict[str, int]:
    """Rewrite all manifest JSON files under a run to use relative paths."""
    run_dir = run_dir.resolve()
    results: dict[str, int] = {}

    for manifest_path in list_manifest_json_files(run_dir):
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        changed = rewrite_manifest_paths(run_dir, payload)
        if changed:
            manifest_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        results[manifest_path.name] = changed
    return results
