"""Consumer-side end-to-end test for the frozen Track D -> Track C boundary.

This test plays the role of a downstream consumer: every ``isinstance``
assertion uses DTOs imported exclusively from ``course_project.models`` —
Track D internal dataclasses are never imported or asserted on here. A
controlled ``.dat`` file must flow end to end into the six frozen DTOs:
``InputMetadata``, ``MessageCandidate``, ``MessageFamily``,
``AlignmentResult``, ``FieldCandidate`` and ``BehaviorFeatures``.
"""

from __future__ import annotations

from pathlib import Path

from course_project.behavior import extract_behavior_features, from_packet_candidates
from course_project.boundary import detect_boundaries, to_message_candidates
from course_project.inference import family_analysis, infer_field_candidates
from course_project.io import input_metadata, load_dat
from course_project.models import (
    AlignmentResult,
    BehaviorFeatures,
    FieldCandidate,
    InputMetadata,
    MessageCandidate,
    MessageFamily,
    PacketCandidate,
)


def _make_message(msg_type: int, seq: int, payload: bytes) -> bytes:
    return (
        b"SYN1"
        + bytes([msg_type])
        + b"\x00\x00\x00"
        + bytes([seq])
        + (11 + len(payload)).to_bytes(2, "big")
        + payload
    )


def test_dat_to_frozen_dtos_full_chain(tmp_path: Path) -> None:
    capture = tmp_path / "controlled.dat"
    capture.write_bytes(b"".join(_make_message(0x01, i + 1, b"P" * 8) for i in range(3)))

    stream = load_dat(capture, source_id="controlled")

    meta = input_metadata(stream)
    assert isinstance(meta, InputMetadata)
    assert meta.kind == "dat"
    assert meta.size_bytes == capture.stat().st_size

    packets = detect_boundaries(stream)
    assert all(isinstance(p, PacketCandidate) for p in packets)

    messages = to_message_candidates(stream, packets, input_id=meta.input_id)
    assert all(isinstance(m, MessageCandidate) for m in messages)

    families, alignments = family_analysis(stream, packets, input_id=meta.input_id)
    assert all(isinstance(f, MessageFamily) for f in families)
    assert all(isinstance(a, AlignmentResult) for a in alignments)

    candidates = infer_field_candidates(stream, packets)
    assert all(isinstance(c, FieldCandidate) for c in candidates)

    flow_packets = from_packet_candidates(packets)
    behavior = extract_behavior_features(flow_packets, flow_id="controlled-flow")
    assert isinstance(behavior, BehaviorFeatures)
