"""Evidence registry and provenance graph for EvidenceGraph-PRE.

Track C owns the broader EvidenceGraph-PRE research surface. Narrow delegated
integration primitives remain project-native and must not silently redefine the
shared contracts or final fusion policy.
"""

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

__all__ = [
    "DecisionVote",
    "EvidenceCollapseResult",
    "EvidenceContribution",
    "EvidenceDependencyError",
    "NaiveVoteError",
    "NaiveVoteResult",
    "collapse_dependent_evidence",
    "naive_multi_source_vote",
]
