"""PCAP/PCAPNG transport-payload extraction via Scapy (Track D, optional).

Scapy is optional: it is imported lazily only when a capture needs parsing.
When missing, callers get an explicit ``dependency_unavailable`` result
(fail-closed), matching the Netzob/BinaryInferno adapters and
``docs/open-source-stack.md``. Scapy objects never cross this boundary — the
adapter emits project-native ``ExtractedPacket`` records.

See ``docs/design-v1.md`` section 5.1 and ``docs/architecture.md`` section 5.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from importlib.util import find_spec
from typing import Literal


@dataclass(frozen=True, slots=True)
class ExtractedPacket:
    """One transport-level payload extracted from a PCAP/PCAPNG capture."""

    index: int  # 0-based ordinal in the capture
    payload: bytes  # transport payload (UDP/TCP data)
    timestamp: float | None = None
    direction: str | None = None  # None until a flow baseline is established
    transport: str | None = None  # "udp" / "tcp" / None
    src: str | None = None  # "ip:port"
    dst: str | None = None


@dataclass(frozen=True, slots=True)
class PcapExtractionResult:
    status: Literal["ok", "unavailable", "failed"]
    error_category: str | None = None
    detail: str | None = None
    packets: tuple[ExtractedPacket, ...] = ()


def is_scapy_available() -> bool:
    """Whether the optional Scapy dependency can be imported."""
    return find_spec("scapy") is not None


def extract_packets(data: bytes) -> PcapExtractionResult:
    """Parse a PCAP/PCAPNG capture into project-native transport packets.

    Missing dependency -> ``status="unavailable"`` with error category
    ``dependency_unavailable``; a failing parse -> ``status="failed"`` with the
    original error text. Failures are never converted into empty successes.
    """
    if not is_scapy_available():
        return PcapExtractionResult(
            status="unavailable",
            error_category="dependency_unavailable",
            detail="scapy is not installed; install the 'pcap' extra to parse captures",
        )
    try:
        packets = _read_packets(data)
    except Exception as exc:  # noqa: BLE001 — surface any upstream failure loudly
        return PcapExtractionResult(
            status="failed",
            error_category="inference_failed",
            detail=f"{type(exc).__name__}: {exc}",
        )
    return PcapExtractionResult(status="ok", packets=tuple(packets))


def _read_packets(data: bytes) -> list[ExtractedPacket]:
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
