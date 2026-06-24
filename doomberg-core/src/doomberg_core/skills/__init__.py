"""doomberg_core.skills — the agent-callable Skill catalog over the v1 archive.

Every skill is a declarative, code-free read against the :class:`ArchiveGateway` protocol
(NO agent code ever runs). Each returns the v2 provenance envelope:

    {"data": ..., "provenance": {"source": "doomberg-v1-archive", "freshness": ..., "pit": ...},
     "warnings": [...]}

``pit`` is ``True`` only for ``fundamentals.pit`` (real point-in-time fundamentals); every other
skill is ``pit: False`` (the archive is restated reference data). ``freshness`` is the max
``updated_at`` / ``fetched_at`` of the rows the skill actually used, or ``None`` when nothing
resolved.

The :class:`ArchiveGateway` Protocol is DEFINED here (per the shared contract) so Stream 3 codes
against the seam without hard-importing Stream 1's package — integration is a no-op because both
sides build to the same protocol.
"""
from __future__ import annotations

from .archive import ArchiveGateway
from .manifest import ALL_SKILL_MANIFESTS, CORE_SKILL_MANIFESTS, SKILL_MANIFESTS
from .skillset import SKILLS, SkillSet

__all__ = [
    "ALL_SKILL_MANIFESTS",
    "ArchiveGateway",
    "CORE_SKILL_MANIFESTS",
    "SKILL_MANIFESTS",
    "SKILLS",
    "SkillSet",
]
