"""Evidence registry and provenance graph for EvidenceGraph-PRE.

Track C owns implementation in this package. Public objects should use the
project-native contracts from ``course_project.models``.
"""

from course_project.evidence.graph import EvidenceGraph, EvidenceGraphError
from course_project.evidence.producers import (
    EvidenceProductionError,
    evidence_from_executable_check,
    evidence_from_field_candidate,
    evidence_from_llm_hypothesis,
)

__all__ = [
    "EvidenceGraph",
    "EvidenceGraphError",
    "EvidenceProductionError",
    "evidence_from_executable_check",
    "evidence_from_field_candidate",
    "evidence_from_llm_hypothesis",
]
