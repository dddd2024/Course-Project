"""Evidence registry and provenance graph for EvidenceGraph-PRE.

Track C owns implementation in this package. Public objects should use the
project-native contracts from ``course_project.models``.
"""

from course_project.evidence.graph import EvidenceGraph, EvidenceGraphError

__all__ = ["EvidenceGraph", "EvidenceGraphError"]
