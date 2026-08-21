"""Stage metadata for modular runs and artifact inspection."""

from __future__ import annotations

# Paths relative to the run directory that `reset-stage` should clear.
# Directories ending with "/" are removed entirely (or paper-scoped files inside).
STAGE_RESET_ARTIFACTS: dict[str, list[str]] = {
    "query_generation": ["artifacts/queries.json"],
    "openalex_search": ["artifacts/openalex_raw/"],
    "merge_rank": ["artifacts/papers_ranked.parquet"],
    "filter_abstracts": [
        "artifacts/papers_filtered.parquet",
        "artifacts/filter_abstracts.checkpoint.json",
    ],
    "download_pdfs": [
        "artifacts/download_manifest.json",
        "artifacts/download_manifest.checkpoint.json",
        "artifacts/pdfs/",
    ],
    "convert_marker": [
        "artifacts/convert_manifest.json",
        "artifacts/markdown/",
    ],
    "clean_markdown": [
        "artifacts/clean_manifest.json",
        "artifacts/markdown_clean/",
    ],
    "pre_extract": [
        "artifacts/pre_extract_manifest.json",
    ],
    "filter_fulltext": [
        "artifacts/fulltext_filter_manifest.json",
        "artifacts/fulltext_filter.checkpoint.json",
    ],
    "extract_schema": [
        "artifacts/extract_manifest.json",
        "artifacts/extractions/",
        "artifacts/extraction_failures/",
        "artifacts/extract_prompt_debug/",
    ],
    "export": [
        "artifacts/output/",
    ],
}

# Per-paper SQLite fields to reset when clearing a stage (where applicable).
STAGE_PAPER_STATUS_FIELDS: dict[str, str] = {
    "download_pdfs": "download_status",
    "convert_marker": "convert_status",
    "clean_markdown": "clean_status",
    "extract_schema": "extract_status",
}

STAGE_ARTIFACTS: dict[str, dict[str, str]] = {
    "query_generation": {
        "primary": "artifacts/queries.json",
        "description": "Generated search queries from the configured LLM",
    },
    "openalex_search": {
        "primary": "artifacts/openalex_raw/",
        "description": "OpenAlex semantic search results per query",
    },
    "merge_rank": {
        "primary": "artifacts/papers_ranked.parquet",
        "description": "Merged and ranked paper list",
    },
    "filter_abstracts": {
        "primary": "artifacts/papers_filtered.parquet",
        "description": "Papers kept after LLM abstract screening",
    },
    "download_pdfs": {
        "primary": "artifacts/download_manifest.json",
        "description": "PDF download manifest",
    },
    "convert_marker": {
        "primary": "artifacts/convert_manifest.json",
        "description": "PDF to markdown conversion manifest",
    },
    "clean_markdown": {
        "primary": "artifacts/clean_manifest.json",
        "description": "Cleaned markdown manifest",
    },
    "pre_extract": {
        "primary": "artifacts/pre_extract_manifest.json",
        "description": "Regex pre-extraction gate decisions",
    },
    "filter_fulltext": {
        "primary": "artifacts/fulltext_filter_manifest.json",
        "description": "LLM fulltext relevance screening",
    },
    "extract_schema": {
        "primary": "artifacts/extract_manifest.json",
        "description": "Schema extraction manifest",
    },
    "export": {
        "primary": "artifacts/output/database.json",
        "description": "Merged extraction database for ingest",
    },
}

STAGE_PREREQUISITES: dict[str, list[str]] = {
    "query_generation": [],
    "openalex_search": ["artifacts/queries.json"],
    "merge_rank": [],
    "filter_abstracts": ["artifacts/papers_ranked.parquet"],
    "download_pdfs": ["artifacts/papers_filtered.parquet"],
    "convert_marker": ["artifacts/download_manifest.json"],
    "clean_markdown": ["artifacts/convert_manifest.json"],
    "pre_extract": ["artifacts/clean_manifest.json"],
    "filter_fulltext": ["artifacts/pre_extract_manifest.json"],
    "extract_schema": ["artifacts/fulltext_filter_manifest.json"],
    "export": ["artifacts/extract_manifest.json"],
}
