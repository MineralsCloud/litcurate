"""litcurate command-line interface."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from litcurate import __version__
from litcurate.constants import STAGE_ORDER, DEFAULT_RUNS_DIR
from litcurate.env import load_project_env
from litcurate.ingest_pdfs import ingest_pdfs
from litcurate.merge_papers_filtered import (
    filtered_parquet_for_run,
    merge_papers_filtered,
)
from litcurate.inspect import show_stage_artifact
from litcurate.paths import (
    list_manifest_json_files,
    normalize_run_manifests,
    project_runs_dir,
    rewrite_manifest_paths,
    run_directory,
)
from litcurate.pipeline import PipelineRunner
from litcurate.reset_stage import reset_stage
from litcurate.run_store import open_run_store
from litcurate.stage_info import STAGE_ARTIFACTS
from litcurate.stages.utils import read_json_if_valid

load_project_env()

app = typer.Typer(
    help="Config-driven literature-to-database pipeline",
    no_args_is_help=True,
)
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"litcurate {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """Config-driven literature-to-database pipeline."""


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


def _resolve_config(config: Path | None, run_dir: Path) -> Path:
    snapshot = run_dir / "config.snapshot.yaml"
    if config is not None:
        return config
    if snapshot.exists():
        return snapshot
    raise typer.BadParameter("Provide --config or ensure config.snapshot.yaml exists in the run")


@app.command()
def run(
    config: Path = typer.Argument(..., help="Path to pipeline YAML config"),
    runs_dir: Path = typer.Option(
        None,
        "--runs-dir",
        help=f"Directory for run outputs (default: ./{DEFAULT_RUNS_DIR})",
    ),
    until_stage: Optional[str] = typer.Option(
        None,
        "--until-stage",
        help=f"Stop after this stage: {', '.join(STAGE_ORDER)}",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Start a new pipeline run."""
    _configure_logging(verbose)
    runner = PipelineRunner(config, runs_dir=runs_dir, until_stage=until_stage)
    run_id = runner.start_new_run()
    console.print(f"[green]Run completed:[/green] {run_id}")
    console.print(f"Artifacts: {run_directory(runner.runs_dir, run_id)}")


@app.command("run-stage")
def run_stage(
    stage: str = typer.Argument(..., help=f"Stage to run: {', '.join(STAGE_ORDER)}"),
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Config path (required for a new run)",
    ),
    run_id: Optional[str] = typer.Option(
        None,
        "--run-id",
        help="Existing run ID (omit to start a new run)",
    ),
    runs_dir: Path = typer.Option(None, "--runs-dir"),
    force: bool = typer.Option(False, "--force", help="Re-run even if already completed"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run a single pipeline stage for modular testing."""
    _configure_logging(verbose)

    if stage not in STAGE_ORDER:
        raise typer.BadParameter(f"Unknown stage '{stage}'. Choose from: {', '.join(STAGE_ORDER)}")

    base_runs = runs_dir or project_runs_dir()

    if run_id is None:
        if config is None:
            raise typer.BadParameter("Provide --config when starting a new run")
        runner = PipelineRunner(config, runs_dir=base_runs, force=force)
    else:
        run_dir = run_directory(base_runs, run_id)
        config_path = _resolve_config(config, run_dir)
        runner = PipelineRunner(config_path, runs_dir=base_runs, run_id=run_id, force=force)

    try:
        result_id = runner.run_stage(stage, run_id=run_id)
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc

    console.print(f"[green]Stage completed:[/green] {stage}")
    console.print(f"Run ID: {result_id}")
    show_stage_artifact(run_directory(base_runs, result_id), stage)


@app.command()
def show(
    stage: str = typer.Argument(..., help=f"Stage artifact to inspect: {', '.join(STAGE_ORDER)}"),
    run_id: str = typer.Argument(..., help="Run ID"),
    runs_dir: Path = typer.Option(None, "--runs-dir"),
) -> None:
    """Show the primary artifact for a stage without re-running it."""
    if stage not in STAGE_ORDER:
        raise typer.BadParameter(f"Unknown stage '{stage}'")
    base_runs = runs_dir or project_runs_dir()
    run_dir = run_directory(base_runs, run_id)
    if not run_dir.exists():
        raise typer.BadParameter(f"Unknown run ID: {run_id}")
    show_stage_artifact(run_dir, stage)


@app.command()
def stages() -> None:
    """List pipeline stages and their primary artifacts."""
    table = Table(title="Pipeline stages")
    table.add_column("#", style="dim")
    table.add_column("Stage")
    table.add_column("Primary artifact")
    table.add_column("Description")
    for idx, name in enumerate(STAGE_ORDER, 1):
        meta = STAGE_ARTIFACTS[name]
        table.add_row(str(idx), name, meta["primary"], meta["description"])
    console.print(table)


@app.command()
def resume(
    run_id: str = typer.Argument(..., help="Existing run ID"),
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        help="Config path (optional if run snapshot exists)",
    ),
    from_stage: Optional[str] = typer.Option(
        None,
        "--from-stage",
        help=f"Restart from stage: {', '.join(STAGE_ORDER)}",
    ),
    until_stage: Optional[str] = typer.Option(
        None,
        "--until-stage",
        help=f"Stop after this stage: {', '.join(STAGE_ORDER)}",
    ),
    force: bool = typer.Option(False, "--force", help="Force re-run from --from-stage onward"),
    runs_dir: Path = typer.Option(None, "--runs-dir"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Resume an existing run, optionally restarting from a stage."""
    _configure_logging(verbose)
    base_runs = runs_dir or project_runs_dir()
    run_dir = run_directory(base_runs, run_id)
    config_path = _resolve_config(config, run_dir)

    runner = PipelineRunner(
        config_path,
        runs_dir=base_runs,
        run_id=run_id,
        from_stage=from_stage,
        until_stage=until_stage,
        force=force,
    )
    runner.resume_run(run_id)
    console.print(f"[green]Run resumed:[/green] {run_id}")


@app.command("status")
def status_cmd(
    run_id: str = typer.Argument(..., help="Run ID"),
    runs_dir: Path = typer.Option(None, "--runs-dir"),
) -> None:
    """Show run and stage status from the SQLite ledger."""
    base_runs = runs_dir or project_runs_dir()
    run_dir = run_directory(base_runs, run_id)
    store = open_run_store(run_dir)
    run = store.get_run(run_id)
    if run is None:
        raise typer.BadParameter(f"Unknown run ID: {run_id}")

    console.print(f"[bold]Run[/bold] {run.id} — {run.name}")
    console.print(f"Status: {run.status}")
    console.print(f"Config: {run.config_snapshot_path}")
    console.print(f"Directory: {run.run_dir}\n")

    table = Table(title="Stages")
    table.add_column("Stage")
    table.add_column("Status")
    table.add_column("Artifact")
    for stage in store.list_stages(run_id):
        table.add_row(stage.stage_name, stage.status, stage.artifact_path or "")
    console.print(table)

    cost_summary = store.get_api_cost_summary(run_id)
    if cost_summary["call_count"]:
        console.print(
            f"\n[bold]Anthropic API usage:[/bold] "
            f"${cost_summary['total_cost_usd']:.4f} "
            f"({cost_summary['call_count']} calls, "
            f"{cost_summary['total_input_tokens']:,} in / "
            f"{cost_summary['total_output_tokens']:,} out tokens)"
        )
        cost_table = Table(title="API cost by stage")
        cost_table.add_column("Stage")
        cost_table.add_column("Calls", justify="right")
        cost_table.add_column("Cost (USD)", justify="right")
        for stage_name, stats in sorted(cost_summary["by_stage"].items()):
            cost_table.add_row(
                stage_name,
                str(stats["calls"]),
                f"${stats['cost_usd']:.4f}",
            )
        console.print(cost_table)
        console.print(f"Details: {run_dir / 'artifacts' / 'api_costs.json'}")

    papers = store.list_papers(run_id)
    if papers:
        console.print(f"\n[bold]Papers tracked:[/bold] {len(papers)}")
        for field in ("download_status", "convert_status", "extract_status"):
            counts = store.count_papers_by_status(run_id, field)
            summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
            console.print(f"  {field}: {summary}")

    clean_manifest = read_json_if_valid(run_dir / "artifacts" / "clean_manifest.json")
    if clean_manifest and "heavy_strip_count" in clean_manifest:
        threshold = clean_manifest.get("heavy_strip_fraction", 0.5)
        count = clean_manifest["heavy_strip_count"]
        console.print(
            f"\n[bold]Markdown clean flags:[/bold] {count} paper(s) stripped "
            f">{threshold:.0%} of content — see clean_manifest.json"
        )


@app.command("ingest-pdfs")
def ingest_pdfs_cmd(
    run_id: str = typer.Option(..., "--run-id", help="Existing run ID"),
    from_dir: Optional[Path] = typer.Option(
        None,
        "--from-dir",
        help="Directory of PDFs to import (default: scan runs/<id>/artifacts/pdfs/)",
    ),
    runs_dir: Path = typer.Option(None, "--runs-dir"),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be ingested without copying or updating manifests",
    ),
) -> None:
    """Register manually downloaded PDFs for papers in an existing run."""
    base_runs = runs_dir or project_runs_dir()
    run_dir = run_directory(base_runs, run_id)
    if not run_dir.exists():
        raise typer.BadParameter(f"Unknown run ID: {run_id}")

    try:
        report = ingest_pdfs(run_dir, from_dir=from_dir, dry_run=dry_run)
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc

    prefix = "[dry-run] " if dry_run else ""
    console.print(
        f"{prefix}[green]Ingested {report.ingested_count} PDFs[/green] "
        f"({len(report.already_success)} already success, "
        f"{len(report.unknown_files)} unknown, "
        f"{len(report.invalid_files)} invalid)"
    )

    if report.ingested:
        table = Table(title=f"{prefix}Newly ingested")
        table.add_column("paper_id")
        table.add_column("source")
        for item in report.ingested:
            table.add_row(item["paper_id"], item["source_file"])
        console.print(table)

    if report.unknown_files:
        console.print("\n[yellow]Unknown files[/yellow] (no matching paper in this run):")
        for name in report.unknown_files:
            console.print(f"  {name}")

    if report.invalid_files:
        console.print("\n[red]Invalid PDFs[/red] (empty or missing %PDF header):")
        for name in report.invalid_files:
            console.print(f"  {name}")


@app.command("merge-filtered")
def merge_filtered_cmd(
    into_run_id: str = typer.Option(
        ...,
        "--into-run-id",
        help="Target run that receives extra papers",
    ),
    from_run_id: str = typer.Option(
        ...,
        "--from-run-id",
        help="Source run whose papers_filtered.parquet will be merged in",
    ),
    runs_dir: Path = typer.Option(None, "--runs-dir"),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be added without writing",
    ),
) -> None:
    """Merge papers_filtered.parquet from one run into another (dedupe by paper_id)."""
    base_runs = runs_dir or project_runs_dir()
    try:
        into_path = filtered_parquet_for_run(base_runs, into_run_id)
        from_path = filtered_parquet_for_run(base_runs, from_run_id)
        report = merge_papers_filtered(into_path, from_path, dry_run=dry_run)
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    prefix = "[dry-run] " if dry_run else ""
    console.print(
        f"{prefix}[green]Merged filtered papers[/green]: "
        f"before={report.before_count}, added={report.added_count}, "
        f"already_present={report.already_present_count}, after={report.after_count}"
    )
    if report.backup_path:
        console.print(f"Backup: {report.backup_path}")
    if report.added_paper_ids:
        table = Table(title=f"{prefix}Newly added paper_ids")
        table.add_column("paper_id")
        for paper_id in report.added_paper_ids:
            table.add_row(paper_id)
        console.print(table)
    if not dry_run and report.added_count:
        console.print(
            "\nNext:\n"
            f"  litcurate ingest-pdfs --run-id {into_run_id} --from-dir <pdf_dir>\n"
            f"  litcurate run-stage convert_marker --run-id {into_run_id} --force"
        )


@app.command("reset-stage")
def reset_stage_cmd(
    stage: str = typer.Argument(..., help=f"Stage to reset: {', '.join(STAGE_ORDER)}"),
    run_id: str = typer.Option(..., "--run-id", help="Existing run ID"),
    and_downstream: bool = typer.Option(
        False,
        "--and-downstream",
        help="Also reset this stage and every later stage",
    ),
    paper_id: Optional[list[str]] = typer.Option(
        None,
        "--paper-id",
        help="Limit reset to one or more paper IDs (repeatable)",
    ),
    runs_dir: Path = typer.Option(None, "--runs-dir"),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be deleted without changing the run",
    ),
) -> None:
    """Clear stage artifacts and mark the stage pending so it can be re-run.

    Unlike --force alone, this deletes cached outputs (e.g. markdown/*.md for
    convert_marker) so the next run-stage actually regenerates them.
    """
    if stage not in STAGE_ORDER:
        raise typer.BadParameter(f"Unknown stage '{stage}'. Choose from: {', '.join(STAGE_ORDER)}")

    base_runs = runs_dir or project_runs_dir()
    run_dir = run_directory(base_runs, run_id)
    if not run_dir.exists():
        raise typer.BadParameter(f"Unknown run ID: {run_id}")

    try:
        report = reset_stage(
            run_dir,
            stage,
            and_downstream=and_downstream,
            paper_ids=paper_id,
            dry_run=dry_run,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    prefix = "[dry-run] " if dry_run else ""
    console.print(
        f"{prefix}[green]Reset stages:[/green] {', '.join(report.stages)}"
    )
    if report.papers:
        console.print(f"Papers: {', '.join(report.papers)}")
    if report.deleted_paths:
        table = Table(title=f"{prefix}Cleared paths")
        table.add_column("Path")
        for rel in report.deleted_paths:
            table.add_row(rel)
        console.print(table)
    else:
        console.print("No artifact paths to clear (already missing).")
    if not dry_run:
        console.print(
            f"Re-run with: litcurate run-stage {stage} --run-id {run_id} --force"
        )


@app.command("normalize-manifests")
def normalize_manifests_cmd(
    run_id: str = typer.Option(..., "--run-id", help="Existing run ID"),
    runs_dir: Path = typer.Option(None, "--runs-dir"),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Report path changes without rewriting manifest files",
    ),
) -> None:
    """Rewrite absolute paths in run manifest JSON files to run-relative paths."""
    base_runs = runs_dir or project_runs_dir()
    run_dir = run_directory(base_runs, run_id)
    if not run_dir.exists():
        raise typer.BadParameter(f"Unknown run ID: {run_id}")

    if dry_run:
        import json

        results: dict[str, int] = {}
        for manifest_path in list_manifest_json_files(run_dir):
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            copy = json.loads(json.dumps(payload))
            results[manifest_path.name] = rewrite_manifest_paths(run_dir, copy)
        console.print("[dry-run] Manifest path changes:")
    else:
        results = normalize_run_manifests(run_dir)
        console.print("[green]Normalized manifest paths[/green]")

    table = Table(title="Manifest files")
    table.add_column("File")
    table.add_column("Paths updated", justify="right")
    for name, count in sorted(results.items()):
        table.add_row(name, str(count))
    console.print(table)


@app.command("list-runs")
def list_runs(
    runs_dir: Path = typer.Option(None, "--runs-dir"),
    limit: int = typer.Option(10, "--limit"),
) -> None:
    """List recent pipeline runs."""
    base_runs = runs_dir or project_runs_dir()
    if not base_runs.exists():
        console.print("No runs directory yet.")
        raise typer.Exit(0)

    table = Table(title="Recent runs")
    table.add_column("Run ID")
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Created")

    for run_dir in sorted(base_runs.iterdir(), reverse=True)[:limit]:
        if not run_dir.is_dir():
            continue
        store = open_run_store(run_dir)
        run = store.get_run(run_dir.name)
        if run:
            table.add_row(run.id, run.name, run.status, run.created_at)

    console.print(table)


if __name__ == "__main__":
    app()
