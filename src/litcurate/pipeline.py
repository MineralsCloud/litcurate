"""Pipeline orchestration with checkpoint/resume."""

from __future__ import annotations

import logging
from pathlib import Path

from litcurate.config import load_config, snapshot_config
from litcurate.constants import STAGE_ORDER, RunStatus
from litcurate.paths import artifacts_directory, logs_directory, project_runs_dir, run_directory
from litcurate.run_store import RunStore, open_run_store
from litcurate.stage_info import STAGE_PREREQUISITES
from litcurate.stages.base import StageContext
from litcurate.stages.registry import get_stage
from litcurate.stages.utils import write_json

logger = logging.getLogger(__name__)


class PipelineRunner:
    def __init__(
        self,
        config_path: Path,
        *,
        runs_dir: Path | None = None,
        run_id: str | None = None,
        from_stage: str | None = None,
        until_stage: str | None = None,
        force: bool = False,
    ) -> None:
        self.config_path = Path(config_path).resolve()
        self.config = load_config(self.config_path)
        self.runs_dir = runs_dir or project_runs_dir()
        self.run_id = run_id
        self.from_stage = from_stage
        self.until_stage = until_stage
        self.force = force

    def start_new_run(self) -> str:
        run_id = self._init_run()
        store = open_run_store(run_directory(self.runs_dir, run_id))
        self._execute_run(store, run_directory(self.runs_dir, run_id))
        return run_id

    def init_run(self) -> str:
        """Create a run directory and ledger without executing stages."""
        return self._init_run()

    def resume_run(self, run_id: str) -> None:
        self.run_id = run_id
        run_dir = run_directory(self.runs_dir, run_id)
        if not run_dir.exists():
            raise FileNotFoundError(f"Run directory not found: {run_dir}")

        snapshot_path = run_dir / "config.snapshot.yaml"
        if snapshot_path.exists() and self.config_path.resolve() == snapshot_path.resolve():
            self.config = load_config(snapshot_path)
        elif not snapshot_path.exists():
            self.config = load_config(self.config_path)

        store = open_run_store(run_dir)
        self._execute_run(store, run_dir)

    def run_stage(self, stage_name: str, *, run_id: str | None = None) -> str:
        """Run a single stage for modular testing."""
        if stage_name not in STAGE_ORDER:
            raise ValueError(f"Unknown stage: {stage_name}")

        if run_id is None:
            run_id = self._init_run()
        else:
            self.run_id = run_id
            run_dir = run_directory(self.runs_dir, run_id)
            snapshot_path = run_dir / "config.snapshot.yaml"
            if snapshot_path.exists() and self.config_path.resolve() == snapshot_path.resolve():
                self.config = load_config(snapshot_path)

        run_dir = run_directory(self.runs_dir, run_id)
        store = open_run_store(run_dir)
        ctx = self._build_context(store, run_dir)

        self._validate_prerequisites(stage_name, ctx)
        if self.force:
            store.reset_stage(run_id, stage_name)

        store.update_run_status(run_id, RunStatus.RUNNING)
        self._run_stage(store, ctx, stage_name)
        store.update_run_status(run_id, RunStatus.RUNNING)
        return run_id

    def _init_run(self) -> str:
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        run_id = self._next_run_id()
        run_dir = run_directory(self.runs_dir, run_id)
        run_dir.mkdir(parents=True)
        artifacts_directory(run_dir).mkdir()
        logs_directory(run_dir).mkdir()

        snapshot_path = run_dir / "config.snapshot.yaml"
        snapshot_config(self.config, snapshot_path)

        store = open_run_store(run_dir)
        store.create_run(
            config_path=self.config_path,
            config_snapshot_path=snapshot_path,
            name=self.config.run.name,
            run_dir=run_dir,
            run_id=run_id,
        )
        self.run_id = run_id
        return run_id

    def _next_run_id(self) -> str:
        import uuid

        return uuid.uuid4().hex[:12]

    def _build_context(self, store: RunStore, run_dir: Path) -> StageContext:
        return StageContext(
            run_id=self.run_id,
            run_dir=run_dir,
            artifacts_dir=artifacts_directory(run_dir),
            config=self.config,
            store=store,
            dry_run=self.config.dry_run,
            force=self.force,
        )

    def _execute_run(self, store: RunStore, run_dir: Path) -> None:
        store.update_run_status(self.run_id, RunStatus.RUNNING)
        ctx = self._build_context(store, run_dir)

        start_index = 0
        if self.from_stage:
            if self.from_stage not in STAGE_ORDER:
                raise ValueError(f"Unknown stage: {self.from_stage}")
            start_index = STAGE_ORDER.index(self.from_stage)
            if self.force:
                self._reset_stages_from(store, self.from_stage)

        end_index = len(STAGE_ORDER)
        if self.until_stage:
            if self.until_stage not in STAGE_ORDER:
                raise ValueError(f"Unknown stage: {self.until_stage}")
            end_index = STAGE_ORDER.index(self.until_stage) + 1

        failed = False
        for stage_name in STAGE_ORDER[start_index:end_index]:
            stage = get_stage(stage_name)
            if stage.should_skip(ctx) and not self._force_rerun_stage(stage_name):
                logger.info("Skipping completed stage: %s", stage_name)
                continue

            try:
                self._run_stage(store, ctx, stage_name)
            except Exception:
                failed = True
                store.update_run_status(self.run_id, RunStatus.FAILED)
                raise

        final_status = RunStatus.FAILED if failed else RunStatus.COMPLETED
        store.update_run_status(self.run_id, final_status)

    def _run_stage(self, store: RunStore, ctx: StageContext, stage_name: str) -> None:
        stage = get_stage(stage_name)
        logger.info("Running stage: %s", stage_name)
        store.start_stage(ctx.run_id, stage_name)
        try:
            result = stage.run(ctx)
            store.complete_stage(
                ctx.run_id,
                stage_name,
                artifact_path=result.artifact_path,
            )
            self._write_api_costs_artifact(store, ctx)
            logger.info(
                "Completed stage %s%s",
                stage_name,
                f" — {result.message}" if result.message else "",
            )
        except Exception as exc:
            store.fail_stage(ctx.run_id, stage_name, str(exc))
            logger.exception("Stage %s failed", stage_name)
            raise

    def _write_api_costs_artifact(self, store: RunStore, ctx: StageContext) -> None:
        summary = store.get_api_cost_summary(ctx.run_id)
        if summary["call_count"] == 0:
            return
        write_json(ctx.artifact("api_costs.json"), summary)

    def _force_rerun_stage(self, stage_name: str) -> bool:
        if self.force and self.from_stage:
            return STAGE_ORDER.index(stage_name) >= STAGE_ORDER.index(self.from_stage)
        return self.force

    def _reset_stages_from(self, store: RunStore, from_stage: str) -> None:
        start = STAGE_ORDER.index(from_stage)
        for stage_name in STAGE_ORDER[start:]:
            store.reset_stage(self.run_id, stage_name)

    def _validate_prerequisites(self, stage_name: str, ctx: StageContext) -> None:
        missing: list[str] = []
        for rel_path in STAGE_PREREQUISITES.get(stage_name, []):
            path = ctx.run_dir / rel_path
            if not path.exists():
                missing.append(rel_path)
                continue
            if path.is_dir() and not any(path.glob("*")):
                missing.append(f"{rel_path} (empty)")

        if stage_name == "merge_rank" and not missing:
            openalex = ctx.artifact("openalex_raw")
            consensus = ctx.artifact("consensus_raw")
            if not (
                (openalex.exists() and any(openalex.glob("*.json")))
                or (consensus.exists() and any(consensus.glob("*.json")))
            ):
                missing.append("artifacts/openalex_raw/ or artifacts/consensus_raw/")

        if missing:
            prior = STAGE_ORDER[STAGE_ORDER.index(stage_name) - 1] if stage_name in STAGE_ORDER else None
            hint = f" Run prior stage first: litcurate run-stage {prior} --run-id {ctx.run_id}"
            if prior is None:
                hint = ""
            raise FileNotFoundError(
                f"Stage '{stage_name}' missing prerequisites: {', '.join(missing)}.{hint}"
            )


def prepare_run_from_config(config_path: Path, *, runs_dir: Path | None = None) -> PipelineRunner:
    return PipelineRunner(config_path, runs_dir=runs_dir)
