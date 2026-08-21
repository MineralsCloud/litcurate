"""Shared constants for pipeline stages and statuses."""

from enum import Enum


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PaperStageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


STAGE_ORDER = [
    "query_generation",
    "openalex_search",
    "merge_rank",
    "filter_abstracts",
    "download_pdfs",
    "convert_marker",
    "clean_markdown",
    "pre_extract",
    "filter_fulltext",
    "extract_schema",
    "export",
]

PAPER_STAGE_FIELDS = [
    "download_status",
    "convert_status",
    "clean_status",
    "extract_status",
]

DEFAULT_RUNS_DIR = "runs"
DEFAULT_LLM_MODEL = "claude-sonnet-4-6"

# Semantic search supports only a subset of filters; heavy filters cause 504 timeouts.
# Full-paper quality gates (DOI, abstract, work type, journal blocklist) run at merge_rank.
EXCLUDED_WORK_TYPES = frozenset(
    {
        "conference-abstract",
        "paratext",
        "letter",
        "editorial",
        "erratum",
        "correction",
        "retraction",
    }
)

# Prefer published journal articles; override / extend via merge.extra_exclude_journal_substrings.
DEFAULT_EXCLUDE_JOURNAL_SUBSTRINGS = [
    "arXiv",
]
