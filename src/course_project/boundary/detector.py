"""Deterministic packet-boundary candidate detection (Track D).

Generates candidate split positions from deterministic evidence (repeated
prefix, periodicity, entropy valleys), scores them with the component scores in
``boundary.scoring`` and emits shared-contract :class:`PacketCandidate` objects.

See ``docs/design-v1.md`` section 5.3.
"""

from __future__ import annotations

from course_project.boundary.scoring import (
    entropy_transition_score,
    field_stability_score,
    length_consistency_score,
    prefix_repeat_score,
    weighted_score,
)
from course_project.features.entropy import local_entropy
from course_project.features.stats import autocorrelation, repeated_prefix
from course_project.io.records import ByteStream
from course_project.models import PacketCandidate

DEFAULT_WEIGHTS = {"prefix": 0.25, "length": 0.25, "entropy": 0.25, "field": 0.25}

_VALLEY_DEPTH = 1.0  # bits: minimum entropy dip for a valley to count
_VALLEY_SNAP_TOLERANCE = 16  # bytes: snap a valley to a nearby prefix occurrence
_PEAK_PERIODICITY = 0.8


def generate_candidate_positions(
    data: bytes,
    *,
    prefix_max_len: int = 4,
    entropy_window: int = 32,
    entropy_step: int = 8,
    min_gap: int = 8,
    max_candidates: int = 200,
) -> list[int]:
    """Candidate split positions strictly inside ``data``, sorted ascending.

    Sources: repeated-prefix occurrences, periodic offsets from the strongest
    autocorrelation lag, and local-entropy valleys. Positions closer than
    ``min_gap`` are merged (first kept) and the list is capped at
    ``max_candidates`` (earliest kept) for determinism.
    """
    positions: set[int] = set()
    prefix_occurrences: list[int] = []

    prefix = repeated_prefix(data, max_len=prefix_max_len)
    if prefix:
        start = 1
        while True:
            idx = data.find(prefix, start)
            if idx == -1:
                break
            positions.add(idx)
            prefix_occurrences.append(idx)
            start = idx + 1

    if len(data) >= 4:
        lags = autocorrelation(data, max_lag=min(64, len(data) // 2))
        if lags:
            best_lag = max(range(1, len(lags) + 1), key=lambda lag: lags[lag - 1])
            if lags[best_lag - 1] >= _PEAK_PERIODICITY:
                positions.update(
                    k * best_lag for k in range(1, len(data) // best_lag + 1)
                )

    series = local_entropy(data, window=entropy_window, step=entropy_step)
    for i in range(1, len(series) - 1):
        left = series[i - 1][1]
        mid = series[i][1]
        right = series[i + 1][1]
        if mid < left - _VALLEY_DEPTH and mid < right - _VALLEY_DEPTH:
            valley = series[i][0]
            if prefix_occurrences:
                nearest = min(prefix_occurrences, key=lambda p: abs(p - valley))
                if abs(nearest - valley) <= _VALLEY_SNAP_TOLERANCE:
                    positions.add(nearest)
                    continue
            positions.add(valley)

    kept: list[int] = []
    for p in sorted(positions):
        if 0 < p < len(data) and (not kept or p - kept[-1] >= min_gap):
            kept.append(p)
    return kept[:max_candidates]


def detect_boundaries(
    stream: ByteStream,
    *,
    weights: dict[str, float] | None = None,
    prefix_max_len: int = 4,
    entropy_window: int = 32,
    entropy_step: int = 8,
    transition_window: int = 32,
    header_len: int = 4,
    min_gap: int = 8,
    max_candidates: int = 200,
) -> list[PacketCandidate]:
    """Detect packet-boundary candidates in a ByteStream.

    Returns one :class:`PacketCandidate` per segment between scored boundary
    positions. Offsets are absolute to the source (``offset_base`` rebased);
    ``confidence`` is the average of the two delimiting boundary scores and
    ``evidence`` keeps the per-component breakdown for downstream modules.
    """
    w = _validate_weights(weights)
    data = stream.data
    if not data:
        return []

    positions = generate_candidate_positions(
        data,
        prefix_max_len=prefix_max_len,
        entropy_window=entropy_window,
        entropy_step=entropy_step,
        min_gap=min_gap,
        max_candidates=max_candidates,
    )
    boundaries = [0, *positions, len(data)]
    prefix = repeated_prefix(data, max_len=prefix_max_len)

    scored: list[tuple[float, dict[str, float]]] = []
    for i, position in enumerate(boundaries):
        if position == 0 or position == len(data):
            scored.append((1.0, {"stream_edge": 1.0}))
            continue
        components = {
            "prefix": prefix_repeat_score(data, position, prefix),
            "length": length_consistency_score(boundaries, i),
            "entropy": entropy_transition_score(data, position, transition_window),
            "field": field_stability_score(data, boundaries, i, header_len),
        }
        scored.append((weighted_score(components, w), components))

    candidates: list[PacketCandidate] = []
    for i in range(len(boundaries) - 1):
        start, end = boundaries[i], boundaries[i + 1]
        start_score, start_comps = scored[i]
        end_score, end_comps = scored[i + 1]
        candidates.append(
            PacketCandidate(
                start_offset=stream.offset_base + start,
                end_offset=stream.offset_base + end,
                confidence=(start_score + end_score) / 2,
                direction=stream.direction,
                timestamp=stream.timestamp,
                evidence={
                    "length": end - start,
                    "start_boundary": {
                        "offset": stream.offset_base + start,
                        "score": start_score,
                        "components": start_comps,
                    },
                    "end_boundary": {
                        "offset": stream.offset_base + end,
                        "score": end_score,
                        "components": end_comps,
                    },
                },
            )
        )
    return candidates


def _validate_weights(weights: dict[str, float] | None) -> dict[str, float]:
    if weights is None:
        return dict(DEFAULT_WEIGHTS)
    unknown = set(weights) - set(DEFAULT_WEIGHTS)
    if unknown:
        raise ValueError(f"unknown boundary weight keys: {sorted(unknown)}")
    total = sum(weights.get(k, 0.0) for k in DEFAULT_WEIGHTS)
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"boundary weights must sum to 1.0, got {total}")
    return {k: weights.get(k, 0.0) for k in DEFAULT_WEIGHTS}
