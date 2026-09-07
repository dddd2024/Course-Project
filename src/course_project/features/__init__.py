"""Byte/statistical feature extraction (Track D).

Deterministic features over raw byte streams: entropy, byte distribution,
n-grams, periodicity and repetition probes. No protocol-semantic conclusions
are drawn here.
"""

from course_project.features.aggregate import compute_features
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

__all__ = [
    "autocorrelation",
    "byte_frequencies",
    "compute_features",
    "local_entropy",
    "printable_ratio",
    "repeated_prefix",
    "repeated_suffix",
    "shannon_entropy",
    "top_ngrams",
    "zero_ratio",
]
