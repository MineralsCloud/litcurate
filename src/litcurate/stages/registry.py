"""Stage registry."""

from __future__ import annotations

from litcurate.constants import STAGE_ORDER
from litcurate.stages.base import Stage
from litcurate.stages.clean_markdown import CleanMarkdownStage
from litcurate.stages.convert_marker import ConvertMarkerStage
from litcurate.stages.download_pdfs import DownloadPdfsStage
from litcurate.stages.export import ExportStage
from litcurate.stages.extract_schema import ExtractSchemaStage
from litcurate.stages.filter_abstracts import FilterAbstractsStage
from litcurate.stages.filter_fulltext import FilterFulltextStage
from litcurate.stages.merge_rank import MergeRankStage
from litcurate.stages.openalex_search import OpenAlexSearchStage
from litcurate.stages.pre_extract import PreExtractStage
from litcurate.stages.query_generation import QueryGenerationStage

STAGES: dict[str, Stage] = {
    QueryGenerationStage.name: QueryGenerationStage(),
    OpenAlexSearchStage.name: OpenAlexSearchStage(),
    MergeRankStage.name: MergeRankStage(),
    FilterAbstractsStage.name: FilterAbstractsStage(),
    DownloadPdfsStage.name: DownloadPdfsStage(),
    ConvertMarkerStage.name: ConvertMarkerStage(),
    CleanMarkdownStage.name: CleanMarkdownStage(),
    PreExtractStage.name: PreExtractStage(),
    FilterFulltextStage.name: FilterFulltextStage(),
    ExtractSchemaStage.name: ExtractSchemaStage(),
    ExportStage.name: ExportStage(),
}

# Backward compat for runs created before the OpenAlex switch.
STAGES["consensus_search"] = STAGES[OpenAlexSearchStage.name]


def get_stage(name: str) -> Stage:
    if name not in STAGES:
        raise KeyError(f"Unknown stage: {name}")
    return STAGES[name]


def stage_names() -> list[str]:
    return list(STAGE_ORDER)
