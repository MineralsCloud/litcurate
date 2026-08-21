"""SQLite run ledger for checkpoint/resume."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from litcurate.constants import (
    PAPER_STAGE_FIELDS,
    STAGE_ORDER,
    PaperStageStatus,
    RunStatus,
    StageStatus,
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RunRecord:
    id: str
    config_path: str
    config_snapshot_path: str
    name: str
    status: str
    created_at: str
    updated_at: str
    run_dir: str


@dataclass
class StageRecord:
    run_id: str
    stage_name: str
    status: str
    started_at: str | None
    finished_at: str | None
    error_message: str | None
    artifact_path: str | None


@dataclass
class PaperRecord:
    run_id: str
    paper_id: str
    doi: str | None
    title: str | None
    download_status: str
    convert_status: str
    clean_status: str
    extract_status: str
    verify_status: str
    last_error: str | None
    metadata_json: str | None


class RunStore:
    """SQLite-backed ledger for pipeline runs, stages, and per-paper progress."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    config_path TEXT NOT NULL,
                    config_snapshot_path TEXT NOT NULL,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    run_dir TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS stages (
                    run_id TEXT NOT NULL,
                    stage_name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    started_at TEXT,
                    finished_at TEXT,
                    error_message TEXT,
                    artifact_path TEXT,
                    PRIMARY KEY (run_id, stage_name),
                    FOREIGN KEY (run_id) REFERENCES runs(id)
                );

                CREATE TABLE IF NOT EXISTS papers (
                    run_id TEXT NOT NULL,
                    paper_id TEXT NOT NULL,
                    doi TEXT,
                    title TEXT,
                    download_status TEXT NOT NULL DEFAULT 'pending',
                    convert_status TEXT NOT NULL DEFAULT 'pending',
                    clean_status TEXT NOT NULL DEFAULT 'pending',
                    extract_status TEXT NOT NULL DEFAULT 'pending',
                    verify_status TEXT NOT NULL DEFAULT 'pending',
                    last_error TEXT,
                    metadata_json TEXT,
                    PRIMARY KEY (run_id, paper_id),
                    FOREIGN KEY (run_id) REFERENCES runs(id)
                );

                CREATE TABLE IF NOT EXISTS api_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    stage_name TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    label TEXT,
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    cost_usd REAL NOT NULL DEFAULT 0,
                    pricing_known INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES runs(id)
                );
                """
            )

    def create_run(
        self,
        *,
        config_path: Path,
        config_snapshot_path: Path,
        name: str,
        run_dir: Path,
        run_id: str | None = None,
    ) -> RunRecord:
        run_id = run_id or uuid.uuid4().hex[:12]
        now = _utcnow()
        record = RunRecord(
            id=run_id,
            config_path=str(config_path.resolve()),
            config_snapshot_path=str(config_snapshot_path.resolve()),
            name=name,
            status=RunStatus.PENDING.value,
            created_at=now,
            updated_at=now,
            run_dir=str(run_dir.resolve()),
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    id, config_path, config_snapshot_path, name, status,
                    created_at, updated_at, run_dir
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.config_path,
                    record.config_snapshot_path,
                    record.name,
                    record.status,
                    record.created_at,
                    record.updated_at,
                    record.run_dir,
                ),
            )
            for stage_name in STAGE_ORDER:
                conn.execute(
                    """
                    INSERT INTO stages (run_id, stage_name, status)
                    VALUES (?, ?, ?)
                    """,
                    (run_id, stage_name, StageStatus.PENDING.value),
                )
        return record

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        return RunRecord(**dict(row))

    def list_runs(self, limit: int = 20) -> list[RunRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [RunRecord(**dict(row)) for row in rows]

    def update_run_status(self, run_id: str, status: RunStatus) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE runs SET status = ?, updated_at = ? WHERE id = ?",
                (status.value, _utcnow(), run_id),
            )

    def get_stage(self, run_id: str, stage_name: str) -> StageRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM stages WHERE run_id = ? AND stage_name = ?",
                (run_id, stage_name),
            ).fetchone()
        if row is None:
            return None
        return StageRecord(**dict(row))

    def list_stages(self, run_id: str) -> list[StageRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM stages WHERE run_id = ?
                ORDER BY CASE stage_name
                    WHEN 'query_generation' THEN 1
                    WHEN 'openalex_search' THEN 2
                    WHEN 'merge_rank' THEN 3
                    WHEN 'filter_abstracts' THEN 4
                    WHEN 'download_pdfs' THEN 5
                    WHEN 'convert_marker' THEN 6
                    WHEN 'clean_markdown' THEN 7
                    WHEN 'pre_extract' THEN 8
                    WHEN 'filter_fulltext' THEN 9
                    WHEN 'extract_schema' THEN 10
                    WHEN 'export' THEN 11
                    ELSE 99
                END
                """,
                (run_id,),
            ).fetchall()
        return [StageRecord(**dict(row)) for row in rows]

    def start_stage(self, run_id: str, stage_name: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE stages
                SET status = ?, started_at = ?, finished_at = NULL, error_message = NULL
                WHERE run_id = ? AND stage_name = ?
                """,
                (StageStatus.RUNNING.value, _utcnow(), run_id, stage_name),
            )

    def complete_stage(
        self,
        run_id: str,
        stage_name: str,
        *,
        artifact_path: Path | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE stages
                SET status = ?, finished_at = ?, artifact_path = ?, error_message = NULL
                WHERE run_id = ? AND stage_name = ?
                """,
                (
                    StageStatus.COMPLETED.value,
                    _utcnow(),
                    str(artifact_path) if artifact_path else None,
                    run_id,
                    stage_name,
                ),
            )

    def fail_stage(self, run_id: str, stage_name: str, error_message: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE stages
                SET status = ?, finished_at = ?, error_message = ?
                WHERE run_id = ? AND stage_name = ?
                """,
                (StageStatus.FAILED.value, _utcnow(), error_message, run_id, stage_name),
            )

    def skip_stage(self, run_id: str, stage_name: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE stages
                SET status = ?, finished_at = ?
                WHERE run_id = ? AND stage_name = ?
                """,
                (StageStatus.SKIPPED.value, _utcnow(), run_id, stage_name),
            )

    def reset_stage(self, run_id: str, stage_name: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE stages
                SET status = ?, started_at = NULL, finished_at = NULL,
                    error_message = NULL, artifact_path = NULL
                WHERE run_id = ? AND stage_name = ?
                """,
                (StageStatus.PENDING.value, run_id, stage_name),
            )

    def reset_paper_stage_field(
        self,
        run_id: str,
        field: str,
        *,
        paper_ids: list[str] | None = None,
        status: PaperStageStatus = PaperStageStatus.PENDING,
    ) -> int:
        """Reset a paper stage field for all papers or a selected subset."""
        if field not in PAPER_STAGE_FIELDS:
            raise ValueError(f"Unknown paper stage field: {field}")
        with self._connect() as conn:
            if paper_ids is None:
                cursor = conn.execute(
                    f"""
                    UPDATE papers
                    SET {field} = ?, last_error = NULL
                    WHERE run_id = ?
                    """,
                    (status.value, run_id),
                )
            else:
                if not paper_ids:
                    return 0
                placeholders = ",".join("?" for _ in paper_ids)
                cursor = conn.execute(
                    f"""
                    UPDATE papers
                    SET {field} = ?, last_error = NULL
                    WHERE run_id = ? AND paper_id IN ({placeholders})
                    """,
                    (status.value, run_id, *paper_ids),
                )
            return int(cursor.rowcount)

    def is_stage_completed(self, run_id: str, stage_name: str) -> bool:
        stage = self.get_stage(run_id, stage_name)
        return stage is not None and stage.status == StageStatus.COMPLETED.value

    def upsert_paper(
        self,
        run_id: str,
        paper_id: str,
        *,
        doi: str | None = None,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        metadata_json = json.dumps(metadata) if metadata is not None else None
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO papers (run_id, paper_id, doi, title, metadata_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id, paper_id) DO UPDATE SET
                    doi = COALESCE(excluded.doi, papers.doi),
                    title = COALESCE(excluded.title, papers.title),
                    metadata_json = COALESCE(excluded.metadata_json, papers.metadata_json)
                """,
                (run_id, paper_id, doi, title, metadata_json),
            )

    def update_paper_stage(
        self,
        run_id: str,
        paper_id: str,
        field: str,
        status: PaperStageStatus,
        *,
        error: str | None = None,
    ) -> None:
        if field not in PAPER_STAGE_FIELDS:
            raise ValueError(f"Unknown paper stage field: {field}")
        with self._connect() as conn:
            conn.execute(
                f"""
                UPDATE papers
                SET {field} = ?, last_error = ?
                WHERE run_id = ? AND paper_id = ?
                """,
                (status.value, error, run_id, paper_id),
            )

    def list_papers(self, run_id: str) -> list[PaperRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM papers WHERE run_id = ? ORDER BY paper_id",
                (run_id,),
            ).fetchall()
        return [PaperRecord(**dict(row)) for row in rows]

    def count_papers_by_status(self, run_id: str, field: str) -> dict[str, int]:
        if field not in PAPER_STAGE_FIELDS:
            raise ValueError(f"Unknown paper stage field: {field}")
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {field} AS status, COUNT(*) AS count
                FROM papers WHERE run_id = ?
                GROUP BY {field}
                """,
                (run_id,),
            ).fetchall()
        return {row["status"]: row["count"] for row in rows}

    def record_api_usage(
        self,
        run_id: str,
        *,
        stage_name: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        label: str | None = None,
        pricing_known: bool = True,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO api_usage (
                    run_id, stage_name, provider, model, label,
                    input_tokens, output_tokens, cost_usd, pricing_known, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    stage_name,
                    provider,
                    model,
                    label,
                    input_tokens,
                    output_tokens,
                    cost_usd,
                    int(pricing_known),
                    _utcnow(),
                ),
            )

    def get_api_cost_summary(self, run_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT stage_name, provider, model, label, input_tokens, output_tokens,
                       cost_usd, pricing_known, created_at
                FROM api_usage
                WHERE run_id = ?
                ORDER BY id
                """,
                (run_id,),
            ).fetchall()

        calls = [dict(row) for row in rows]
        for call in calls:
            call["pricing_known"] = bool(call["pricing_known"])

        total_input = sum(int(call["input_tokens"]) for call in calls)
        total_output = sum(int(call["output_tokens"]) for call in calls)
        total_cost = round(sum(float(call["cost_usd"]) for call in calls), 6)

        by_stage: dict[str, dict[str, Any]] = {}
        by_model: dict[str, dict[str, Any]] = {}
        for call in calls:
            for bucket, key in ((by_stage, call["stage_name"]), (by_model, call["model"])):
                entry = bucket.setdefault(
                    key,
                    {
                        "calls": 0,
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cost_usd": 0.0,
                    },
                )
                entry["calls"] += 1
                entry["input_tokens"] += int(call["input_tokens"])
                entry["output_tokens"] += int(call["output_tokens"])
                entry["cost_usd"] = round(entry["cost_usd"] + float(call["cost_usd"]), 6)

        return {
            "provider": "anthropic",
            "currency": "USD",
            "pricing_note": "Estimated from published per-million-token rates; verify against Anthropic billing.",
            "call_count": len(calls),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_cost_usd": total_cost,
            "by_stage": by_stage,
            "by_model": by_model,
            "calls": calls,
        }


def open_run_store(run_dir: Path) -> RunStore:
    return RunStore(run_dir / "run.db")
