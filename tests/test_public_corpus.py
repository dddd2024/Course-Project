from __future__ import annotations

import hashlib
from pathlib import Path

import dpkt
import pytest

from course_project.experiments import public_corpus


def _udp_frame(src: bytes, dst: bytes, sport: int, dport: int, payload: bytes) -> bytes:
    udp = dpkt.udp.UDP(sport=sport, dport=dport, data=payload)
    udp.ulen = len(udp)
    ip = dpkt.ip.IP(src=src, dst=dst, p=dpkt.ip.IP_PROTO_UDP, data=udp)
    ip.len = len(ip)
    return bytes(
        dpkt.ethernet.Ethernet(
            src=b"\x00\x01\x02\x03\x04\x05",
            dst=b"\x06\x07\x08\x09\x0a\x0b",
            type=dpkt.ethernet.ETH_TYPE_IP,
            data=ip,
        )
    )


def test_materializer_checks_hash_before_persisting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    good_pcap = b"pcap"
    good_result = b"result"
    spec = public_corpus.PublicCapture(
        "fixture.pcap",
        hashlib.sha256(good_pcap).hexdigest(),
        len(good_pcap),
        hashlib.sha256(good_result).hexdigest(),
        len(good_result),
        "behavior",
        "QUERY",
        "train",
    )
    monkeypatch.setattr(public_corpus, "PUBLIC_CAPTURES", (spec,))

    with pytest.raises(ValueError, match="integrity mismatch"):
        public_corpus.materialize_public_corpus(tmp_path, fetch=lambda _url: b"wrong")

    assert not (tmp_path / "tests" / "pcaps" / spec.name).exists()


def test_pcap_flow_extraction_preserves_direction_size_and_payload(tmp_path: Path) -> None:
    path = tmp_path / "tiny.pcap"
    client = b"\x0a\x00\x00\x01"
    server = b"\x0a\x00\x00\x02"
    with path.open("wb") as handle:
        writer = dpkt.pcap.Writer(handle)
        first = _udp_frame(client, server, 53000, 53, b"query")
        second = _udp_frame(server, client, 53, 53000, b"answer")
        writer.writepkt(first, ts=1.0)
        writer.writepkt(second, ts=1.25)

    flows = public_corpus._read_flows(path)

    assert len(flows) == 1
    assert [item.direction for item in flows[0].packets] == ["up", "down"]
    assert [item.timestamp for item in flows[0].packets] == [1.0, 1.25]
    assert flows[0].frame_bytes == len(first) + len(second)
    assert flows[0].payload_chunks == [b"query", b"answer"]


def test_upstream_mapping_is_explicit_and_rejects_unknown_categories() -> None:
    assert public_corpus._label_from_upstream(
        {"application_name": "TLS.DoH_DoT", "application_category_name": "Network"}
    ) == "QUERY"
    assert public_corpus._label_from_upstream(
        {"application_name": "QUIC.YouTubeUpload", "application_category_name": "Media"}
    ) == "UPLOAD"
    with pytest.raises(ValueError, match="no declared project behavior mapping"):
        public_corpus._label_from_upstream(
            {"application_name": "Unknown", "application_category_name": "Unspecified"}
        )


def test_modbus_recognition_and_restoration_use_structural_invariants() -> None:
    request = bytes.fromhex("000100000006010300000001")
    response = bytes.fromhex("00010000000501030241c8")

    result = public_corpus._recognize_modbus_tcp((request, response))

    assert result["detectedProtocol"] == "Modbus/TCP"
    assert result["confidence"] == 1.0
    assert result["readHoldingRegisterRequests"] == 1
    assert result["readHoldingRegisterResponses"] == 1
    assert result["restoredRegisterValueCount"] == 1


def test_exact_boundary_f1_reports_partial_recovery() -> None:
    assert public_corpus._boundary_f1({10, 20}, {10, 30}) == 0.5
    assert public_corpus._boundary_f1(set(), set()) == 1.0
