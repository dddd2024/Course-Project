from __future__ import annotations

from importlib.metadata import version

import pytest

from course_project.inference.netzob_adapter import (
    is_netzob_available,
    run_netzob_baseline,
)
from course_project.io import load_raw
from course_project.models import FieldCandidate, PacketCandidate

pytestmark = pytest.mark.skipif(
    not is_netzob_available(),
    reason="live Netzob smoke runs only in the isolated Netzob baseline workflow",
)


def _fixture() -> tuple[object, list[PacketCandidate]]:
    messages = [
        b"MSG!\x01PPPP",
        b"MSG!\x02PPPP",
        b"MSG!\x03PPPP",
    ]
    raw = b"".join(messages)
    packets: list[PacketCandidate] = []
    offset = 0
    for message in messages:
        packets.append(PacketCandidate(offset, offset + len(message), 1.0))
        offset += len(message)
    return load_raw(raw, source_id="netzob-live-smoke"), packets


def test_live_netzob_2_0_0_runs_through_project_native_adapter() -> None:
    assert version("Netzob") == "2.0.0"
    assert is_netzob_available() is True

    stream, packets = _fixture()
    first = run_netzob_baseline(stream, packets, min_support=2)
    second = run_netzob_baseline(stream, packets, min_support=2)

    assert first.status == "ok", first.detail
    assert first.error_category is None
    assert first.backend == "netzob"
    assert first.field_candidates
    assert first == second
    assert all(isinstance(candidate, FieldCandidate) for candidate in first.field_candidates)
    assert all(
        candidate.attributes.get("backend") == "netzob"
        for candidate in first.field_candidates
    )
    assert all(candidate.offset >= 0 for candidate in first.field_candidates)
