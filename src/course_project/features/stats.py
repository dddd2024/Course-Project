"""Byte-distribution and periodicity features (Track D).

Deterministic byte-frequency, n-gram, autocorrelation and repetition probes.
No protocol-semantic conclusions are drawn here.

See ``docs/design-v1.md`` section 5.2.
"""

from __future__ import annotations

import math
from collections import Counter

_PRINTABLE_MIN = 0x20
_PRINTABLE_MAX = 0x7E


def byte_frequencies(data: bytes) -> list[int]:
    """Count of each byte value, index 0..255, summing to ``len(data)``."""
    counts = [0] * 256
    for b in data:
        counts[b] += 1
    return counts


def printable_ratio(data: bytes) -> float:
    """Fraction of bytes in the printable ASCII range ``0x20..0x7E``."""
    if not data:
        return 0.0
    printable = sum(1 for b in data if _PRINTABLE_MIN <= b <= _PRINTABLE_MAX)
    return printable / len(data)


def zero_ratio(data: bytes) -> float:
    """Fraction of zero bytes."""
    if not data:
        return 0.0
    return data.count(0) / len(data)


def top_ngrams(data: bytes, n: int, k: int = 8) -> list[tuple[bytes, int]]:
    """Most frequent ``n``-grams (overlapping windows), as ``(ngram, count)``.

    Sorted by descending count with byte-value tie-breaking for determinism.
    """
    if n < 1:
        raise ValueError("n must be >= 1")
    if k < 1:
        raise ValueError("k must be >= 1")
    if len(data) < n:
        return []
    counts = Counter(data[i : i + n] for i in range(len(data) - n + 1))
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:k]


def autocorrelation(data: bytes, max_lag: int) -> list[float]:
    """Pearson autocorrelation of byte values for lags ``1..max_lag``.

    Deterministic periodicity probe; each value is a per-lag correlation in
    ``[-1, 1]`` (0.0 where the variance is zero or undefined).
    """
    if max_lag < 1:
        raise ValueError("max_lag must be >= 1")
    if len(data) < 2:
        return []
    out: list[float] = []
    for lag in range(1, min(max_lag, len(data)) + 1):
        out.append(_pearson(data[:-lag], data[lag:]))
    return out


def _pearson(x: bytes, y: bytes) -> float:
    n = len(x)
    if n == 0:
        return 0.0
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    cov = 0.0
    var_x = 0.0
    var_y = 0.0
    for a, b in zip(x, y):
        dx = a - mean_x
        dy = b - mean_y
        cov += dx * dy
        var_x += dx * dx
        var_y += dy * dy
    if var_x == 0.0 or var_y == 0.0:
        return 0.0
    return cov / math.sqrt(var_x * var_y)


def repeated_prefix(data: bytes, max_len: int = 64) -> bytes | None:
    """Longest prefix (up to ``max_len`` bytes) that re-occurs later in the data.

    Deterministic header/magic repetition evidence available before boundary
    detection exists. Returns ``None`` when no prefix repeats.
    """
    if max_len < 1:
        raise ValueError("max_len must be >= 1")
    for length in range(min(max_len, len(data) // 2 + 1), 0, -1):
        if data.find(data[:length], 1) != -1:
            return data[:length]
    return None


def repeated_suffix(data: bytes, max_len: int = 64) -> bytes | None:
    """Longest suffix (up to ``max_len`` bytes) that occurs earlier in the data."""
    if max_len < 1:
        raise ValueError("max_len must be >= 1")
    for length in range(min(max_len, len(data) // 2 + 1), 0, -1):
        suffix = data[len(data) - length :]
        if data.find(suffix, 0, len(data) - length) != -1:
            return suffix
    return None
