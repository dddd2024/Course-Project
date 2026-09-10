from __future__ import annotations

import socket
import struct

import pytest

from course_project.io import scapy_adapter
from course_project.io.scapy_adapter import (
    PcapExtractionResult,
    extract_packets,
    is_dpkt_available,
    is_scapy_available,
)


def _dtls_pcap() -> bytes:
    """Build a tiny classic PCAP with one Ethernet/IPv4/UDP DTLS record."""
    payload = b"\x17\xfe\xfd\x00\x01" + b"\x00" * 6 + b"\x00\x04test"
    udp = struct.pack("!HHHH", 50000, 443, 8 + len(payload), 0) + payload
    src = socket.inet_aton("10.0.0.1")
    dst = socket.inet_aton("10.0.0.2")
    ipv4 = struct.pack(
        "!BBHHHBBH4s4s",
        0x45,
        0,
        20 + len(udp),
        0,
        0,
        64,
        17,
        0,
        src,
        dst,
    ) + udp
    ethernet = b"\x00" * 6 + b"\x01" * 6 + b"\x08\x00" + ipv4
    global_header = struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)
    packet_header = struct.pack("<IIII", 1, 0, len(ethernet), len(ethernet))
    return global_header + packet_header + ethernet


def _assert_dtls_packet(result: PcapExtractionResult) -> None:
    assert result.status == "ok"
    assert len(result.packets) == 1
    packet = result.packets[0]
    assert packet.index == 0
    assert packet.transport == "udp"
    assert packet.src == "10.0.0.1:50000"
    assert packet.dst == "10.0.0.2:443"
    assert packet.payload[:3] == b"\x17\xfe\xfd"
    assert packet.timestamp is not None


@pytest.mark.skipif(not is_scapy_available(), reason="scapy is not installed")
def test_extract_packets_live_scapy() -> None:
    result = extract_packets(_dtls_pcap())
    _assert_dtls_packet(result)
    assert result.backend == "scapy"


@pytest.mark.skipif(not is_dpkt_available(), reason="dpkt is not installed")
def test_extract_packets_packaged_dpkt_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scapy_adapter, "is_scapy_available", lambda: False)
    result = extract_packets(_dtls_pcap())
    _assert_dtls_packet(result)
    assert result.backend == "dpkt"


def test_extract_packets_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scapy_adapter, "is_scapy_available", lambda: False)
    monkeypatch.setattr(scapy_adapter, "is_dpkt_available", lambda: False)
    result = extract_packets(_dtls_pcap())
    assert result.status == "unavailable"
    assert result.error_category == "dependency_unavailable"
    assert result.packets == ()
