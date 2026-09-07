"""Aggregate deterministic features for one ByteStream (Track D)."""

from __future__ import annotations

from typing import Any

from course_project.features.entropy import local_entropy, shannon_entropy
from course_project.features.stats import (
    autocorrelation,
    byte_frequencies,
    printable_ratio,
    repeated_prefix,
    repeated_suffix,
    top_ngrams,
    zero_ratio,
)
from course_project.io.records import ByteStream


def compute_features(
    stream: ByteStream,
    *,
    window: int = 64,
    step: int = 16,
    ngram_n: int = 2,
    ngram_k: int = 8,
    max_lag: int = 32,
    max_repeat_len: int = 64,
) -> dict[str, Any]:
    """Compute the deterministic V1 feature record for a ByteStream.

    The result is a plain JSON-serializable dict so Track C can convert
    individual entries into ``Evidence.observation`` values without importing
    Track D internals.
    """
    data = stream.data
    ngrams = top_ngrams(data, ngram_n, ngram_k)
    prefix = repeated_prefix(data, max_repeat_len)
    suffix = repeated_suffix(data, max_repeat_len)
    return {
        "source_id": stream.source_id,
        "size": stream.size,
        "global_entropy": shannon_entropy(data),
        "local_entropy": [
            {"offset": stream.offset_base + offset, "entropy": entropy}
            for offset, entropy in local_entropy(data, window=window, step=step)
        ],
        "byte_frequency": byte_frequencies(data),
        "printable_ratio": printable_ratio(data),
        "zero_ratio": zero_ratio(data),
        "top_ngrams": [
            {"ngram": ngram.hex(), "count": count} for ngram, count in ngrams
        ],
        "repeated_prefix": prefix.hex() if prefix is not None else None,
        "repeated_suffix": suffix.hex() if suffix is not None else None,
        "autocorrelation": autocorrelation(data, max_lag),
    }
