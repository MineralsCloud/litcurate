"""Environment variable helpers."""

from __future__ import annotations

import os
from pathlib import Path


def get_env(name: str) -> str | None:
    """Return an env var with surrounding whitespace/newlines stripped."""
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _candidate_env_paths() -> list[Path]:
    """Locate `.env` near the package or the current working directory."""
    paths: list[Path] = []
    # Editable/src layout: src/litcurate/env.py -> project root
    package_root = Path(__file__).resolve().parents[2]
    paths.append(package_root / ".env")
    # Installed package or alternate layout: walk up from this file
    for parent in Path(__file__).resolve().parents:
        paths.append(parent / ".env")
    # Always try the process cwd (typical when running from the repo root)
    paths.append(Path.cwd() / ".env")

    ordered: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        ordered.append(resolved)
    return ordered


def load_project_env() -> None:
    """Load the first existing `.env` found near the project or cwd."""
    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        raise RuntimeError(
            "python-dotenv is required to load .env files. "
            "Install LitCurate dependencies with: pip install -e ."
        ) from exc

    for env_path in _candidate_env_paths():
        if env_path.is_file():
            load_dotenv(env_path, override=False)
            return
