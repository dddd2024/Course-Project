from __future__ import annotations

import os
from pathlib import Path

import pytest

from course_project.inference import BinaryInfernoConfig, run_binaryinferno_baseline
from course_project.io import load_raw
from course_project.models import FieldCandidate, PacketCandidate


@pytest.mark.skipif(
    not os.environ.get("BINARYINFERNO_ROOT"),
    reason="BINARYINFERNO_ROOT is required for the isolated upstream smoke",
)
def test_pinned_upstream_binaryinferno_subprocess_is_deterministic() -> None:
    messages = [
        bytes.fromhex("01000D60A67AED054150504C45"),
        bytes.fromhex("01001160A67B0504504C554D0450454152"),
        bytes.fromhex("01000E60A67AF9064F52414E4745"),
    ]
    raw = b"".join(messages)
    packets: list[PacketCandidate] = []
    offset = 0
    for message in messages:
        packets.append(PacketCandidate(offset, offset + len(message), 1.0))
        offset += len(message)

    stream = load_raw(raw, source_id="binaryinferno-upstream-smoke")
    config = BinaryInfernoConfig(
        root=Path(os.environ["BINARYINFERNO_ROOT"]),
        detectors=("length", "length2BE"),
        timeout_seconds=180,
    )

    first = run_binaryinferno_baseline(stream, packets, config=config)
    second = run_binaryinferno_baseline(stream, packets, config=config)

    assert first.status == "ok", first.detail
    assert second.status == "ok", second.detail
    assert first == second
    assert first.field_candidates
    assert all(isinstance(candidate, FieldCandidate) for candidate in first.field_candidates)
    assert all(
        candidate.attributes["backend"] == "binaryinferno"
        for candidate in first.field_candidates
    )
    assert any("length" in candidate.candidate_types for candidate in first.field_candidates)
    assert all(
        candidate.attributes["verification_status"] == "not_verified"
        for candidate in first.field_candidates
    )
