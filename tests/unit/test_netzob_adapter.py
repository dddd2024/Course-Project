from __future__ import annotations

import pytest

from course_project.inference.netzob_adapter import (
    convert_field_segments,
    is_netzob_available,
    run_netzob_baseline,
)
from course_project.io import load_raw
from course_project.models import PacketCandidate


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
    assert result.field_hypotheses == ()


def test_convert_field_segments_basic() -> None:
    messages = [b"MSG!" + bytes([i]) + b"P" * 4 for i in range(3)]
    packets = [PacketCandidate(i * 9, i * 9 + 9, 1.0) for i in range(3)]
    rows = [[m[:4], m[4:5], m[5:]] for m in messages]
    hypotheses = convert_field_segments(messages, packets, rows, backend="netzob")

    by_field = {h.evidence["field_index"]: h for h in hypotheses}
    assert set(by_field) == {0, 1, 2}

    magic = by_field[0]
    assert magic.semantic_type == "magic"
    assert magic.offset == 0
    assert magic.size == 4
    assert magic.evidence["value"] == "4d534721"
    assert magic.evidence["support"] == 3
    assert magic.evidence["sample_offsets"] == [0, 9, 18]

    enum = by_field[1]
    assert enum.semantic_type == "enum"
    assert enum.offset == 4
    assert enum.evidence["cardinality"] == 3

    constant = by_field[2]
    assert constant.semantic_type == "constant"
    assert constant.offset == 5
    assert constant.evidence["value"] == "50505050"

    assert all(h.evidence["backend"] == "netzob" for h in hypotheses)


def test_convert_field_segments_min_support() -> None:
    messages = [b"AB", b"AB", b"AB"]
    packets = [PacketCandidate(0, 2, 1.0), PacketCandidate(2, 4, 1.0), PacketCandidate(4, 6, 1.0)]
    rows = [[b"A", b"B"], [b"A"], [b"A", b"B"]]
    hypotheses = convert_field_segments(messages, packets, rows, min_support=3)
    assert [h.evidence["field_index"] for h in hypotheses] == [0]
    assert hypotheses[0].evidence["support"] == 3


def test_convert_field_segments_variable_size() -> None:
    messages = [b"ABXX", b"ABYYY"]
    packets = [PacketCandidate(0, 4, 1.0), PacketCandidate(4, 9, 1.0)]
    rows = [[b"AB", b"XX"], [b"AB", b"YYY"]]
    hypotheses = convert_field_segments(messages, packets, rows)
    field1 = next(h for h in hypotheses if h.evidence["field_index"] == 1)
    assert field1.semantic_type == "unknown"
    assert field1.size is None
    assert field1.evidence["variable_sizes"] == [2, 3]
    assert field1.evidence["starts_consistent"] is True


def test_convert_field_segments_coerces_cell_types() -> None:
    messages = [b"AB", b"AB"]
    packets = [PacketCandidate(0, 2, 1.0), PacketCandidate(2, 4, 1.0)]
    rows = [[bytearray(b"A"), b"B"], [b"A", memoryview(b"B")]]
    hypotheses = convert_field_segments(messages, packets, rows)
    assert hypotheses[0].semantic_type == "magic"
    assert hypotheses[1].evidence["value"] == "42"


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
