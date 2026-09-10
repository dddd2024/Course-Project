from course_project.inference.fields import infer_fields
from course_project.io import load_raw
from course_project.models import PacketCandidate


def _make_message(seq: int, payload: bytes) -> bytes:
    return (
        b"SYN1"
        + b"\x01"
        + b"\x00\x00\x00"
        + bytes([seq])
        + (11 + len(payload)).to_bytes(2, "big")
        + payload
    )


def _make_packets(messages: list[bytes]) -> tuple[bytes, list[PacketCandidate]]:
    data = b"".join(messages)
    packets: list[PacketCandidate] = []
    offset = 0
    for message in messages:
        packets.append(PacketCandidate(offset, offset + len(message), 1.0))
        offset += len(message)
    return data, packets


def test_two_byte_total_length_disambiguates_low_byte() -> None:
    messages = [
        _make_message(1, b"A" * 8),
        _make_message(2, b"B" * 300),
        _make_message(3, b"C" * 520),
    ]
    data, packets = _make_packets(messages)
    assert [len(message) for message in messages] == [19, 311, 531]
    assert [message[10] for message in messages] == [19, 55, 19]

    hypotheses = infer_fields(load_raw(data, source_id="syn1-width", format="dat"), packets)
    total_length = [
        hypothesis
        for hypothesis in hypotheses
        if hypothesis.semantic_type == "length"
        and hypothesis.evidence.get("match") == "total"
    ]
    assert any(
        hypothesis.offset == 9
        and hypothesis.size == 2
        and hypothesis.endian == "big"
        and hypothesis.confidence == 1.0
        for hypothesis in total_length
    )
    assert not any(
        hypothesis.offset == 10 and hypothesis.size == 1
        for hypothesis in total_length
    )
