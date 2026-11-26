"""Built-in stages, by name, in pipeline order."""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from card_update.stages.approve import ApproveStage
from card_update.stages.base import Stage
from card_update.stages.build import BuildStage
from card_update.stages.check import CheckStage
from card_update.stages.cleanup import CleanupStage
from card_update.stages.enrich import EnrichStage
from card_update.stages.fetch import FetchStage
from card_update.stages.health import HealthStage
from card_update.stages.prep import PrepStage
from card_update.stages.promote import PromoteStage
from card_update.stages.rebuild import RebuildStage
from card_update.stages.verify import VerifyStage

BUILTIN_STAGES: Mapping[str, type[Stage]] = MappingProxyType({cls.name: cls for cls in (
    CheckStage, FetchStage, PrepStage, EnrichStage, BuildStage, VerifyStage,
    ApproveStage, PromoteStage, RebuildStage, HealthStage, CleanupStage,
)})
