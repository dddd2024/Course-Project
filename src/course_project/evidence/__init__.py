"""Evidence registry, provenance graph and fusion primitives for EvidenceGraph-PRE."""

from course_project.evidence.dependency_collapse import (
    EvidenceCollapseResult,
    EvidenceContribution,
    EvidenceDependencyError,
    collapse_dependent_evidence,
)
from course_project.evidence.naive_vote import (
    DecisionVote,
    NaiveVoteError,
    NaiveVoteResult,
    naive_multi_source_vote,
)
from course_project.evidence.provenance_fusion import (
    POLICY_VERSION,
    FusionComponent,
    ProvenanceFusionError,
    ProvenanceFusionResult,
    fuse_hypothesis_evidence,
)

__all__ = [
    "POLICY_VERSION",
    "DecisionVote",
    "EvidenceCollapseResult",
    "EvidenceContribution",
    "EvidenceDependencyError",
    "FusionComponent",
    "NaiveVoteError",
    "NaiveVoteResult",
    "ProvenanceFusionError",
    "ProvenanceFusionResult",
    "collapse_dependent_evidence",
    "fuse_hypothesis_evidence",
    "naive_multi_source_vote",
]
