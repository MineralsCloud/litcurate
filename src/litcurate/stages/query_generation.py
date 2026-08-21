"""Stage 1: Generate OpenAlex search queries via Claude."""

from __future__ import annotations

import logging

from litcurate.clients.llm import llm_chat, llm_require_configured
from litcurate.config import resolve_stage_llm
from litcurate.llm_json import parse_llm_json_object
from litcurate.query_portfolio import (
    MAX_REGENERATIONS,
    build_portfolio_classification_prompt,
    build_query_generation_prompt,
    build_regeneration_feedback,
    parse_portfolio_classification,
    portfolio_validation_to_dict,
    validate_query_portfolio,
)
from litcurate.stages.base import StageContext, StageResult
from litcurate.stages.utils import write_json

logger = logging.getLogger(__name__)


class QueryGenerationStage:
    name = "query_generation"
    description = "Generate diverse OpenAlex semantic search queries from the user goal"

    def should_skip(self, ctx: StageContext) -> bool:
        output = ctx.artifact("queries.json")
        return output.exists() and ctx.store.is_stage_completed(ctx.run_id, self.name)

    def run(self, ctx: StageContext) -> StageResult:
        output = ctx.artifact("queries.json")
        num_queries = ctx.config.search.num_queries
        user_goal = ctx.config.run.user_goal
        retrieval_objective = ctx.config.search.retrieval_objective

        if ctx.dry_run:
            queries = [
                {
                    "id": f"q{i + 1}",
                    "query": f"{user_goal.strip()[:80]} — query variant {i + 1}",
                    "rationale": "dry_run placeholder",
                }
                for i in range(min(num_queries, 3))
            ]
            write_json(output, {"queries": queries, "dry_run": True})
            return StageResult(artifact_path=output, message=f"Wrote {len(queries)} dry-run queries")

        stage_llm = resolve_stage_llm(ctx.config.llm, ctx.config.search)
        llm_require_configured(stage_llm, stage=self.name)
        model = ctx.config.search.model

        payload, validation_report, regenerated = _generate_validated_queries(
            ctx=ctx,
            model=model,
            stage_llm=stage_llm,
            num_queries=num_queries,
            user_goal=user_goal,
            retrieval_objective=retrieval_objective,
        )

        output_payload = dict(payload)
        output_payload["portfolio_validation"] = validation_report
        output_payload["regenerated"] = regenerated
        write_json(output, output_payload)

        query_count = len(payload.get("queries", []))
        regen_note = " (regenerated once)" if regenerated else ""
        return StageResult(
            artifact_path=output,
            message=f"Generated {query_count} queries{regen_note}",
        )


def _generate_validated_queries(
    *,
    ctx: StageContext,
    model: str,
    stage_llm,
    num_queries: int,
    user_goal: str,
    retrieval_objective: str | None,
) -> tuple[dict, dict, bool]:
    feedback: str | None = None
    regenerated = False
    last_validation: dict = {}
    payload: dict = {"queries": []}

    for attempt in range(MAX_REGENERATIONS + 1):
        prompt = build_query_generation_prompt(
            num_queries=num_queries,
            user_goal=user_goal,
            retrieval_objective=retrieval_objective,
            feedback=feedback,
        )
        response = llm_chat(
            ctx,
            stage_name=QueryGenerationStage.name,
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
            label="generate_queries" if attempt == 0 else "generate_queries_regen",
            llm=stage_llm,
        )
        payload = parse_llm_json_object(response.text)
        queries = payload.get("queries") or []
        if not isinstance(queries, list):
            raise ValueError("Query generation response missing queries list")

        metrics = _classify_query_portfolio(
            ctx=ctx,
            model=model,
            stage_llm=stage_llm,
            queries=queries,
            user_goal=user_goal,
            retrieval_objective=retrieval_objective,
        )
        validation = validate_query_portfolio(
            queries=queries,
            num_queries=num_queries,
            metrics=metrics,
        )
        last_validation = portfolio_validation_to_dict(validation)

        if validation.valid:
            return payload, last_validation, regenerated

        if attempt >= MAX_REGENERATIONS:
            error_summary = "; ".join(validation.errors)
            raise ValueError(f"Query generation failed validation: {error_summary}")

        logger.warning(
            "query_generation portfolio validation failed (attempt %d); regenerating: %s",
            attempt + 1,
            validation.errors,
        )
        feedback = build_regeneration_feedback(validation)
        regenerated = True

    return payload, last_validation, regenerated


def _classify_query_portfolio(
    *,
    ctx: StageContext,
    model: str,
    stage_llm,
    queries: list[dict],
    user_goal: str,
    retrieval_objective: str | None,
):
    prompt = build_portfolio_classification_prompt(
        queries=queries,
        user_goal=user_goal,
        retrieval_objective=retrieval_objective,
    )
    response = llm_chat(
        ctx,
        stage_name=QueryGenerationStage.name,
        model=model,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
        label="classify_queries",
        llm=stage_llm,
    )
    classification = parse_llm_json_object(response.text)
    return parse_portfolio_classification(classification)
