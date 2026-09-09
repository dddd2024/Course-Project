"""Evidence registry, provenance graph and fusion primitives for EvidenceGraph-PRE."""

from course_project.evidence.dependency_collapse import (
    EvidenceCollapseResult,
    EvidenceContribution,
    EvidenceDependencyError,
    collapse_dependent_evidence,
)
from course_project.evidence.fusion import (
    FusionError,
    FusionPolicy,
    FusionResult,
    naive_vote,
    provenance_aware_fusion,
)
from course_project.evidence.global_selection import (
    POLICY_VERSION as GLOBAL_SELECTION_POLICY_VERSION,
)
from course_project.evidence.global_selection import (
    FieldSelectionCandidate,
    FieldSelectionDecision,
    GlobalFieldSelectionResult,
    GlobalSelectionError,
    select_globally_consistent_fields,
)
from course_project.evidence.graph import EvidenceGraph, EvidenceGraphError
from course_project.evidence.naive_vote import (
    DecisionVote,
    NaiveVoteError,
    NaiveVoteResult,
    naive_multi_source_vote,
)
from course_project.evidence.producers import (
    EvidenceProductionError,
    evidence_from_executable_check,
    evidence_from_field_candidate,
    evidence_from_llm_hypothesis,
)
from course_project.evidence.provenance_fusion import (
    POLICY_VERSION,
    FusionComponent,
    ProvenanceFusionError,
    ProvenanceFusionResult,
    fuse_hypothesis_evidence,
)
from course_project.evidence.workflow import (
    SemanticWorkflow,
    SemanticWorkflowError,
    SemanticWorkflowResult,
)

__all__ = [
    "GLOBAL_SELECTION_POLICY_VERSION",
    "POLICY_VERSION",
    "DecisionVote",
    "EvidenceCollapseResult",
    "EvidenceContribution",
    "EvidenceDependencyError",
    "EvidenceGraph",
    "EvidenceGraphError",
    "EvidenceProductionError",
    "FieldSelectionCandidate",
    "FieldSelectionDecision",
    "FusionComponent",
    "FusionError",
    "FusionPolicy",
    "FusionResult",
    "GlobalFieldSelectionResult",
    "GlobalSelectionError",
    "NaiveVoteError",
    "NaiveVoteResult",
    "ProvenanceFusionError",
    "ProvenanceFusionResult",
    "SemanticWorkflow",
    "SemanticWorkflowError",
    "SemanticWorkflowResult",
    "collapse_dependent_evidence",
    "evidence_from_executable_check",
    "evidence_from_field_candidate",
    "evidence_from_llm_hypothesis",
    "fuse_hypothesis_evidence",
    "naive_multi_source_vote",
    "naive_vote",
    "provenance_aware_fusion",
    "select_globally_consistent_fields",
]
]
