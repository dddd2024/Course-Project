"""Packet/message boundary candidate detection (Track D).

Generates candidate split positions from deterministic evidence (repeated
prefix, periodicity, entropy valleys), scores them with prefix/length/entropy/
field-stability components, and emits shared-contract ``PacketCandidate``
objects.
"""

from course_project.boundary.detector import (
    detect_boundaries,
    generate_candidate_positions,
)
from course_project.boundary.scoring import (
    entropy_transition_score,
    field_stability_score,
    length_consistency_score,
    prefix_repeat_score,
    weighted_score,
)

__all__ = [
    "detect_boundaries",
    "entropy_transition_score",
    "field_stability_score",
    "generate_candidate_positions",
    "length_consistency_score",
    "prefix_repeat_score",
    "weighted_score",
]
