"""Pipeline stage registry."""

from litcurate.stages.base import Stage, StageContext, StageResult
from litcurate.stages.registry import STAGES, get_stage, stage_names

__all__ = [
    "STAGES",
    "Stage",
    "StageContext",
    "StageResult",
    "get_stage",
    "stage_names",
]
