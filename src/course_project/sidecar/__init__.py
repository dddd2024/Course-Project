"""Stable task-level protocol exposed to the desktop application.

Track A owns the sidecar boundary. The implementation follows the schemas in
``contracts/`` and exposes task-level operations only; it never exposes arbitrary
shell execution.
"""

from course_project.sidecar.runtime import (
    ANALYSIS_MODES,
    ANALYSIS_STAGES,
    MAX_READ_RANGE,
    PROTOCOL_VERSION,
    SIDE_CAR_METHODS,
    AnalysisBackend,
    MetadataOnlyBackend,
    SidecarError,
    SidecarRuntime,
)
from course_project.sidecar.semantic_bridge import (
    SemanticAnalysis,
    SemanticBackend,
    validate_semantic_analysis,
)
from course_project.sidecar.track_d_backend import TrackDBaselineBackend

__all__ = [
    "ANALYSIS_MODES",
    "ANALYSIS_STAGES",
    "MAX_READ_RANGE",
    "PROTOCOL_VERSION",
    "SIDE_CAR_METHODS",
    "AnalysisBackend",
    "MetadataOnlyBackend",
    "SemanticAnalysis",
    "SemanticBackend",
    "SidecarError",
    "SidecarRuntime",
    "TrackDBaselineBackend",
    "validate_semantic_analysis",
]
