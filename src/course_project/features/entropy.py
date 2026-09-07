"""Byte-level entropy features (Track D).

Deterministic Shannon-entropy computations over raw byte streams. Consumed by
``boundary`` (entropy transitions) and by Track C as evidence observations.

See ``docs/design-v1.md`` section 5.2.
"""

from __future__ import annotations

import math
from collections import Counter


def shannon_entropy(data: bytes) -> float:
    """Shannon entropy of the byte distribution, in bits per byte (0..8).

    An empty input returns 0.0 instead of NaN so feature records stay
    JSON-serializable and comparable.
    """
    if not data:
        return 0.0
    total = len(data)
    counts = Counter(data)
    entropy = 0.0
    for count in counts.values():
        p = count / total
        entropy -= p * math.log2(p)
    return entropy


def local_entropy(
    data: bytes, *, window: int = 64, step: int = 16
) -> list[tuple[int, float]]:
    """Sliding-window Shannon entropy.

    Returns ``(window_start_offset, entropy)`` pairs for every full window.
    Offsets are relative to ``data``; callers rebase them with
    ``ByteStream.offset_base`` when reporting absolute positions.

    When ``data`` is shorter than ``window``, a single window covering the
    whole input is returned.
    """
    if window < 1:
        raise ValueError("window must be >= 1")
    if step < 1:
        raise ValueError("step must be >= 1")
    if not data:
        return []
    if len(data) < window:
        return [(0, shannon_entropy(data))]
    return [
        (start, shannon_entropy(data[start : start + window]))
        for start in range(0, len(data) - window + 1, step)
    ]
