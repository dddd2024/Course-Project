from __future__ import annotations

import os
import tempfile

import pytest

from course_project.io import load_raw, preprocess
from course_project.io.scapy_adapter import is_scapy_available


def _dtls_pcap() -> bytes:
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


def test_preprocess_raw_passthrough() -> None:
    stream = load_raw(b"\x00" * 20, source_id="s", format="dat")
    result = preprocess(stream)
    assert result.container == "unknown"
    assert result.protocol_hint is None
    assert result.stream.data == b"\x00" * 20
    assert result.packets == ()
    assert result.error_category is None


@pytest.mark.skipif(not is_scapy_available(), reason="scapy is not installed")
def test_preprocess_pcap_strips_network_layers() -> None:
    pcap = _dtls_pcap()
    stream = load_raw(pcap, source_id="s", format="dat")
    result = preprocess(stream)
    assert result.container == "pcap"
    assert result.protocol_hint == "dtls"
    # the analyzed stream is the transport payload, not the PCAP container
    assert len(result.stream.data) < len(pcap)
    assert result.stream.data[:2] == b"\x17\xfe"
    assert len(result.packets) == 1
