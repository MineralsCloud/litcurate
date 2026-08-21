"""Pydantic models for pipeline configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from litcurate.constants import DEFAULT_LLM_MODEL


class LlmConfig(BaseModel):
    """LLM backend settings. Global `llm` is required; stages may override provider fields."""

    provider: str  # anthropic | openai_compatible — required, no default
    base_url: str | None = None  # e.g. http://localhost:11434/v1 (Ollama)
    api_key_env: str | None = None  # default: ANTHROPIC_API_KEY or OPENAI_API_KEY
    timeout_seconds: float = 600.0

    @field_validator("provider")
    @classmethod
    def _validate_provider(cls, value: str) -> str:
        allowed = {"anthropic", "openai_compatible"}
        if value not in allowed:
            raise ValueError(
                f"llm.provider must be one of {sorted(allowed)}, got {value!r}"
            )
        return value

    def resolved_api_key_env(self) -> str:
        if self.api_key_env:
            return self.api_key_env
        if self.provider == "openai_compatible":
            return "OPENAI_API_KEY"
        return "ANTHROPIC_API_KEY"


def resolve_stage_llm(global_llm: LlmConfig, stage: Any) -> LlmConfig:
    """Merge optional per-stage provider overrides onto the global llm config."""
    merged = global_llm.model_dump()
    for field in ("provider", "base_url", "api_key_env", "timeout_seconds"):
        value = getattr(stage, field, None)
        if value is not None:
            merged[field] = value
    return LlmConfig(**merged)


class RunConfig(BaseModel):
    name: str
    user_goal: str


class MergeConfig(BaseModel):
    strategy: str = "union_dedupe_rank"
    min_query_hits: int = 1
    top_k: int = 200
    frequency_weight: float = 1.0
    relevance_weight: float = 1.0
    citation_weight: float = 0.1
    extra_exclude_journal_substrings: list[str] = Field(default_factory=list)


class YearSliceConfig(BaseModel):
    """Inclusive publication-year window for one semantic search pass."""

    year_min: int | None = None
    year_max: int | None = None


class OpenAlexConfig(BaseModel):
    max_results_per_query: int = 50
    per_page: int = 50
    year_min: int | None = None
    year_max: int | None = None
    year_slices: list[YearSliceConfig] = Field(default_factory=list)
    extra_filter: str | None = None
    is_oa: bool | None = None
    request_delay_seconds: float = 0.1

    def search_year_slices(self) -> list[YearSliceConfig]:
        """Return year windows to search; each can yield up to 50 semantic hits."""
        if self.year_slices:
            return self.year_slices
        if self.year_min is not None or self.year_max is not None:
            return [YearSliceConfig(year_min=self.year_min, year_max=self.year_max)]
        return [YearSliceConfig()]

    def slice_result_suffix(self, slice_cfg: YearSliceConfig) -> str:
        """Filename suffix when multiple year slices are configured."""
        if len(self.search_year_slices()) <= 1:
            return ""
        lo = slice_cfg.year_min if slice_cfg.year_min is not None else "start"
        hi = slice_cfg.year_max if slice_cfg.year_max is not None else "up"
        return f"_y{lo}_{hi}"


class SearchConfig(BaseModel):
    num_queries: int = 20
    model: str = DEFAULT_LLM_MODEL
    provider: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    timeout_seconds: float | None = None
    full_papers_only: bool = True
    retrieval_objective: str | None = None
    merge: MergeConfig = Field(default_factory=MergeConfig)
    openalex: OpenAlexConfig = Field(default_factory=OpenAlexConfig)


class AbstractFilterConfig(BaseModel):
    criteria: str
    model: str = DEFAULT_LLM_MODEL
    provider: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    timeout_seconds: float | None = None
    batch_size: int = 20
    max_tokens: int = 8192


class DownloadConfig(BaseModel):
    unpaywalled_only: bool = False
    request_delay_seconds: float = 1.0


class ConversionConfig(BaseModel):
    engine: str = "marker"
    device: str = "auto"  # auto, cuda, mps, cpu


class ExtractionSchemaRef(BaseModel):
    name: str
    path: str
    prompt: str | None = None
    format: str = "json_schema"  # json_schema | yaml_schema | declarative_yaml | pydantic
    version: str | None = None
    model: str | None = None
    markdown_max_chars: int | None = None
    empty_list_field: str | None = None
    skip_when_prior_empty: str | None = None
    # When set (e.g. "papers_meta"), fill from OpenAlex/parquet instead of calling an LLM.
    fill_from: str | None = None

    @model_validator(mode="after")
    def prompt_required_unless_fill_from(self) -> ExtractionSchemaRef:
        if self.fill_from:
            return self
        if not self.prompt:
            raise ValueError("prompt is required unless fill_from is set")
        return self


class ExtractionConfig(BaseModel):
    schemas: list[ExtractionSchemaRef] = Field(default_factory=list)
    model: str = DEFAULT_LLM_MODEL
    provider: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    timeout_seconds: float | None = None
    markdown_max_chars: int = 120_000
    # full_document = Marker markdown (not stripped);
    # cleaned_markdown = output of clean_markdown (after strip_*).
    section_mode: str = "cleaned_markdown"


class PreExtractConfig(BaseModel):
    enabled: bool = False
    regex_signals: list[str] = Field(default_factory=list)
    min_signal_hits: int = 1
    case_insensitive: bool = True


class FulltextFilterConfig(BaseModel):
    enabled: bool = False
    criteria: str = ""
    model: str = DEFAULT_LLM_MODEL
    provider: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    timeout_seconds: float | None = None
    batch_size: int = 5
    max_tokens: int = 8192
    input_max_chars: int = 8_000


class MarkdownCleanConfig(BaseModel):
    strip_references: bool = True
    strip_acknowledgments: bool = True
    strip_supplementary: bool = True
    strip_funding: bool = True
    # Supplementary/acknowledgment/funding headers in publisher front matter must
    # not truncate the paper body (references still strip at first header match).
    min_body_lines_before_strip: int = 40
    heavy_strip_fraction: float = 0.5


class PipelineConfig(BaseModel):
    run: RunConfig
    llm: LlmConfig
    search: SearchConfig = Field(default_factory=SearchConfig)
    abstract_filter: AbstractFilterConfig
    download: DownloadConfig = Field(default_factory=DownloadConfig)
    conversion: ConversionConfig = Field(default_factory=ConversionConfig)
    markdown_clean: MarkdownCleanConfig = Field(default_factory=MarkdownCleanConfig)
    pre_extract: PreExtractConfig = Field(default_factory=PreExtractConfig)
    fulltext_filter: FulltextFilterConfig = Field(default_factory=FulltextFilterConfig)
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    dry_run: bool = False

    @field_validator("abstract_filter", mode="before")
    @classmethod
    def _require_abstract_filter(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("abstract_filter is required")
        return value


def load_config(path: Path, *, project_root: Path | None = None) -> PipelineConfig:
    """Load and validate a YAML pipeline config."""
    config_path = Path(path).resolve()
    with config_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    config = PipelineConfig.model_validate(raw)
    root = project_root or _find_project_root(config_path)
    _resolve_schema_paths(config, root)
    return config


def _find_project_root(config_path: Path) -> Path:
    for parent in [config_path.parent, *config_path.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    return config_path.parent


def _resolve_schema_paths(config: PipelineConfig, root: Path) -> None:
    for schema in config.extraction.schemas:
        if schema.format != "pydantic":
            schema_path = Path(schema.path)
            if not schema_path.is_absolute():
                schema.path = str((root / schema_path).resolve())
        if schema.prompt:
            prompt_path = Path(schema.prompt)
            if not prompt_path.is_absolute():
                schema.prompt = str((root / prompt_path).resolve())


def snapshot_config(config: PipelineConfig, dest: Path) -> Path:
    """Write a resolved config snapshot for reproducibility."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = config.model_dump(mode="json")
    with dest.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)
    return dest
