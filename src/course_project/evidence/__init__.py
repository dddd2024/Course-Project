"""Evidence registry and provenance graph for EvidenceGraph-PRE.

Track C owns implementation in this package. Public objects should use the
project-native contracts from ``course_project.models``.
"""

from course_project.evidence.fusion import (
    FusionError,
    FusionPolicy,
    FusionResult,
    naive_vote,
    provenance_aware_fusion,
)
from course_project.evidence.graph import EvidenceGraph, EvidenceGraphError
from course_project.evidence.producers import (
    EvidenceProductionError,
    evidence_from_executable_check,
    evidence_from_field_candidate,
    evidence_from_llm_hypothesis,
)
from course_project.evidence.workflow import (
    SemanticWorkflow,
    SemanticWorkflowError,
    SemanticWorkflowResult,
)

__all__ = [
    "EvidenceGraph",
    "EvidenceGraphError",
    "EvidenceProductionError",
    "FusionError",
    "FusionPolicy",
    "FusionResult",
    "SemanticWorkflow",
    "SemanticWorkflowError",
    "SemanticWorkflowResult",
    "evidence_from_executable_check",
    "evidence_from_field_candidate",
    "evidence_from_llm_hypothesis",
    "naive_vote",
    "provenance_aware_fusion",
]
