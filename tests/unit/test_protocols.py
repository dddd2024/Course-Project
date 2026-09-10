from __future__ import annotations

from course_project.io.protocols import classify_transport, parse_dtls_record
from course_project.io.scapy_adapter import ExtractedPacket


def dtls_record(content_type: int = 0x17, version: int = 0xFEFD, fragment: bytes = b"\x00" * 8) -> bytes:
    header = (
        bytes([content_type])
        + version.to_bytes(2, "big")
        + b"\x00\x00"  # epoch
        + b"\x00" * 6  # sequence number
        + len(fragment).to_bytes(2, "big")
    )
    return header + fragment


def test_parse_dtls_record_valid() -> None:
    parsed = parse_dtls_record(dtls_record())
    assert parsed is not None
    assert parsed.content_type == 0x17
    assert parsed.version == 0xFEFD
    assert parsed.length == 8
    assert parsed.fragment == b"\x00" * 8


def test_parse_dtls_record_handshake() -> None:
    parsed = parse_dtls_record(dtls_record(content_type=0x16))
    assert parsed is not None and parsed.content_type == 0x16


def test_parse_dtls_record_rejects_bad_content_type() -> None:
    assert parse_dtls_record(dtls_record(content_type=0x01)) is None


def test_parse_dtls_record_rejects_tls_version() -> None:
    # 0x0303 is a TLS record version, not DTLS
    assert parse_dtls_record(dtls_record(version=0x0303)) is None


def test_parse_dtls_record_rejects_short_and_truncated() -> None:
    assert parse_dtls_record(b"\x17\xfe\xfd") is None
    assert parse_dtls_record(dtls_record()[:-1]) is None  # truncated fragment


def test_classify_transport_dtls_and_none() -> None:
    dtls = [
        ExtractedPacket(index=0, payload=dtls_record(), transport="udp"),
        ExtractedPacket(index=1, payload=dtls_record(content_type=0x16), transport="udp"),
    ]
    assert classify_transport(dtls) == "dtls"
    assert classify_transport([]) is None
    assert classify_transport([ExtractedPacket(index=0, payload=b"\x00" * 20, transport="udp")]) is None
