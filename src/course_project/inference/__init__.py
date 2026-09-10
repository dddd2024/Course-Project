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
from course_project.inference.binaryinferno_adapter import (
    BINARYINFERNO_UPSTREAM_COMMIT,
    BinaryInfernoConfig,
    BinaryInfernoExecutionError,
    BinaryInfernoOutputError,
    BinaryInfernoRunner,
    SubprocessBinaryInfernoRunner,
    encode_binaryinferno_input,
    is_binaryinferno_available,
    parse_binaryinferno_spec,
    run_binaryinferno_baseline,
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
    refine_boundaries,
    to_field_candidate,
)

__all__ = [
    "BINARYINFERNO_UPSTREAM_COMMIT",
    "BinaryInfernoConfig",
    "BinaryInfernoExecutionError",
    "BinaryInfernoOutputError",
    "BinaryInfernoRunner",
    "ColumnProfile",
    "FamilyProfile",
    "PREBaselineResult",
    "SubprocessBinaryInfernoRunner",
    "align_family",
    "cluster_messages",
    "convert_field_segments",
    "encode_binaryinferno_input",
    "family_analysis",
    "infer_field_candidates",
    "is_binaryinferno_available",
    "is_netzob_available",
    "message_similarity",
    "parse_binaryinferno_spec",
    "refine_boundaries",
    "run_binaryinferno_baseline",
    "run_netzob_baseline",
    "to_field_candidate",
]
