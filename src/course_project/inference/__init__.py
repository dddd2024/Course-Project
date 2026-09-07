"""Message clustering, alignment and field candidates (Track D).

Public D->C boundary functions (``family_analysis``, ``infer_field_candidates``)
return the frozen ``course_project.models`` DTOs. Internal profiles
(``ColumnProfile`` / ``FamilyProfile``) and semantic-tagged hypotheses
(``inference.fields``) never cross that boundary.
"""

from course_project.inference.alignment import (
    ColumnProfile,
    FamilyProfile,
    align_family,
)
from course_project.inference.clustering import cluster_messages, message_similarity
from course_project.inference.netzob_adapter import (
    PREBaselineResult,
    convert_field_segments,
    is_netzob_available,
    run_netzob_baseline,
)
from course_project.inference.public import (
    family_analysis,
    infer_field_candidates,
    to_field_candidate,
)

__all__ = [
    "ColumnProfile",
    "FamilyProfile",
    "PREBaselineResult",
    "align_family",
    "cluster_messages",
    "convert_field_segments",
    "family_analysis",
    "infer_field_candidates",
    "is_netzob_available",
    "message_similarity",
    "run_netzob_baseline",
    "to_field_candidate",
]
