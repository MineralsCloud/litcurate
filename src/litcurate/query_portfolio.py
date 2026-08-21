"""High-recall OpenAlex query portfolio generation and validation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

QueryCategory = Literal["targeted_producer", "broad_recall", "downstream_consumer"]

TARGETED_FRACTION_MIN = 0.65
TARGETED_FRACTION_MAX = 0.75
BROAD_FRACTION_MIN = 0.25
BROAD_FRACTION_MAX = 0.35

# Regenerate when substantially outside the intended mix (wider tolerance band).
TARGETED_REGEN_MIN = 0.55
TARGETED_REGEN_MAX = 0.85
BROAD_REGEN_MIN = 0.15
BROAD_REGEN_MAX = 0.45

MAX_CONSUMER_FRACTION = 0.15
MAX_CONSUMER_COUNT = 2

MAX_QUERY_CHARS = 220
MAX_QUERY_WORDS = 28
MAX_REGENERATIONS = 1

_BOOLEAN_PATTERN = re.compile(
    r"\b(AND|OR|NOT)\b|"
    r"[+]|"
    r"\([^)]*\b(AND|OR|NOT)\b[^)]*\)|"
    r'"[^"]+"\s*(AND|OR)\s*"[^"]+"',
    re.IGNORECASE,
)


@dataclass(frozen=True)
class StructuralValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PortfolioMetrics:
    targeted_producer: int = 0
    broad_recall: int = 0
    downstream_consumer: int = 0
    classifications: list[dict[str, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.targeted_producer + self.broad_recall + self.downstream_consumer


@dataclass(frozen=True)
class PortfolioValidationResult:
    valid: bool
    structural: StructuralValidationResult
    metrics: PortfolioMetrics | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def build_query_generation_prompt(
    *,
    num_queries: int,
    user_goal: str,
    retrieval_objective: str | None,
    feedback: str | None = None,
) -> str:
    """Build the LLM prompt for OpenAlex semantic query generation."""
    targeted_min = int(round(num_queries * TARGETED_FRACTION_MIN))
    targeted_max = int(round(num_queries * TARGETED_FRACTION_MAX))
    broad_min = num_queries - targeted_max
    broad_max = num_queries - targeted_min

    lines = [
        f"Generate exactly {num_queries} diverse academic search queries for OpenAlex "
        "semantic search.",
        "",
        "Research goal (scientific scope):",
        user_goal.strip(),
    ]

    if retrieval_objective and retrieval_objective.strip():
        lines.extend(
            [
                "",
                "Retrieval objective (optimize queries for this):",
                retrieval_objective.strip(),
                "",
                "Use the research goal and retrieval objective together to infer:",
                "1. the target record type to retrieve,",
                "2. producer signals (terminology indicating a study reports or derives new "
                "target records),",
                "3. broad-recall terminology (still on-topic when producer signals are absent "
                "from titles or abstracts),",
                "4. downstream-consumer topics to avoid or use sparingly.",
                "",
                "Definitions:",
                "- A producer study reports, measures, calculates, fits, or derives a new target "
                "record, dataset, or parameterization within the retrieval objective.",
                "- A consumer study adopts or applies previously published parameters or models "
                "for aggregate, compositional, geophysical, or downstream modeling.",
                "",
                "Query portfolio (high recall within the target record type):",
                f"- Approximately {targeted_min}-{targeted_max} queries ({int(TARGETED_FRACTION_MIN * 100)}"
                f"-{int(TARGETED_FRACTION_MAX * 100)}%): targeted producer queries with explicit "
                "producer signals inferred from the retrieval objective (parameter names, model "
                "names, dataset types, measurement or fitting language mentioned there).",
                f"- Approximately {broad_min}-{broad_max} queries ({int(BROAD_FRACTION_MIN * 100)}"
                f"-{int(BROAD_FRACTION_MAX * 100)}%): broader high-recall queries that vary "
                "phase, composition, method, temperature or pressure regime, and structural or "
                "thermoelastic wording so relevant producer papers are still retrieved when "
                "producer terminology is missing from the title or abstract.",
                "",
                "Targeted producer queries should name concrete producer signals drawn from the "
                "retrieval objective. Broad-recall queries should stay centered on papers that "
                "may still contain extractable target records for this database.",
                "",
                "High recall must not mean unrestricted topical diversity. Avoid queries "
                "primarily centered on downstream consumers of the target data, such as:",
                "- fitting or interpreting aggregate reference models,",
                "- assemblage, geodynamic, or forward modeling that mainly applies published "
                "parameters,",
                "- partitioning or phase-equilibrium studies without new target-record production,",
                "- phase-boundary interpretation without new target-record production,",
                "- experimental apparatus, pressure calibration, or instrument development,",
                "- sound velocity or full elastic-tensor studies when the retrieval objective "
                "concerns a different record type,",
                "unless the query also contains a plausible producer signal or the topic is known "
                "to commonly include new target-record results for this objective.",
                "",
                "Prefer producer studies. Broad-recall queries do not need explicit producer "
                "terminology in every query string.",
                "",
                "Diversity must remain within the target record type. Vary:",
                "- material, phase, or composition (as appropriate to the goal),",
                "- static versus thermal formulations when relevant,",
                "- experimental versus theoretical methods,",
                "- producer terminology and model names from the retrieval objective,",
                "- pressure and temperature conditions.",
                "Do not create diversity by drifting into adjacent topics unlikely to yield "
                "extractable target records.",
                "",
                "Each query must be a short natural-language phrase suitable for semantic search. "
                "Do not use Boolean syntax (AND, OR, NOT, quotes for logic, parentheses, +).",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "Base queries on the research goal. Use a mixed portfolio favoring explicit "
                "target-record producer signals while keeping some broader high-recall queries "
                "within the same record type.",
            ]
        )

    lines.extend(
        [
            "",
            'Return JSON only: {"queries": [{"id": "q1", "query": "...", "rationale": "..."}]}',
            "Use unique ids q1..qN and unique query strings.",
        ]
    )

    if feedback and feedback.strip():
        lines.extend(["", "Revision required for the previous attempt:", feedback.strip()])

    return "\n".join(lines)


def validate_queries_structure(
    queries: list[dict[str, Any]],
    *,
    num_queries: int,
) -> StructuralValidationResult:
    errors: list[str] = []

    if len(queries) != num_queries:
        errors.append(f"expected {num_queries} queries, got {len(queries)}")

    ids: list[str] = []
    texts: list[str] = []
    for index, item in enumerate(queries, start=1):
        if not isinstance(item, dict):
            errors.append(f"query entry {index} is not an object")
            continue
        query_id = item.get("id")
        query_text = item.get("query")
        if not query_id or not str(query_id).strip():
            errors.append(f"query entry {index} missing id")
        else:
            ids.append(str(query_id).strip())
        if not query_text or not str(query_text).strip():
            errors.append(f"query entry {index} missing query text")
        else:
            text = str(query_text).strip()
            texts.append(text)
            if looks_like_boolean_syntax(text):
                errors.append(f"query {query_id or index} uses Boolean-style syntax")
            if len(text) > MAX_QUERY_CHARS:
                errors.append(
                    f"query {query_id or index} exceeds {MAX_QUERY_CHARS} characters"
                )
            if len(text.split()) > MAX_QUERY_WORDS:
                errors.append(f"query {query_id or index} exceeds {MAX_QUERY_WORDS} words")

    if len(ids) != len(set(ids)):
        errors.append("duplicate query ids")
    normalized = [text.lower() for text in texts]
    if len(normalized) != len(set(normalized)):
        errors.append("duplicate query strings")

    return StructuralValidationResult(valid=not errors, errors=errors)


def looks_like_boolean_syntax(query: str) -> bool:
    return bool(_BOOLEAN_PATTERN.search(query))


def build_portfolio_classification_prompt(
    *,
    queries: list[dict[str, Any]],
    user_goal: str,
    retrieval_objective: str | None,
) -> str:
    objective_block = (
        retrieval_objective.strip()
        if retrieval_objective and retrieval_objective.strip()
        else "Infer the target record type from the research goal."
    )
    compact = [
        {"id": item.get("id"), "query": item.get("query"), "rationale": item.get("rationale")}
        for item in queries
    ]
    return "\n".join(
        [
            "Classify each OpenAlex search query for portfolio validation.",
            "",
            "Research goal:",
            user_goal.strip(),
            "",
            "Retrieval objective:",
            objective_block,
            "",
            "Categories:",
            "- targeted_producer: explicit producer signals for the target record type",
            "- broad_recall: on-topic high-recall phrasing without requiring explicit producer "
            "signals",
            "- downstream_consumer: primarily about applying published parameters or downstream "
            "modeling rather than producing new target records",
            "",
            "Queries:",
            json.dumps(compact, indent=2),
            "",
            "Return JSON only:",
            '{"classifications": [{"id": "q1", "category": "targeted_producer"}], '
            '"summary": {"targeted_producer": 0, "broad_recall": 0, "downstream_consumer": 0}}',
        ]
    )


def parse_portfolio_classification(payload: dict[str, Any]) -> PortfolioMetrics:
    summary = payload.get("summary") or {}
    classifications = payload.get("classifications") or []
    if not isinstance(classifications, list):
        classifications = []

    targeted = int(summary.get("targeted_producer", 0) or 0)
    broad = int(summary.get("broad_recall", 0) or 0)
    consumer = int(summary.get("downstream_consumer", 0) or 0)

    parsed: list[dict[str, str]] = []
    if classifications:
        targeted = broad = consumer = 0
        for item in classifications:
            if not isinstance(item, dict):
                continue
            category = str(item.get("category", "")).strip()
            parsed.append({"id": str(item.get("id", "")), "category": category})
            if category == "targeted_producer":
                targeted += 1
            elif category == "broad_recall":
                broad += 1
            elif category == "downstream_consumer":
                consumer += 1
    else:
        parsed = [
            {"id": str(item.get("id", "")), "category": str(item.get("category", ""))}
            for item in classifications
            if isinstance(item, dict)
        ]

    return PortfolioMetrics(
        targeted_producer=targeted,
        broad_recall=broad,
        downstream_consumer=consumer,
        classifications=parsed,
    )


def validate_query_portfolio(
    *,
    queries: list[dict[str, Any]],
    num_queries: int,
    metrics: PortfolioMetrics | None,
) -> PortfolioValidationResult:
    structural = validate_queries_structure(queries, num_queries=num_queries)
    errors = list(structural.errors)
    warnings: list[str] = []

    if metrics is None:
        return PortfolioValidationResult(
            valid=structural.valid,
            structural=structural,
            metrics=None,
            errors=errors,
            warnings=warnings,
        )

    total = metrics.total or len(queries)
    if total != num_queries:
        errors.append(f"portfolio classification count {total} != expected {num_queries}")

    portfolio_errors: list[str] = []
    if total > 0:
        targeted_fraction = metrics.targeted_producer / total
        broad_fraction = metrics.broad_recall / total

        warnings.append(
            "portfolio mix: "
            f"targeted={metrics.targeted_producer} ({targeted_fraction:.0%}), "
            f"broad_recall={metrics.broad_recall} ({broad_fraction:.0%}), "
            f"consumer={metrics.downstream_consumer} ({metrics.downstream_consumer / total:.0%})"
        )

        if targeted_fraction < TARGETED_REGEN_MIN or targeted_fraction > TARGETED_REGEN_MAX:
            portfolio_errors.append(
                "targeted producer fraction "
                f"{targeted_fraction:.0%} outside acceptable "
                f"{TARGETED_REGEN_MIN:.0%}-{TARGETED_REGEN_MAX:.0%} band"
            )
        if broad_fraction < BROAD_REGEN_MIN or broad_fraction > BROAD_REGEN_MAX:
            portfolio_errors.append(
                "broad-recall fraction "
                f"{broad_fraction:.0%} outside acceptable "
                f"{BROAD_REGEN_MIN:.0%}-{BROAD_REGEN_MAX:.0%} band"
            )

        consumer_limit = max(MAX_CONSUMER_COUNT, int(round(num_queries * MAX_CONSUMER_FRACTION)))
        if metrics.downstream_consumer > consumer_limit:
            portfolio_errors.append(
                f"too many downstream-consumer queries ({metrics.downstream_consumer} > "
                f"{consumer_limit})"
            )

    errors.extend(portfolio_errors)
    return PortfolioValidationResult(
        valid=not errors,
        structural=structural,
        metrics=metrics,
        errors=errors,
        warnings=warnings,
    )


def build_regeneration_feedback(validation: PortfolioValidationResult) -> str:
    lines = ["Fix all of the following issues in a complete replacement query set:"]
    for error in validation.errors:
        lines.append(f"- {error}")
    if validation.metrics is not None:
        consumer_ids = [
            item["id"]
            for item in validation.metrics.classifications
            if item.get("category") == "downstream_consumer"
        ]
        if consumer_ids:
            lines.append(
                "- Replace or rewrite downstream-consumer queries: " + ", ".join(consumer_ids)
            )
    lines.append(
        f"- Restore portfolio balance near {int(TARGETED_FRACTION_MIN * 100)}-"
        f"{int(TARGETED_FRACTION_MAX * 100)}% targeted producer and "
        f"{int(BROAD_FRACTION_MIN * 100)}-{int(BROAD_FRACTION_MAX * 100)}% broad-recall."
    )
    return "\n".join(lines)


def portfolio_validation_to_dict(validation: PortfolioValidationResult) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "valid": validation.valid,
        "errors": validation.errors,
        "warnings": validation.warnings,
        "structural_valid": validation.structural.valid,
    }
    if validation.metrics is not None:
        payload["metrics"] = {
            "targeted_producer": validation.metrics.targeted_producer,
            "broad_recall": validation.metrics.broad_recall,
            "downstream_consumer": validation.metrics.downstream_consumer,
        }
    return payload
