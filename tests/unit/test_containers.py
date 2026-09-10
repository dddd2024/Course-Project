from __future__ import annotations

from course_project.io import detect_container


def test_detect_container_pcapng() -> None:
    assert detect_container(b"\x0a\x0d\x0d\x0a" + b"\x00" * 20) == "pcapng"


def test_detect_container_pcap_endiannesses() -> None:
    magics = (b"\xd4\xc3\xb2\xa1", b"\xa1\xb2\xc3\xd4", b"\x4d\x3c\xb2\xa1", b"\xa1\xb2\x3c\x4d")
    for magic in magics:
        assert detect_container(magic + b"\x00" * 20) == "pcap"


def test_detect_container_unknown_and_short() -> None:
    assert detect_container(b"\x00" * 4) == "unknown"
    assert detect_container(b"") == "unknown"
    assert detect_container(b"\x0a\x0d") == "unknown"
