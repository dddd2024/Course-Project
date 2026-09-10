from __future__ import annotations

import pytest

from course_project.behavior import (
    FlowPacket,
    extract_behavior_features,
    predict_behavior,
)
from course_project.boundary import detect_boundaries, to_message_candidates
from course_project.inference import (
    family_analysis,
    infer_field_candidates,
    refine_boundaries,
)
from course_project.io import input_metadata, load_raw
from course_project.models import (
    AlignmentResult,
    BehaviorFeatures,
    FieldCandidate,
    InputMetadata,
    MessageCandidate,
    MessageFamily,
    PacketCandidate,
)


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


def test_input_metadata_mapping() -> None:
    stream = load_raw(b"\x00" * 8, source_id="s1", format="dat")
    meta = input_metadata(stream)
    assert isinstance(meta, InputMetadata)
    assert meta.input_id == "s1"
    assert meta.kind == "dat"
    assert meta.size_bytes == 8
    assert meta.sha256 is not None and len(meta.sha256) == 64
    assert meta.direction_available is False
    assert meta.timestamp_available is False


def test_to_message_candidates_ids_and_families() -> None:
    stream = load_raw(b"\x00" * 20, source_id="s1", format="dat")
    packets = [PacketCandidate(0, 10, 0.9), PacketCandidate(10, 20, 0.8)]
    messages = to_message_candidates(
        stream, packets, family_ids=["family-0", "family-1"]
    )
    assert all(isinstance(m, MessageCandidate) for m in messages)
    assert [m.message_id for m in messages] == ["s1-m0", "s1-m1"]
    assert [m.family_id for m in messages] == ["family-0", "family-1"]
    assert messages[0].input_id == "s1"
    assert messages[0].confidence == pytest.approx(0.9)


def test_to_message_candidates_rejects_misaligned_families() -> None:
    stream = load_raw(b"\x00" * 20, source_id="s1")
    packets = [PacketCandidate(0, 10, 0.9)]
    with pytest.raises(ValueError):
        to_message_candidates(stream, packets, family_ids=["a", "b"])


def test_family_analysis_dtos() -> None:
    messages = [
        make_message(0x01, 1, b"A" * 8),
        make_message(0x01, 2, b"C" * 16),
        make_message(0x02, 1, b"B" * 8),
        make_message(0x02, 2, b"D" * 16),
    ]
    data = b"".join(messages)
    stream = load_raw(data, source_id="s1", format="dat")
    packets = []
    offset = 0
    for message in messages:
        packets.append(PacketCandidate(offset, offset + len(message), 1.0))
        offset += len(message)

    families, alignments = family_analysis(stream, packets)
    assert all(isinstance(f, MessageFamily) for f in families)
    assert all(isinstance(a, AlignmentResult) for a in alignments)
    assert len(families) == 2
    assert {f.family_id for f in families} == {"family-0", "family-1"}

    for alignment in alignments:
        kinds = [region.kind for region in alignment.regions]
        assert kinds[0] == "stable"  # magic+type+reserved prefix
        assert all(kind in ("stable", "variable") for kind in kinds)
        # message ids join with the boundary DTO scheme
        for message_id in alignment.message_ids:
            assert message_id.startswith("s1-m")

    # family ids join to the boundary DTO scheme
    messages_by_family = {f.family_id: f.message_ids for f in families}
    assert all(
        ids in messages_by_family["family-0"] + messages_by_family["family-1"]
        for ids in ("s1-m0", "s1-m1", "s1-m2", "s1-m3")
    )


def test_infer_field_candidates_dtos() -> None:
    messages = [make_message(0x01, i + 1, b"P" * 8) for i in range(3)]
    data = b"".join(messages)
    stream = load_raw(data, source_id="s1", format="dat")
    packets = []
    offset = 0
    for message in messages:
        packets.append(PacketCandidate(offset, offset + len(message), 1.0))
        offset += len(message)

    candidates = infer_field_candidates(stream, packets)
    assert all(isinstance(c, FieldCandidate) for c in candidates)
    assert any(
        c.candidate_types == ("magic",) and c.offset == 0 for c in candidates
    )
    assert any(
        c.candidate_types == ("length",)
        and c.offset == 9
        and c.size == 2
        and c.endian == "big"
        for c in candidates
    )
    assert all(c.family_id == "family-0" for c in candidates)


def test_behavior_features_dto() -> None:
    packets = [FlowPacket(32, "up" if i % 2 == 0 else "down") for i in range(6)]
    features = extract_behavior_features(packets, flow_id="f1")
    assert isinstance(features, BehaviorFeatures)
    assert features.flow_id == "f1"
    assert features.values["packet_count"] == 6
    assert features.sample_ids == tuple(f"f1-p{i}" for i in range(6))
    # frozen DTO only carries scalar values
    assert all(
        isinstance(v, (int, float, str, bool)) or v is None
        for v in features.values.values()
    )

    prediction = predict_behavior(packets, flow_id="f1")
    assert prediction.label == "HEARTBEAT"


def test_boundary_and_inference_chain_join() -> None:
    messages = [make_message(0x01, i + 1, b"P" * 8) for i in range(3)]
    stream = load_raw(b"".join(messages), source_id="s1", format="dat")
    packets = detect_boundaries(stream)
    meta = input_metadata(stream)
    messages_dto = to_message_candidates(stream, packets, input_id=meta.input_id)
    families, _ = family_analysis(stream, packets, input_id=meta.input_id)
    assert {m.message_id for m in messages_dto} == {
        id_ for f in families for id_ in f.message_ids
    }


def test_refine_boundaries_annotates_and_preserves_positions() -> None:
    messages = [make_message(0x01, i + 1, b"P" * 8) for i in range(6)]
    stream = load_raw(b"".join(messages), source_id="s", format="dat")
    packets = detect_boundaries(stream)
    refined = refine_boundaries(stream, packets)

    # positions and order are never changed
    assert [r.start_offset for r in refined] == [p.start_offset for p in packets]
    assert [r.end_offset for r in refined] == [p.end_offset for p in packets]

    # alignment evidence + family id are attached, confidence stays in range
    for r in refined:
        assert "alignment_gain" in r.evidence
        assert "family_id" in r.evidence
        assert 0.0 <= r.confidence <= 1.0

    # clean, well-aligned families keep high confidence
    assert all(r.confidence >= 0.5 for r in refined)
    assert len({r.evidence["family_id"] for r in refined}) == 1


def test_refine_boundaries_is_deterministic() -> None:
    messages = [make_message(0x01, i + 1, b"P" * 8) for i in range(6)]
    stream = load_raw(b"".join(messages), source_id="s", format="dat")
    packets = detect_boundaries(stream)
    assert refine_boundaries(stream, packets) == refine_boundaries(stream, packets)


def test_refine_boundaries_rejects_bad_blend() -> None:
    stream = load_raw(b"\x00" * 8, source_id="s")
    with pytest.raises(ValueError):
        refine_boundaries(stream, [], blend=1.5)
