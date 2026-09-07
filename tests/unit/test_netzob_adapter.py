from __future__ import annotations

import pytest

from course_project.inference.netzob_adapter import (
    convert_field_segments,
    is_netzob_available,
    run_netzob_baseline,
)
from course_project.io import load_raw
from course_project.models import FieldCandidate, PacketCandidate


@pytest.mark.skipif(
    is_netzob_available(), reason="netzob is installed; fallback path not exercised"
)
def test_run_netzob_baseline_unavailable_fallback() -> None:
    stream = load_raw(b"\x00" * 8, source_id="s")
    packets = [PacketCandidate(0, 8, 1.0)]
    result = run_netzob_baseline(stream, packets)
    assert result.backend == "netzob"
    assert result.status == "unavailable"
    assert result.error_category == "dependency_unavailable"
    assert result.field_candidates == ()


def test_convert_field_segments_basic() -> None:
    messages = [b"MSG!" + bytes([i]) + b"P" * 4 for i in range(3)]
    packets = [PacketCandidate(i * 9, i * 9 + 9, 1.0) for i in range(3)]
    rows = [[m[:4], m[4:5], m[5:]] for m in messages]
    candidates = convert_field_segments(messages, packets, rows, backend="netzob")

    assert all(isinstance(c, FieldCandidate) for c in candidates)
    by_field = {c.attributes["field_index"]: c for c in candidates}
    assert set(by_field) == {0, 1, 2}

    magic = by_field[0]
    assert magic.candidate_types == ("magic",)
    assert magic.offset == 0
    assert magic.size == 4
    assert magic.attributes["value"] == "4d534721"
    assert magic.attributes["support"] == 3
    assert magic.attributes["sample_offsets"] == [0, 9, 18]

    enum = by_field[1]
    assert enum.candidate_types == ("enum",)
    assert enum.offset == 4
    assert enum.attributes["cardinality"] == 3

    constant = by_field[2]
    assert constant.candidate_types == ("constant",)
    assert constant.offset == 5
    assert constant.attributes["value"] == "50505050"

    assert all(c.attributes["backend"] == "netzob" for c in candidates)


def test_convert_field_segments_min_support() -> None:
    messages = [b"AB", b"AB", b"AB"]
    packets = [
        PacketCandidate(0, 2, 1.0),
        PacketCandidate(2, 4, 1.0),
        PacketCandidate(4, 6, 1.0),
    ]
    rows = [[b"A", b"B"], [b"A"], [b"A", b"B"]]
    candidates = convert_field_segments(messages, packets, rows, min_support=3)
    assert [c.attributes["field_index"] for c in candidates] == [0]
    assert candidates[0].attributes["support"] == 3


def test_convert_field_segments_variable_size() -> None:
    messages = [b"ABXX", b"ABYYY"]
    packets = [PacketCandidate(0, 4, 1.0), PacketCandidate(4, 9, 1.0)]
    rows = [[b"AB", b"XX"], [b"AB", b"YYY"]]
    candidates = convert_field_segments(messages, packets, rows)
    field1 = next(c for c in candidates if c.attributes["field_index"] == 1)
    assert field1.candidate_types == ("unknown",)
    assert field1.size is None
    assert field1.attributes["variable_sizes"] == [2, 3]
    assert field1.attributes["starts_consistent"] is True


def test_convert_field_segments_coerces_cell_types() -> None:
    messages = [b"AB", b"AB"]
    packets = [PacketCandidate(0, 2, 1.0), PacketCandidate(2, 4, 1.0)]
    rows = [[bytearray(b"A"), b"B"], [b"A", memoryview(b"B")]]
    candidates = convert_field_segments(messages, packets, rows)
    assert candidates[0].candidate_types == ("magic",)
    assert candidates[1].attributes["value"] == "42"


def test_convert_field_segments_rejects_length_mismatch() -> None:
    with pytest.raises(ValueError):
        convert_field_segments(
            [b"AB"], [PacketCandidate(0, 2, 1.0)], [[b"A"], [b"A"]]
        )


def test_convert_field_segments_rejects_bad_min_support() -> None:
    with pytest.raises(ValueError):
        convert_field_segments([], [], [], min_support=0)


def test_convert_field_segments_is_deterministic() -> None:
    messages = [b"MSG!" + bytes([i]) + b"P" * 4 for i in range(3)]
    packets = [PacketCandidate(i * 9, i * 9 + 9, 1.0) for i in range(3)]
    rows = [[m[:4], m[4:5], m[5:]] for m in messages]
    first = convert_field_segments(messages, packets, rows)
    second = convert_field_segments(messages, packets, rows)
    assert first == second
