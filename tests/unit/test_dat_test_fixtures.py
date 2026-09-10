from __future__ import annotations

from pathlib import Path

from course_project.inference import infer_field_candidates
from course_project.io import load_raw
from course_project.models import PacketCandidate


_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "test-data"
    / "dat"
    / "controlled-syn1.dat"
)


def _packets_from_declared_syn1_lengths(data: bytes) -> list[PacketCandidate]:
    packets: list[PacketCandidate] = []
    offset = 0
    while offset < len(data):
        assert data[offset : offset + 4] == b"SYN1"
        total_length = int.from_bytes(data[offset + 9 : offset + 11], "big")
        assert total_length >= 11
        packets.append(PacketCandidate(offset, offset + total_length, 1.0))
        offset += total_length
    assert offset == len(data)
    return packets


def test_controlled_syn1_fixture_disambiguates_total_length_width() -> None:
    data = _FIXTURE.read_bytes()
    assert len(data) == 861

    packets = _packets_from_declared_syn1_lengths(data)
    lengths = [packet.end_offset - packet.start_offset for packet in packets]

    assert lengths == [19, 311, 531]
    assert any(length > 255 for length in lengths)
    assert [data[packet.start_offset + 10] for packet in packets] == [19, 55, 19]

    stream = load_raw(data, source_id="controlled-syn1", format="dat")
    candidates = infer_field_candidates(stream, packets)
    total_length_candidates = [
        candidate
        for candidate in candidates
        if candidate.candidate_types == ("length",)
        and candidate.attributes.get("match") == "total"
    ]

    assert any(
        candidate.offset == 9
        and candidate.size == 2
        and candidate.endian == "big"
        and candidate.score == 1.0
        for candidate in total_length_candidates
    )
    assert not any(
        candidate.offset == 10 and candidate.size == 1
        for candidate in total_length_candidates
    )
