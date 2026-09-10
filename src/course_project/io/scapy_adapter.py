"""PCAP/PCAPNG transport-payload extraction (Track D input adapter).

The project keeps Scapy as an optional richer adapter, while the packaged Sidecar
always carries the small BSD-licensed ``dpkt`` runtime parser. Both backends emit
the same project-native ``ExtractedPacket`` records; no third-party packet object
crosses this boundary.

See ``docs/design-v1.md`` section 5.1 and ``docs/architecture.md`` section 5.
"""

from __future__ import annotations

import io
import socket
from dataclasses import dataclass
from importlib.util import find_spec
from typing import Callable, Literal


@dataclass(frozen=True, slots=True)
class ExtractedPacket:
    """One transport-level payload extracted from a PCAP/PCAPNG capture."""

    index: int
    payload: bytes
    timestamp: float | None = None
    direction: str | None = None
    transport: str | None = None
    src: str | None = None
    dst: str | None = None


@dataclass(frozen=True, slots=True)
class PcapExtractionResult:
    status: Literal["ok", "unavailable", "failed"]
    error_category: str | None = None
    detail: str | None = None
    packets: tuple[ExtractedPacket, ...] = ()
    backend: str | None = None


def is_scapy_available() -> bool:
    """Whether the optional Scapy backend can be imported."""
    return find_spec("scapy") is not None


def is_dpkt_available() -> bool:
    """Whether the packaged-runtime dpkt backend can be imported."""
    return find_spec("dpkt") is not None


def extract_packets(data: bytes) -> PcapExtractionResult:
    """Parse a PCAP/PCAPNG capture into project-native transport packets.

    Scapy is preferred when explicitly installed. ``dpkt`` is the production
    fallback and is a core project dependency so the packaged desktop Sidecar can
    parse captures without a separate optional-extra installation. A parser error
    is never converted into an empty success.
    """
    backends: list[tuple[str, Callable[[bytes], list[ExtractedPacket]]]] = []
    if is_scapy_available():
        backends.append(("scapy", _read_packets_scapy))
    if is_dpkt_available():
        backends.append(("dpkt", _read_packets_dpkt))
    if not backends:
        return PcapExtractionResult(
            status="unavailable",
            error_category="dependency_unavailable",
            detail="no PCAP parser is installed; install the project runtime or the 'pcap' extra",
        )

    failures: list[str] = []
    for backend_name, reader in backends:
        try:
            packets = reader(data)
        except Exception as exc:  # noqa: BLE001 - normalize third-party parser failures
            failures.append(f"{backend_name}: {type(exc).__name__}: {exc}")
            continue
        return PcapExtractionResult(
            status="ok",
            packets=tuple(packets),
            backend=backend_name,
        )

    return PcapExtractionResult(
        status="failed",
        error_category="inference_failed",
        detail="; ".join(failures),
    )


def _read_packets_scapy(data: bytes) -> list[ExtractedPacket]:
    from scapy.layers.inet import IP, TCP, UDP
    from scapy.layers.inet6 import IPv6
    from scapy.packet import Raw
    from scapy.utils import PcapReader

    out: list[ExtractedPacket] = []
    for index, packet in enumerate(PcapReader(io.BytesIO(data))):
        ip = packet.getlayer(IP) or packet.getlayer(IPv6)
        transport: str | None = None
        sport: int | None = None
        dport: int | None = None
        if packet.haslayer(UDP):
            transport = "udp"
            sport, dport = packet[UDP].sport, packet[UDP].dport
        elif packet.haslayer(TCP):
            transport = "tcp"
            sport, dport = packet[TCP].sport, packet[TCP].dport
        payload = bytes(packet[Raw].load) if packet.haslayer(Raw) else b""
        src = dst = None
        if ip is not None:
            src = f"{ip.src}:{sport}" if sport is not None else ip.src
            dst = f"{ip.dst}:{dport}" if dport is not None else ip.dst
        timestamp = float(packet.time) if packet.time is not None else None
        out.append(
            ExtractedPacket(
                index=index,
                payload=payload,
                timestamp=timestamp,
                transport=transport,
                src=src,
                dst=dst,
            )
        )
    return out


def _read_packets_dpkt(data: bytes) -> list[ExtractedPacket]:
    import dpkt

    handle = io.BytesIO(data)
    reader = (
        dpkt.pcapng.Reader(handle)
        if data[:4] == b"\x0a\x0d\x0d\x0a"
        else dpkt.pcap.Reader(handle)
    )
    out: list[ExtractedPacket] = []
    for index, (timestamp, raw) in enumerate(reader):
        network: object | None = None
        try:
            ethernet = dpkt.ethernet.Ethernet(raw)
            if isinstance(ethernet.data, (dpkt.ip.IP, dpkt.ip6.IP6)):
                network = ethernet.data
        except (ValueError, dpkt.dpkt.NeedData, dpkt.dpkt.UnpackError):
            network = None

        if network is None and raw:
            version = raw[0] >> 4
            try:
                if version == 4:
                    network = dpkt.ip.IP(raw)
                elif version == 6:
                    network = dpkt.ip6.IP6(raw)
            except (ValueError, dpkt.dpkt.NeedData, dpkt.dpkt.UnpackError):
                network = None

        transport: str | None = None
        sport: int | None = None
        dport: int | None = None
        payload = b""
        src = dst = None
        if isinstance(network, (dpkt.ip.IP, dpkt.ip6.IP6)):
            layer4 = network.data
            family = socket.AF_INET if isinstance(network, dpkt.ip.IP) else socket.AF_INET6
            src_ip = socket.inet_ntop(family, network.src)
            dst_ip = socket.inet_ntop(family, network.dst)
            if isinstance(layer4, dpkt.udp.UDP):
                transport = "udp"
                sport, dport = layer4.sport, layer4.dport
                payload = bytes(layer4.data)
            elif isinstance(layer4, dpkt.tcp.TCP):
                transport = "tcp"
                sport, dport = layer4.sport, layer4.dport
                payload = bytes(layer4.data)
            src = f"{src_ip}:{sport}" if sport is not None else src_ip
            dst = f"{dst_ip}:{dport}" if dport is not None else dst_ip

        out.append(
            ExtractedPacket(
                index=index,
                payload=payload,
                timestamp=float(timestamp),
                transport=transport,
                src=src,
                dst=dst,
            )
        )
    return out
