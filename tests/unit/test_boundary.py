from __future__ import annotations

import pytest

from course_project.boundary import (
    detect_boundaries,
    entropy_transition_score,
    field_stability_score,
    generate_candidate_positions,
    length_consistency_score,
    prefix_repeat_score,
)
from course_project.io import ByteStream, load_raw

MESSAGE = b"MSG!" + bytes.fromhex("8f3a11d7c0459e622bf805a371cc489d")
UNSTRUCTURED = bytes.fromhex("c5d71484f8cf9bf4b76f47904730804b9e3225a9")


def test_prefix_repeat_score_match_and_mismatch() -> None:
    data = MESSAGE * 3
    assert prefix_repeat_score(data, 20, b"MSG!") == 1.0
    assert prefix_repeat_score(data, 21, b"MSG!") == 0.0


def test_prefix_repeat_score_without_prefix_is_neutral() -> None:
    assert prefix_repeat_score(b"abc", 1, None) == 0.5


def test_prefix_repeat_score_near_end_is_neutral() -> None:
    assert prefix_repeat_score(b"ABCD", 2, b"ABCD") == 0.5


def test_length_consistency_equal_gaps() -> None:
    boundaries = [0, 10, 20, 30]
    assert length_consistency_score(boundaries, 1) == 1.0
    assert length_consistency_score(boundaries, 2) == 1.0


def test_length_consistency_single_gap_is_neutral() -> None:
    assert length_consistency_score([0, 10], 0) == 0.5


def test_length_consistency_deviation_lowers_score() -> None:
    boundaries = [0, 10, 20, 25, 35]
    assert length_consistency_score(boundaries, 1) == pytest.approx(1.0)
    assert length_consistency_score(boundaries, 2) == pytest.approx(0.5)


def test_entropy_transition_drop_scores_high() -> None:
    noisy = bytes.fromhex("8f3a11d7c0459e622bf805a371cc489d")
    data = noisy * 4 + b"\x00" * 64
    score = entropy_transition_score(data, len(data) - 64, window=32)
    assert score > 0.9


def test_entropy_transition_flat_is_neutral() -> None:
    assert entropy_transition_score(b"\x00" * 64, 32, window=16) == pytest.approx(0.5)


def test_entropy_transition_rejects_bad_window() -> None:
    with pytest.raises(ValueError):
        entropy_transition_score(b"\x00" * 8, 4, window=0)


def test_field_stability_matching_headers() -> None:
    score = field_stability_score(MESSAGE * 3, [0, 20, 40, 60], 1, header_len=4)
    assert score == pytest.approx(1.0)


def test_field_stability_mismatching_headers_low() -> None:
    data = b"MSG!" + b"\x00" * 16 + b"xxxx" + b"\x00" * 16
    score = field_stability_score(data, [0, 20, 40], 1, header_len=4)
    assert score < 0.5


def test_field_stability_no_others_is_neutral() -> None:
    assert field_stability_score(b"abc", [0, 3], 0, header_len=4) == pytest.approx(0.5)


def test_generate_candidates_from_repeated_prefix() -> None:
    positions = generate_candidate_positions(MESSAGE * 4, prefix_max_len=4)
    assert 20 in positions
    assert 40 in positions
    assert 60 in positions


def test_generate_candidates_unstructured_is_empty() -> None:
    assert generate_candidate_positions(UNSTRUCTURED) == []


def test_detect_boundaries_structured_stream() -> None:
    stream = load_raw(MESSAGE * 4, source_id="s", format="dat")
    candidates = detect_boundaries(stream)
    starts = [candidate.start_offset for candidate in candidates]
    assert starts == [0, 20, 40, 60]
    assert all(candidate.end_offset - candidate.start_offset == 20 for candidate in candidates)
    assert all(candidate.confidence > 0.5 for candidate in candidates)
    for candidate in candidates:
        assert "start_boundary" in candidate.evidence
        assert "end_boundary" in candidate.evidence
        assert candidate.evidence["length"] == 20


def test_detect_boundaries_empty_stream() -> None:
    assert detect_boundaries(load_raw(b"", source_id="e")) == []


def test_detect_boundaries_unstructured_stream_single_candidate() -> None:
    candidates = detect_boundaries(load_raw(UNSTRUCTURED, source_id="u"))
    assert len(candidates) == 1
    assert candidates[0].start_offset == 0
    assert candidates[0].end_offset == len(UNSTRUCTURED)


def test_detect_boundaries_rebases_offsets() -> None:
    base = load_raw(b"\x00" * 8 + MESSAGE * 4, source_id="s", format="dat")
    part = base.slice(8, 88)
    starts = [candidate.start_offset for candidate in detect_boundaries(part)]
    assert starts == [8, 28, 48, 68]


def test_detect_boundaries_propagates_metadata() -> None:
    stream = ByteStream(
        source_id="s", data=MESSAGE * 2, direction="c2s", timestamp=1.5
    )
    candidates = detect_boundaries(stream)
    assert all(candidate.direction == "c2s" for candidate in candidates)
    assert all(candidate.timestamp == 1.5 for candidate in candidates)


def test_detect_boundaries_rejects_bad_weights() -> None:
    stream = load_raw(b"abc", source_id="s")
    with pytest.raises(ValueError):
        detect_boundaries(stream, weights={"prefix": 0.3})
    with pytest.raises(ValueError):
        detect_boundaries(stream, weights={"prefix": 0.5, "length": 0.5, "nope": 0.0})


def test_detect_boundaries_is_deterministic() -> None:
    stream = load_raw(MESSAGE * 4, source_id="s")
    assert detect_boundaries(stream) == detect_boundaries(stream)
