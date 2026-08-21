"""Pretty-print stage artifacts for modular testing."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from litcurate.stage_info import STAGE_ARTIFACTS

console = Console()


def show_stage_artifact(run_dir: Path, stage_name: str) -> None:
    meta = STAGE_ARTIFACTS.get(stage_name)
    if meta is None:
        raise ValueError(f"Unknown stage: {stage_name}")

    rel_path = meta["primary"]
    path = run_dir / rel_path
    console.print(Panel(f"[bold]{stage_name}[/bold]\n{meta['description']}", expand=False))
    console.print(f"Path: {path}\n")

    if not path.exists():
        console.print("[yellow]Artifact not found yet.[/yellow]")
        return

    if path.is_dir():
        files = sorted(path.glob("*"))
        table = Table(title=f"Files in {rel_path}")
        table.add_column("File")
        table.add_column("Size (bytes)")
        for file in files[:50]:
            table.add_row(file.name, str(file.stat().st_size))
        console.print(table)
        if len(files) > 50:
            console.print(f"... and {len(files) - 50} more")
        return

    if path.suffix == ".json":
        _show_json(path, stage_name)
        return

    if path.suffix == ".parquet":
        _show_parquet(path)
        return

    if path.suffix == ".jsonl":
        _show_jsonl(path)
        return

    console.print(path.read_text(encoding="utf-8")[:4000])


def _show_json(path: Path, stage_name: str) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))

    if stage_name == "query_generation":
        queries = payload.get("queries", [])
        table = Table(title="Generated queries")
        table.add_column("#", style="dim")
        table.add_column("ID")
        table.add_column("Query")
        table.add_column("Rationale")
        for idx, item in enumerate(queries, 1):
            table.add_row(
                str(idx),
                item.get("id", ""),
                item.get("query", "")[:120],
                (item.get("rationale") or "")[:80],
            )
        console.print(table)
        console.print(f"\nTotal queries: {len(queries)}")
        return

    text = json.dumps(payload, indent=2, ensure_ascii=False)
    console.print(text[:8000])
    if len(text) > 8000:
        console.print("\n[dim]... truncated[/dim]")


def _show_parquet(path: Path) -> None:
    frame = pd.read_parquet(path)
    console.print(f"Rows: {len(frame)}")
    columns = [
        c
        for c in (
            "paper_id",
            "doi",
            "title",
            "year",
            "journal",
            "citation_count",
            "frequency",
            "score",
            "keep",
            "filter_reason",
        )
        if c in frame.columns
    ]
    display = frame[columns] if columns else frame
    console.print(display.head(20).to_string(index=False))
    if len(frame) > 20:
        console.print(f"\n... and {len(frame) - 20} more rows")


def _show_jsonl(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    console.print(f"Records: {len(lines)}")
    for line in lines[:5]:
        console.print(json.dumps(json.loads(line), indent=2, ensure_ascii=False)[:2000])
        console.print()
