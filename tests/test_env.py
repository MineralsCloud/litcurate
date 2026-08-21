"""Tests for .env loading."""

from __future__ import annotations

from pathlib import Path

from litcurate.env import _candidate_env_paths, get_env, load_project_env


def test_get_env_strips_whitespace(monkeypatch) -> None:
    monkeypatch.setenv("LITCURATE_TEST_KEY", "  value  \n")
    assert get_env("LITCURATE_TEST_KEY") == "value"


def test_get_env_empty_is_none(monkeypatch) -> None:
    monkeypatch.setenv("LITCURATE_TEST_KEY", "   ")
    assert get_env("LITCURATE_TEST_KEY") is None


def test_load_project_env_reads_cwd_dotenv(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("OPENALEX_EMAIL=test@example.com\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENALEX_EMAIL", raising=False)

    load_project_env()
    assert get_env("OPENALEX_EMAIL") == "test@example.com"


def test_candidate_env_paths_include_cwd(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    paths = _candidate_env_paths()
    assert (tmp_path / ".env").resolve() in paths
