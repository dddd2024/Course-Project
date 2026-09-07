from __future__ import annotations

import json
import math

import pytest

from course_project.features import (
    autocorrelation,
    byte_frequencies,
    compute_features,
    local_entropy,
    printable_ratio,
    repeated_prefix,
    repeated_suffix,
    shannon_entropy,
    top_ngrams,
    zero_ratio,
)
from course_project.io import load_raw


def test_shannon_entropy_uniform_bytes_is_8_bits() -> None:
    data = bytes(range(256)) * 4
    assert shannon_entropy(data) == pytest.approx(8.0)


def test_shannon_entropy_two_symbols_is_1_bit() -> None:
    assert shannon_entropy(b"\x00\xff" * 8) == pytest.approx(1.0)


def test_shannon_entropy_single_symbol_is_zero() -> None:
    assert shannon_entropy(b"\x42" * 10) == 0.0


def test_shannon_entropy_empty_is_zero() -> None:
    assert shannon_entropy(b"") == 0.0


def test_local_entropy_offsets_and_values() -> None:
    data = bytes(range(64)) * 4
    result = local_entropy(data, window=64, step=64)
    assert [offset for offset, _ in result] == [0, 64, 128, 192]
    for _, entropy in result:
        assert entropy == pytest.approx(math.log2(64))


def test_local_entropy_short_data_single_window() -> None:
    data = b"\x00\x01\x02\x03"
    assert local_entropy(data, window=64, step=16) == [(0, shannon_entropy(data))]


def test_local_entropy_empty_is_empty() -> None:
    assert local_entropy(b"", window=64, step=16) == []


def test_local_entropy_rejects_bad_parameters() -> None:
    with pytest.raises(ValueError):
        local_entropy(b"\x00", window=0, step=16)
    with pytest.raises(ValueError):
        local_entropy(b"\x00", window=64, step=0)


def test_byte_frequencies_shape_and_total() -> None:
    counts = byte_frequencies(b"\x00\x01\x01\xff")
    assert len(counts) == 256
    assert sum(counts) == 4
    assert counts[0] == 1
    assert counts[1] == 2
    assert counts[255] == 1
    assert counts[2] == 0


def test_printable_ratio() -> None:
    assert printable_ratio(b"ABC\x00") == pytest.approx(0.75)
    assert printable_ratio(b"\x00\xff") == 0.0
    assert printable_ratio(b"") == 0.0


def test_zero_ratio() -> None:
    assert zero_ratio(b"\x00\x01\x00") == pytest.approx(2 / 3)
    assert zero_ratio(b"\x01\x02") == 0.0
    assert zero_ratio(b"") == 0.0


def test_top_ngrams_counts_and_order() -> None:
    assert top_ngrams(b"ababab", 2, 3) == [(b"ab", 3), (b"ba", 2)]


def test_top_ngrams_tie_break_is_deterministic() -> None:
    assert top_ngrams(b"abba", 1, 2) == [(b"a", 2), (b"b", 2)]


def test_top_ngrams_too_short_input() -> None:
    assert top_ngrams(b"ab", 3, 5) == []


def test_autocorrelation_periodic_signal() -> None:
    data = b"\x01\x02\x03" * 10  # period 3
    values = autocorrelation(data, max_lag=5)
    assert values[2] == pytest.approx(1.0)  # lag 3


def test_autocorrelation_empty_or_single() -> None:
    assert autocorrelation(b"", 8) == []
    assert autocorrelation(b"\x00", 8) == []


def test_repeated_prefix_finds_header() -> None:
    data = b"ABCD" + b"\x00" * 8 + b"ABCD" + b"\xff" * 8
    assert repeated_prefix(data) == b"ABCD"


def test_repeated_prefix_no_repeat() -> None:
    assert repeated_prefix(b"\x00\x01\x02\x03") is None


def test_repeated_suffix_finds_trailer() -> None:
    data = b"TAIL" + b"\x00" * 3 + b"TAIL"
    assert repeated_suffix(data) == b"TAIL"


def test_repeated_suffix_no_repeat() -> None:
    assert repeated_suffix(b"\x00\x01\x02\x03") is None


def test_compute_features_is_deterministic() -> None:
    stream = load_raw(bytes(range(256)) * 2, source_id="s1")
    assert compute_features(stream) == compute_features(stream)


def test_compute_features_keys_and_values() -> None:
    stream = load_raw(b"\x00\x01\x02\x03\x04\x05", source_id="s1")
    features = compute_features(stream)
    assert features["source_id"] == "s1"
    assert features["size"] == 6
    assert features["global_entropy"] == pytest.approx(math.log2(6))
    assert len(features["byte_frequency"]) == 256
    assert features["zero_ratio"] == pytest.approx(1 / 6)
    assert features["printable_ratio"] == 0.0
    assert features["repeated_prefix"] is None
    assert features["repeated_suffix"] is None
    assert len(features["autocorrelation"]) == 6
    assert features["top_ngrams"][0] == {"ngram": "0001", "count": 1}
    assert features["local_entropy"] == [
        {"offset": 0, "entropy": pytest.approx(math.log2(6))}
    ]


def test_compute_features_local_entropy_offsets_are_absolute() -> None:
    stream = load_raw(b"\x00" * 64 + bytes(range(64)), source_id="s1")
    part = stream.slice(64, 128)
    features = compute_features(part)
    assert features["size"] == 64
    assert features["local_entropy"][0]["offset"] == 64


def test_compute_features_is_json_serializable() -> None:
    features = compute_features(load_raw(b"\x00\x01\x02\x03", source_id="s1"))
    json.dumps(features)
