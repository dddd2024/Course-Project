"""Evidence-score functions for packet-boundary candidates (Track D).

Each component returns a deterministic score in ``[0, 1]`` where ``0.5`` means
"no usable evidence". Components combine into a weighted boundary score in
``detector.detect_boundaries``.

``alignment_gain`` from the V1 design formula is intentionally not part of this
module: it depends on message clustering/alignment, which lives in the
``inference`` module and can adjust boundary confidence later.

See ``docs/design-v1.md`` section 5.3.
"""

from __future__ import annotations

from collections import Counter
from itertools import pairwise

from course_project.features.entropy import shannon_entropy

NEUTRAL = 0.5


def weighted_score(components: dict[str, float], weights: dict[str, float]) -> float:
    """Weighted sum of per-component evidence scores."""
    return sum(weights[key] * value for key, value in components.items())


def prefix_repeat_score(data: bytes, position: int, prefix: bytes | None) -> float:
    """1.0 when the repeated prefix occurs exactly at ``position``.

    0.5 when there is no prefix to test or the position is too close to the end
    of the data to verify, 0.0 on mismatch.
    """
    if not prefix:
        return NEUTRAL
    end = position + len(prefix)
    if end > len(data):
        return NEUTRAL
    return 1.0 if data[position:end] == prefix else 0.0


def length_consistency_score(boundaries: list[int], index: int) -> float:
    """How close the segment length after ``boundaries[index]`` is to the mode gap.

    Equal-length segments score 1.0; neutral 0.5 when there is only one gap.
    """
    gaps = [b - a for a, b in pairwise(boundaries)]
    if len(gaps) <= 1:
        return NEUTRAL
    gap = boundaries[index + 1] - boundaries[index]
    mode_gap = Counter(gaps).most_common(1)[0][0]
    return 1.0 - min(abs(gap - mode_gap) / max(gap, mode_gap), 1.0)


def entropy_transition_score(data: bytes, position: int, window: int = 32) -> float:
    """Boundary evidence from an entropy drop across ``position``.

    A drop of >= 2 bits scores 1.0, flat entropy scores 0.5 and a rise
    approaches 0.0. Windows are clipped at the stream edges; positions where no
    before/after window exists score 0.5.
    """
    if window < 1:
        raise ValueError("window must be >= 1")
    if position <= 0 or position >= len(data):
        return NEUTRAL
    before = data[max(0, position - window) : position]
    after = data[position : min(len(data), position + window)]
    if not before or not after:
        return NEUTRAL
    drop = shannon_entropy(before) - shannon_entropy(after)
    return max(0.0, min(NEUTRAL + drop / 4.0, 1.0))


def field_stability_score(
    data: bytes, boundaries: list[int], index: int, header_len: int = 4
) -> float:
    """Byte-match rate of the first ``header_len`` bytes after this boundary
    against the same offsets after every other boundary.

    High rates are strong magic/header evidence; neutral 0.5 when no other
    boundary provides a comparable header window.
    """
    if header_len < 1:
        raise ValueError("header_len must be >= 1")
    position = boundaries[index]
    others = [q for j, q in enumerate(boundaries) if j != index and q != len(data)]
    rates = []
    for q in others:
        h = min(header_len, len(data) - position, len(data) - q)
        if h <= 0:
            continue
        matches = sum(1 for i in range(h) if data[position + i] == data[q + i])
        rates.append(matches / h)
    if not rates:
        return NEUTRAL
    return sum(rates) / len(rates)
