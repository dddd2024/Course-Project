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

__all__ = [
    "EvidenceCollapseResult",
    "EvidenceContribution",
    "EvidenceDependencyError",
    "collapse_dependent_evidence",
]
