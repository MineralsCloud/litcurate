"""Export: merge extraction envelopes into a single database.json for ingest."""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from litcurate.extraction_envelope import is_envelope, unwrap_payload
from litcurate.stages.base import StageContext, StageResult
from litcurate.stages.utils import read_json, write_json

logger = logging.getLogger(__name__)

OUTPUT_NAME = "database.json"


class ExportStage:
    name = "export"
    description = "Merge extraction envelopes into database.json for downstream ingest"

    def should_skip(self, ctx: StageContext) -> bool:
        output = ctx.artifact("output", OUTPUT_NAME)
        return output.exists() and ctx.store.is_stage_completed(ctx.run_id, self.name)

    def run(self, ctx: StageContext) -> StageResult:
        extract_manifest = ctx.artifact("extract_manifest.json")
        if not extract_manifest.exists():
            raise FileNotFoundError("extract_manifest.json not found")

        payload = read_json(extract_manifest)
        schema_refs = list(ctx.config.extraction.schemas)
        schema_names = [ref.name for ref in schema_refs]
        empty_list_fields = {
            ref.name: ref.empty_list_field for ref in schema_refs if ref.empty_list_field
        }

        papers: list[dict[str, Any]] = []
        schema_present: Counter[str] = Counter()
        missing_by_schema: dict[str, list[str]] = {name: [] for name in schema_names}
        n_list_entries = 0
        n_papers_with_list_entries = 0
        list_entries_by_schema: Counter[str] = Counter()

        extractions = [
            item for item in payload.get("extractions", []) if item.get("status") == "success"
        ]
        logger.info("export starting: %d successful extractions", len(extractions))

        for item in extractions:
            paper_id = item["paper_id"]
            paper_dir = ctx.artifact("extractions", paper_id)
            record: dict[str, Any] = {"paper_id": paper_id}

            loaded = _load_paper_schemas(paper_dir)
            for schema_name in schema_names:
                envelope = loaded.get(schema_name)
                record[schema_name] = envelope
                if envelope is None:
                    missing_by_schema[schema_name].append(paper_id)
                else:
                    schema_present[schema_name] += 1

            # Include any unexpected schema files under the paper folder.
            for extra_name, envelope in loaded.items():
                if extra_name not in record:
                    record[extra_name] = envelope
                    schema_present[extra_name] += 1

            paper_list_total = 0
            for schema_name, list_field in empty_list_fields.items():
                envelope = record.get(schema_name)
                if envelope is None:
                    continue
                n_entries = _entry_count(envelope, list_field)
                list_entries_by_schema[schema_name] += n_entries
                paper_list_total += n_entries
            n_list_entries += paper_list_total
            if paper_list_total > 0:
                n_papers_with_list_entries += 1

            papers.append(record)

        papers.sort(key=lambda row: row["paper_id"])

        database = {
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "run_id": ctx.run_id,
            "description": (
                "Merged extraction envelopes from extract_schema for database ingest. "
                "Each paper includes configured schemas (full envelopes when present)."
            ),
            "schemas": schema_names,
            "stats": {
                "n_papers": len(papers),
                "n_papers_with_list_entries": n_papers_with_list_entries,
                "n_list_entries": n_list_entries,
                "list_entries_by_schema": dict(list_entries_by_schema),
                "by_schema": dict(schema_present),
                "missing_schemas": {
                    name: ids for name, ids in missing_by_schema.items() if ids
                },
            },
            "papers": papers,
        }

        output_dir = ctx.artifact("output")
        output_dir.mkdir(parents=True, exist_ok=True)
        database_path = output_dir / OUTPUT_NAME
        write_json(database_path, database)

        summary_path = output_dir / "export_summary.json"
        write_json(
            summary_path,
            {
                "papers_exported": len(papers),
                "n_list_entries": n_list_entries,
                "database": ctx.store_path(database_path),
            },
        )

        logger.info(
            "export finished: papers=%d list_entries=%d -> %s",
            len(papers),
            n_list_entries,
            database_path,
        )
        return StageResult(
            artifact_path=database_path,
            message=(
                f"Exported {len(papers)} papers "
                f"({n_list_entries} list entries) to {OUTPUT_NAME}"
            ),
            papers_touched=len(papers),
        )


def _load_paper_schemas(paper_dir: Path) -> dict[str, dict[str, Any]]:
    if not paper_dir.is_dir():
        return {}
    loaded: dict[str, dict[str, Any]] = {}
    for path in sorted(paper_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("export: skip unreadable %s (%s)", path, exc)
            continue
        if not isinstance(data, dict):
            logger.warning("export: skip non-object JSON %s", path)
            continue
        schema_name = data.get("schema_name") if is_envelope(data) else path.stem
        if not isinstance(schema_name, str) or not schema_name:
            schema_name = path.stem
        loaded[schema_name] = data
    return loaded


def _entry_count(envelope: dict[str, Any], list_field: str) -> int:
    payload = unwrap_payload(envelope)
    entries = payload.get(list_field)
    return len(entries) if isinstance(entries, list) else 0
