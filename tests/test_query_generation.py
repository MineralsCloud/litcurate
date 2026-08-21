"""Tests for query generation prompt and portfolio validation."""

from litcurate.config import SearchConfig
from litcurate.query_portfolio import (
    PortfolioMetrics,
    build_query_generation_prompt,
    looks_like_boolean_syntax,
    parse_portfolio_classification,
    validate_queries_structure,
    validate_query_portfolio,
)


def test_search_config_accepts_retrieval_objective() -> None:
    config = SearchConfig(
        retrieval_objective="Find papers with fitted parameters and tables.",
    )
    assert config.retrieval_objective == "Find papers with fitted parameters and tables."


def test_build_query_generation_prompt_without_retrieval_objective() -> None:
    prompt = build_query_generation_prompt(
        num_queries=5,
        user_goal="Build a structured database from primary literature.",
        retrieval_objective=None,
    )
    assert "Build a structured database from primary literature." in prompt
    assert "Research goal" in prompt
    assert "Retrieval objective" not in prompt
    assert "target-record producer signals" in prompt


def test_build_query_generation_prompt_with_retrieval_objective() -> None:
    prompt = build_query_generation_prompt(
        num_queries=20,
        user_goal="Literature database for a research topic.",
        retrieval_objective="Retrieve primary studies with extractable numeric results.",
    )
    assert "Literature database for a research topic." in prompt
    assert "Retrieve primary studies with extractable numeric results." in prompt
    assert "producer study" in prompt
    assert "consumer study" in prompt
    assert "13-15 queries (65-75%)" in prompt
    assert "5-7 queries (25-35%)" in prompt
    assert "downstream consumers" in prompt
    assert "exactly 20" in prompt


def test_build_query_generation_prompt_includes_feedback() -> None:
    prompt = build_query_generation_prompt(
        num_queries=10,
        user_goal="Goal",
        retrieval_objective="Objective",
        feedback="Too many consumer queries.",
    )
    assert "Revision required" in prompt
    assert "Too many consumer queries." in prompt


def test_looks_like_boolean_syntax() -> None:
    assert looks_like_boolean_syntax("catalyst AND reaction kinetics")
    assert looks_like_boolean_syntax('("protein" OR enzyme)')
    assert not looks_like_boolean_syntax("high-pressure compression of materials")


def test_validate_queries_structure() -> None:
    queries = [
        {"id": "q1", "query": "primary experimental measurements topic", "rationale": "targeted"},
        {"id": "q2", "query": "high-throughput screening methods", "rationale": "broad"},
    ]
    result = validate_queries_structure(queries, num_queries=2)
    assert result.valid

    bad_count = validate_queries_structure(queries, num_queries=3)
    assert not bad_count.valid
    assert any("expected 3" in error for error in bad_count.errors)

    duplicate = queries + [{"id": "q1", "query": "duplicate topic query", "rationale": "dup"}]
    dup_result = validate_queries_structure(duplicate, num_queries=3)
    assert not dup_result.valid


def test_validate_query_portfolio_mix() -> None:
    queries = [{"id": f"q{i}", "query": f"query topic {i}", "rationale": "r"} for i in range(1, 21)]
    metrics = PortfolioMetrics(targeted_producer=14, broad_recall=6, downstream_consumer=0)
    validation = validate_query_portfolio(queries=queries, num_queries=20, metrics=metrics)
    assert validation.valid
    assert validation.metrics is not None
    assert validation.metrics.targeted_producer == 14

    bad_mix = PortfolioMetrics(targeted_producer=8, broad_recall=10, downstream_consumer=2)
    bad_validation = validate_query_portfolio(queries=queries, num_queries=20, metrics=bad_mix)
    assert not bad_validation.valid
    assert any("targeted producer fraction" in error for error in bad_validation.errors)


def test_parse_portfolio_classification_from_items() -> None:
    payload = {
        "classifications": [
            {"id": "q1", "category": "targeted_producer"},
            {"id": "q2", "category": "broad_recall"},
            {"id": "q3", "category": "downstream_consumer"},
        ]
    }
    metrics = parse_portfolio_classification(payload)
    assert metrics.targeted_producer == 1
    assert metrics.broad_recall == 1
    assert metrics.downstream_consumer == 1
