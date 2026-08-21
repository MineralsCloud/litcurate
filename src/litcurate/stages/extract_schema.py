"""Stage 9: Extract structured data from markdown into config schemas."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from litcurate.clients.llm import llm_chat, llm_require_configured
from litcurate.config import ExtractionSchemaRef, resolve_stage_llm
from litcurate.constants import PaperStageStatus
from litcurate.extraction_envelope import (
    ValidationResult,
    build_extraction_envelope,
    envelope_to_dict,
    unwrap_payload,
)
from litcurate.extraction_text import markdown_path_for_extraction, prepare_extraction_markdown
from litcurate.gate_papers import paper_passes_gates
from litcurate.llm_json import parse_llm_json_object
from litcurate.schema_samples import dry_run_sample_from_schema, is_empty_list_field
from litcurate.schema_spec import LoadedSchemaSpec, load_schema_spec
from litcurate.source_from_meta import load_papers_meta_index, source_payload_from_paper_meta
from litcurate.stages.base import StageContext, StageResult
from litcurate.stages.utils import read_json, write_json

logger = logging.getLogger(__name__)

FAILURE_DIR_NAME = "extraction_failures"
PROMPT_DEBUG_DIR_NAME = "extract_prompt_debug"
RAW_RESPONSE_PREVIEW_CHARS = 4_000
EXTRACT_MAX_TOKENS = 16_384
# Dump the extraction prompt when the model reports unexpectedly small context.
LOW_INPUT_TOKEN_THRESHOLD = 2_000


class ExtractionParseError(ValueError):
    """Raised when the LLM response cannot be parsed as JSON."""

    def __init__(self, message: str, *, raw_response: str) -> None:
        super().__init__(message)
        self.raw_response = raw_response


@dataclass(frozen=True)
class _LLMExtractionResult:
    envelope: object
    raw_response: str


class ExtractSchemaStage:
    name = "extract_schema"
    description = "LLM extraction of schema-shaped JSON from markdown"

    def should_skip(self, ctx: StageContext) -> bool:
        manifest = ctx.artifact("extract_manifest.json")
        return manifest.exists() and ctx.store.is_stage_completed(ctx.run_id, self.name)

    def run(self, ctx: StageContext) -> StageResult:
        clean_manifest = ctx.artifact("clean_manifest.json")
        if not clean_manifest.exists():
            raise FileNotFoundError("clean_manifest.json not found")
        if not ctx.artifact("fulltext_filter_manifest.json").exists():
            raise FileNotFoundError("fulltext_filter_manifest.json not found — run filter_fulltext first")

        payload = read_json(clean_manifest)
        extract_root = ctx.artifact("extractions")
        extract_root.mkdir(parents=True, exist_ok=True)
        failure_root = ctx.artifact(FAILURE_DIR_NAME)
        failure_root.mkdir(parents=True, exist_ok=True)
        manifest_path = ctx.artifact("extract_manifest.json")
        schemas = ctx.config.extraction.schemas
        manifest: list[dict] = []
        success = 0
        skipped = 0
        failed = 0
        papers_meta = load_papers_meta_index(ctx)

        eligible = [
            item
            for item in payload.get("cleaned", [])
            if item.get("status") == "success"
        ]
        total = len(eligible)
        logger.info("extract_schema starting: %d cleaned papers", total)

        for index, item in enumerate(eligible, start=1):
            paper_id = item["paper_id"]
            passes, gate_reason = paper_passes_gates(ctx, paper_id)
            if not passes:
                logger.info(
                    "extract_schema [%d/%d] %s skipped by gates: %s",
                    index,
                    total,
                    paper_id,
                    gate_reason,
                )
                manifest.append(
                    {
                        "paper_id": paper_id,
                        "status": "skipped",
                        "reason": gate_reason,
                        "schemas": [],
                    }
                )
                ctx.store.update_paper_stage(
                    ctx.run_id, paper_id, "extract_status", PaperStageStatus.SKIPPED
                )
                skipped += 1
                _flush_extract_manifest(manifest_path, manifest)
                continue

            md_path = markdown_path_for_extraction(
                ctx,
                paper_id,
                clean_manifest_path=item.get("path"),
            )
            paper_dir = extract_root / paper_id
            paper_dir.mkdir(parents=True, exist_ok=True)

            ctx.store.update_paper_stage(
                ctx.run_id, paper_id, "extract_status", PaperStageStatus.RUNNING
            )
            logger.info("extract_schema [%d/%d] %s started", index, total, paper_id)

            try:
                if not md_path.exists():
                    raise FileNotFoundError(
                        f"markdown for extraction not found "
                        f"({ctx.config.extraction.section_mode}): {md_path}"
                    )
                markdown = md_path.read_text(encoding="utf-8")
                schema_results = []
                prior_outputs: dict[str, dict] = {}

                for schema_ref in schemas:
                    if _should_skip_schema(schema_ref, prior_outputs, schemas):
                        reason = f"prior schema {schema_ref.skip_when_prior_empty} empty"
                        logger.info(
                            "extract_schema %s schema %s skipped: %s",
                            paper_id,
                            schema_ref.name,
                            reason,
                        )
                        schema_results.append(
                            {
                                "schema": schema_ref.name,
                                "status": "skipped",
                                "reason": reason,
                            }
                        )
                        continue

                    out_path = paper_dir / f"{schema_ref.name}.json"
                    if out_path.exists() and out_path.stat().st_size > 0:
                        cached = json.loads(out_path.read_text(encoding="utf-8"))
                        prior_outputs[schema_ref.name] = unwrap_payload(cached)
                        logger.info(
                            "extract_schema %s schema %s using cached file",
                            paper_id,
                            schema_ref.name,
                        )
                        schema_results.append(
                            _manifest_entry_from_cached(schema_ref, cached, ctx, out_path)
                        )
                        continue

                    spec = load_schema_spec(schema_ref)
                    model = schema_ref.model or ctx.config.extraction.model

                    if schema_ref.fill_from:
                        envelope = _extract_from_fill_source(
                            ctx=ctx,
                            schema_ref=schema_ref,
                            spec=spec,
                            paper_id=paper_id,
                            papers_meta=papers_meta,
                            out_path=out_path,
                        )
                        prior_outputs[schema_ref.name] = envelope.payload
                        schema_results.append(
                            _manifest_entry_from_envelope(envelope, ctx, out_path)
                        )
                        logger.info(
                            "extract_schema %s schema %s filled from %s → %s",
                            paper_id,
                            schema_ref.name,
                            schema_ref.fill_from,
                            out_path.name,
                        )
                        continue

                    logger.info(
                        "extract_schema %s schema %s calling LLM model=%s",
                        paper_id,
                        schema_ref.name,
                        model,
                    )

                    if ctx.dry_run:
                        sample = dry_run_sample_from_schema(spec.json_schema)
                        envelope = build_extraction_envelope(
                            schema_name=schema_ref.name,
                            schema_version=spec.version,
                            schema_format=spec.format.value,
                            paper_id=paper_id,
                            model="dry_run",
                            payload=sample,
                            validation=ValidationResult(valid=True),
                        )
                        write_json(out_path, envelope_to_dict(envelope))
                        prior_outputs[schema_ref.name] = envelope.payload
                        schema_results.append(
                            _manifest_entry_from_envelope(envelope, ctx, out_path)
                        )
                        continue

                    result = _extract_with_llm(
                        ctx=ctx,
                        markdown=markdown,
                        spec=spec,
                        schema_ref=schema_ref,
                        model=model,
                        paper_id=paper_id,
                    )
                    envelope = result.envelope
                    if not envelope.validation.valid:
                        error = (
                            f"Extraction for {schema_ref.name} failed validation: "
                            + "; ".join(envelope.validation.errors)
                        )
                        failure_path = _write_failure_record(
                            failure_root,
                            paper_id=paper_id,
                            schema_name=schema_ref.name,
                            error=error,
                            raw_response=result.raw_response,
                            payload=envelope.payload,
                            validation_errors=envelope.validation.errors,
                        )
                        logger.error(
                            "extract_schema %s schema %s validation failed; "
                            "wrote debug artifact %s; errors=%s",
                            paper_id,
                            schema_ref.name,
                            failure_path,
                            envelope.validation.errors[:5],
                        )
                        raise ValueError(error)

                    write_json(out_path, envelope_to_dict(envelope))
                    prior_outputs[schema_ref.name] = envelope.payload
                    schema_results.append(
                        _manifest_entry_from_envelope(envelope, ctx, out_path)
                    )
                    entry_count = _payload_entry_count(envelope.payload, schema_ref)
                    logger.info(
                        "extract_schema %s schema %s wrote %s (%s entries)",
                        paper_id,
                        schema_ref.name,
                        out_path.name,
                        entry_count,
                    )

                manifest.append(
                    {"paper_id": paper_id, "status": "success", "schemas": schema_results}
                )
                ctx.store.update_paper_stage(
                    ctx.run_id, paper_id, "extract_status", PaperStageStatus.SUCCESS
                )
                success += 1
                logger.info("extract_schema [%d/%d] %s completed", index, total, paper_id)
            except ExtractionParseError as exc:
                failure_path = _write_failure_record(
                    failure_root,
                    paper_id=paper_id,
                    schema_name=schema_ref.name,
                    error=str(exc),
                    raw_response=exc.raw_response,
                )
                logger.error(
                    "extract_schema [%d/%d] %s schema %s JSON parse failed; "
                    "debug artifact %s",
                    index,
                    total,
                    paper_id,
                    schema_ref.name,
                    failure_path,
                )
                manifest.append(
                    {
                        "paper_id": paper_id,
                        "status": "failed",
                        "error": str(exc),
                        "failure_artifact": str(failure_path.relative_to(ctx.run_dir)),
                    }
                )
                ctx.store.update_paper_stage(
                    ctx.run_id,
                    paper_id,
                    "extract_status",
                    PaperStageStatus.FAILED,
                    error=str(exc),
                )
                failed += 1
            except Exception as exc:
                failure_path = _write_failure_record(
                    failure_root,
                    paper_id=paper_id,
                    schema_name="paper",
                    error=str(exc),
                )
                logger.exception(
                    "extract_schema [%d/%d] %s failed; debug artifact %s",
                    index,
                    total,
                    paper_id,
                    failure_path,
                )
                manifest.append(
                    {
                        "paper_id": paper_id,
                        "status": "failed",
                        "error": str(exc),
                        "failure_artifact": str(failure_path.relative_to(ctx.run_dir)),
                    }
                )
                ctx.store.update_paper_stage(
                    ctx.run_id,
                    paper_id,
                    "extract_status",
                    PaperStageStatus.FAILED,
                    error=str(exc),
                )
                failed += 1

            _flush_extract_manifest(manifest_path, manifest)

        # Always create the manifest, including when no cleaned papers are eligible.
        # Downstream export treats an empty extraction list as a valid empty result.
        _flush_extract_manifest(manifest_path, manifest)

        logger.info(
            "extract_schema finished: success=%d failed=%d skipped=%d",
            success,
            failed,
            skipped,
        )
        suffix = f", {skipped} skipped by gates" if skipped else ""
        if failed:
            suffix += f", {failed} failed (see artifacts/{FAILURE_DIR_NAME}/)"
        return StageResult(
            artifact_path=manifest_path,
            message=f"Extracted schemas for {success} papers{suffix}",
            papers_touched=success,
        )


def _flush_extract_manifest(manifest_path: Path, manifest: list[dict]) -> None:
    write_json(manifest_path, {"extractions": manifest})


def _payload_entry_count(payload: dict, schema_ref: ExtractionSchemaRef) -> str:
    if schema_ref.empty_list_field and isinstance(payload.get(schema_ref.empty_list_field), list):
        return str(len(payload[schema_ref.empty_list_field]))
    return "n/a"


def _write_failure_record(
    failure_root: Path,
    *,
    paper_id: str,
    schema_name: str,
    error: str,
    raw_response: str | None = None,
    payload: dict | None = None,
    validation_errors: list[str] | None = None,
) -> Path:
    paper_dir = failure_root / paper_id
    paper_dir.mkdir(parents=True, exist_ok=True)
    out_path = paper_dir / f"{schema_name}.json"
    record = {
        "paper_id": paper_id,
        "schema": schema_name,
        "error": error,
        "validation_errors": validation_errors or [],
        "payload": payload,
        "raw_response_preview": (raw_response or "")[:RAW_RESPONSE_PREVIEW_CHARS],
        "raw_response_chars": len(raw_response or ""),
    }
    write_json(out_path, record)
    return out_path


def _manifest_entry_from_envelope(envelope, ctx: StageContext, out_path: Path) -> dict:
    return {
        "schema": envelope.schema_name,
        "path": ctx.store_path(out_path),
        "schema_version": envelope.schema_version,
        "validation": envelope.validation.model_dump(),
    }


def _manifest_entry_from_cached(
    schema_ref: ExtractionSchemaRef,
    cached: dict,
    ctx: StageContext,
    out_path: Path,
) -> dict:
    entry = {
        "schema": schema_ref.name,
        "path": ctx.store_path(out_path),
        "cached": True,
    }
    if "schema_version" in cached:
        entry["schema_version"] = cached["schema_version"]
    if "validation" in cached:
        entry["validation"] = cached["validation"]
    return entry


def _should_skip_schema(
    schema_ref: ExtractionSchemaRef,
    prior_outputs: dict[str, dict],
    schemas: list[ExtractionSchemaRef],
) -> bool:
    if not schema_ref.skip_when_prior_empty:
        return False
    prior_name = schema_ref.skip_when_prior_empty
    prior_schema = next((s for s in schemas if s.name == prior_name), None)
    if prior_schema is None:
        return False
    prior_payload = prior_outputs.get(prior_name)
    if prior_payload is None:
        return False
    return is_empty_list_field(prior_payload, prior_schema.empty_list_field)


def _extract_from_fill_source(
    *,
    ctx: StageContext,
    schema_ref: ExtractionSchemaRef,
    spec: LoadedSchemaSpec,
    paper_id: str,
    papers_meta: dict[str, dict],
    out_path: Path,
):
    if schema_ref.fill_from != "papers_meta":
        raise ValueError(
            f"Unsupported fill_from={schema_ref.fill_from!r} for schema {schema_ref.name}"
        )
    meta = papers_meta.get(paper_id)
    if not meta:
        raise ValueError(
            f"No papers_meta row for {paper_id}; "
            "expected papers_filtered/enriched/ranked.parquet"
        )
    payload = source_payload_from_paper_meta(meta)
    validation = spec.validate_payload(payload)
    if not validation.valid:
        raise ValueError(
            f"papers_meta fill for {schema_ref.name} failed validation: "
            + "; ".join(validation.errors)
        )
    envelope = build_extraction_envelope(
        schema_name=schema_ref.name,
        schema_version=spec.version,
        schema_format=spec.format.value,
        paper_id=paper_id,
        model="papers_meta",
        payload=payload,
        validation=validation,
    )
    write_json(out_path, envelope_to_dict(envelope))
    return envelope


def _extract_with_llm(
    *,
    ctx: StageContext,
    markdown: str,
    spec: LoadedSchemaSpec,
    schema_ref: ExtractionSchemaRef,
    model: str,
    paper_id: str,
) -> _LLMExtractionResult:
    stage_llm = resolve_stage_llm(ctx.config.llm, ctx.config.extraction)
    llm_require_configured(stage_llm, stage=ExtractSchemaStage.name)

    if not schema_ref.prompt:
        raise ValueError(f"schema {schema_ref.name} requires prompt for LLM extraction")
    prompt_template = Path(schema_ref.prompt).read_text(encoding="utf-8")
    extraction_text = prepare_extraction_markdown(
        markdown,
        extraction_cfg=ctx.config.extraction,
        schema_ref=schema_ref,
    )
    user_prompt = (
        f"{prompt_template.strip()}\n\n"
        f"JSON Schema:\n{json.dumps(spec.json_schema, indent=2)}\n\n"
        f"Markdown:\n{extraction_text}\n\n"
        "Return valid JSON only matching the schema."
    )

    response = llm_chat(
        ctx,
        stage_name=ExtractSchemaStage.name,
        model=model,
        max_tokens=EXTRACT_MAX_TOKENS,
        messages=[{"role": "user", "content": user_prompt}],
        label=f"{paper_id}:{schema_ref.name}",
        llm=stage_llm,
    )
    if (
        isinstance(response.input_tokens, int)
        and response.input_tokens < LOW_INPUT_TOKEN_THRESHOLD
    ):
        _dump_low_input_prompt(
            ctx,
            paper_id=paper_id,
            schema_name=schema_ref.name,
            input_tokens=response.input_tokens,
            raw_markdown_chars=len(markdown),
            prepared_markdown_chars=len(extraction_text),
            user_prompt=user_prompt,
        )

    raw_response = response.text
    try:
        payload = parse_llm_json_object(raw_response)
    except ValueError as exc:
        logger.error(
            "extract_schema %s schema %s JSON parse failed: %s",
            paper_id,
            schema_ref.name,
            exc,
        )
        raise ExtractionParseError(
            f"Extraction for {schema_ref.name} JSON parse failed: {exc}",
            raw_response=raw_response,
        ) from exc

    validation = spec.validate_payload(payload)
    envelope = build_extraction_envelope(
        schema_name=schema_ref.name,
        schema_version=spec.version,
        schema_format=spec.format.value,
        paper_id=paper_id,
        model=model,
        payload=payload,
        validation=validation,
    )
    return _LLMExtractionResult(envelope=envelope, raw_response=raw_response)


def _dump_low_input_prompt(
    ctx: StageContext,
    *,
    paper_id: str,
    schema_name: str,
    input_tokens: int,
    raw_markdown_chars: int,
    prepared_markdown_chars: int,
    user_prompt: str,
) -> Path:
    """Write the full extraction prompt when API-reported input tokens are suspiciously low."""
    debug_root = ctx.artifact(PROMPT_DEBUG_DIR_NAME)
    debug_root.mkdir(parents=True, exist_ok=True)
    out_path = debug_root / f"{paper_id}_{schema_name}_prompt.txt"
    header = (
        f"paper_id={paper_id}\n"
        f"schema={schema_name}\n"
        f"input_tokens={input_tokens}\n"
        f"raw_markdown_chars={raw_markdown_chars}\n"
        f"prepared_markdown_chars={prepared_markdown_chars}\n"
        f"user_prompt_chars={len(user_prompt)}\n"
        f"{'=' * 72}\n"
    )
    out_path.write_text(header + user_prompt, encoding="utf-8")
    logger.warning(
        "extract_schema %s schema %s low input_tokens=%s "
        "(raw_md=%s prepared_md=%s prompt_chars=%s); dumped prompt to %s",
        paper_id,
        schema_name,
        input_tokens,
        raw_markdown_chars,
        prepared_markdown_chars,
        len(user_prompt),
        out_path.relative_to(ctx.run_dir),
    )
    return out_path
