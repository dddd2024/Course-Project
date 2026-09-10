from __future__ import annotations

import pytest

from course_project.boundary import detect_boundaries
from course_project.inference import (
    align_family,
    cluster_messages,
    message_similarity,
)
from course_project.inference.fields import infer_fields
from course_project.io import load_raw
from course_project.models import PacketCandidate


def make_message(msg_type: int, seq: int, payload: bytes) -> bytes:
    """magic(4) + type(1) + reserved(3) + seq(1) + total-length BE(2) + payload."""
    return (
        b"MSG!"
        + bytes([msg_type])
        + b"\x00\x00\x00"
        + bytes([seq])
        + (11 + len(payload)).to_bytes(2, "big")
        + payload
    )


def make_packets(messages: list[bytes]) -> tuple[bytes, list[PacketCandidate]]:
    data = b"".join(messages)
    packets = []
    offset = 0
    for message in messages:
        packets.append(PacketCandidate(offset, offset + len(message), 1.0))
        offset += len(message)
    return data, packets


def test_message_similarity() -> None:
    assert message_similarity(b"MSG!abcd", b"MSG!abcd") == 1.0
    assert message_similarity(b"MSG!abcd", b"MSG!xyzw") == 0.5
    assert message_similarity(b"AB", b"AC") == 0.5
    assert message_similarity(b"", b"anything") == 0.0


def test_cluster_messages_groups_families() -> None:
    messages = [
        make_message(0x01, 1, b"A" * 8),
        make_message(0x01, 2, b"C" * 16),
        make_message(0x02, 1, b"B" * 8),
        make_message(0x02, 2, b"D" * 16),
    ]
    assert cluster_messages(messages) == [0, 0, 1, 1]


def test_cluster_messages_rejects_bad_threshold() -> None:
    with pytest.raises(ValueError):
        cluster_messages([b"a"], threshold=1.5)


def test_align_family_regions() -> None:
    messages = [b"AB" + bytes([i % 3]) + bytes([i]) * 12 for i in range(10)]
    family = align_family(messages)
    assert family.message_count == 10
    assert family.min_length == 15
    assert family.max_length == 15
    assert not family.has_variable_tail
    kinds = [region.kind for region in family.regions]
    assert kinds[0] == "constant"
    assert kinds[1] == "constant"
    assert kinds[2] == "enum"
    assert all(kind == "variable" for kind in kinds[3:])


def test_align_family_variable_tail() -> None:
    family = align_family([b"AB\x01HELLO", b"AB\x01LONGMESSAGEHERE"])
    assert family.has_variable_tail
    assert family.min_length == 8
    assert family.max_length == 18


def test_align_family_empty_raises() -> None:
    with pytest.raises(ValueError):
        align_family([])


def test_infer_fields_families() -> None:
    messages = [
        make_message(0x01, 1, b"A" * 8),
        make_message(0x01, 2, b"C" * 16),
        make_message(0x02, 1, b"B" * 8),
        make_message(0x02, 2, b"D" * 16),
    ]
    data, packets = make_packets(messages)
    hypotheses = infer_fields(load_raw(data, source_id="s", format="dat"), packets)

    keys = [(h.semantic_type, h.offset) for h in hypotheses]
    assert ("magic", 0) in keys
    assert ("enum", 8) in keys
    assert ("sequence", 8) in keys
    assert ("payload", 11) in keys  # derived from the accepted length(total) field
    assert ("payload", 19) not in keys  # raw tail candidate is suppressed

    length_h = [h for h in hypotheses if h.semantic_type == "length"]
    assert any(
        h.offset == 9
        and h.size == 2
        and h.endian == "big"
        and h.evidence["match"] == "total"
        and h.confidence == pytest.approx(1.0)
        for h in length_h
    )

    # degenerate padded readings are filtered out
    assert not any(
        h.semantic_type == "sequence" and h.offset in (5, 7) for h in hypotheses
    )
    assert not any(h.semantic_type == "timestamp" for h in hypotheses)
    assert not any(
        h.semantic_type == "length" and h.size == 1 and h.endian == "little"
        for h in hypotheses
    )

    ids = [h.field_id for h in hypotheses]
    assert len(ids) == len(set(ids))

    magic_starts = {
        h.evidence["sample_offsets"][0]
        for h in hypotheses
        if h.semantic_type == "magic"
    }
    assert magic_starts == {0, 46}


def test_infer_fields_no_packets_is_empty() -> None:
    assert infer_fields(load_raw(b"whatever", source_id="s"), []) == []


def test_infer_fields_ignores_out_of_range_packets() -> None:
    data, _ = make_packets([make_message(0x01, 1, b"A" * 8)])
    stream = load_raw(data, source_id="s")
    bogus = [PacketCandidate(1000, 1010, 1.0)]
    assert infer_fields(stream, bogus) == []


def test_infer_fields_is_deterministic() -> None:
    messages = [make_message(0x01, i + 1, b"P" * 8) for i in range(3)]
    data, packets = make_packets(messages)
    stream = load_raw(data, source_id="s")
    assert infer_fields(stream, packets) == infer_fields(stream, packets)


def test_pipeline_boundary_then_inference() -> None:
    messages = [b"MSG!" + bytes([i]) * 16 for i in range(4)]
    stream = load_raw(b"".join(messages), source_id="s", format="dat")
    packets = detect_boundaries(stream)
    hypotheses = infer_fields(stream, packets)
    keys = [(h.semantic_type, h.offset) for h in hypotheses]
    assert ("magic", 0) in keys
    assert all(h.offset >= 0 for h in hypotheses)


def test_cross_family_enum_candidate() -> None:
    messages = [
        make_message(0x01, 1, b"A" * 8),
        make_message(0x01, 2, b"A" * 8),
        make_message(0x02, 1, b"A" * 8),
        make_message(0x02, 2, b"A" * 8),
    ]
    data, packets = make_packets(messages)
    hypotheses = infer_fields(load_raw(data, source_id="s"), packets)
    cross_enums = [
        h
        for h in hypotheses
        if h.semantic_type == "enum"
        and h.offset == 4
        and h.evidence.get("cross_family")
    ]
    assert len(cross_enums) == 1
    assert cross_enums[0].evidence["cardinality"] == 2
    assert cross_enums[0].evidence["families"] == [0, 1]
    assert cross_enums[0].evidence["support"] == 4


def test_cross_family_no_candidates_for_single_family() -> None:
    messages = [make_message(0x01, i + 1, b"P" * 8) for i in range(3)]
    data, packets = make_packets(messages)
    hypotheses = infer_fields(load_raw(data, source_id="s"), packets)
    assert not any(h.evidence.get("cross_family") for h in hypotheses)


def test_sequence_wrap_detection() -> None:
    messages = [make_message(0x01, seq, b"P" * 8) for seq in (254, 255, 0, 1, 2)]
    data, packets = make_packets(messages)
    hypotheses = infer_fields(load_raw(data, source_id="s", format="dat"), packets)
    seq = [
        h
        for h in hypotheses
        if h.semantic_type == "sequence" and h.offset == 8 and h.size == 1
    ]
    assert seq, "wrapped 8-bit sequence (254, 255, 0, 1, 2) should be detected"
    assert seq[0].evidence["step_support"] == pytest.approx(1.0)


def test_eight_byte_length_detection() -> None:
    def make_8byte(payload: bytes) -> bytes:
        return b"SYN8" + (12 + len(payload)).to_bytes(8, "big") + payload

    messages = [make_8byte(b"A" * (i + 1)) for i in range(5)]
    data, packets = make_packets(messages)
    hypotheses = infer_fields(load_raw(data, source_id="s", format="dat"), packets)
    assert any(
        h.semantic_type == "length"
        and h.size == 8
        and h.offset == 4
        and h.endian == "big"
        and h.evidence["match"] == "total"
        for h in hypotheses
    )
