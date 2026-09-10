from __future__ import annotations

import os
import tempfile

import pytest

from course_project.io.scapy_adapter import (
    extract_packets,
    is_scapy_available,
)


def _dtls_pcap() -> bytes:
    """Build a tiny PCAP with one UDP packet carrying a DTLS application record."""
    from scapy.all import IP, UDP, Ether, Raw, wrpcap

    packet = (
        Ether()
        / IP(src="10.0.0.1", dst="10.0.0.2")
        / UDP(sport=50000, dport=443)
        / Raw(load=b"\x17\xfe\xfd\x00\x00\x00\x00" + b"\x00" * 16)
    )
    fd, path = tempfile.mkstemp(suffix=".pcap")
    os.close(fd)
    try:
        wrpcap(path, [packet])
        with open(path, "rb") as fh:
            return fh.read()
    finally:
        os.unlink(path)


@pytest.mark.skipif(not is_scapy_available(), reason="scapy is not installed")
def test_extract_packets_live() -> None:
    result = extract_packets(_dtls_pcap())
    assert result.status == "ok"
    assert len(result.packets) == 1

    packet = result.packets[0]
    assert packet.index == 0
    assert packet.transport == "udp"
    assert packet.src == "10.0.0.1:50000"
    assert packet.dst == "10.0.0.2:443"
    assert packet.payload[:2] == b"\x17\xfe"  # DTLS application-data record head
    assert packet.timestamp is not None


@pytest.mark.skipif(
    is_scapy_available(), reason="scapy is installed; fallback path not exercised"
)
def test_extract_packets_unavailable() -> None:
    result = extract_packets(b"\xd4\xc3\xb2\xa1" + b"\x00" * 40)
    assert result.status == "unavailable"
    assert result.error_category == "dependency_unavailable"
    assert result.packets == ()
