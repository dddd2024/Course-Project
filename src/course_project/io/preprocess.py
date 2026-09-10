"""Container-aware input preprocessing / inference gating (Track D, io layer).

Decides what downstream field inference should actually analyze: for PCAP
inputs the network layers are stripped and only transport payloads are kept,
so the generic field inference never blind-scans a whole container. A known
protocol hint (e.g. ``"dtls"``) signals that ciphertext must not be claimed as
recoverable plaintext.

See ``docs/design-v1.md`` section 5.1.
"""

from __future__ import annotations

from dataclasses import dataclass

from course_project.io.containers import detect_container
from course_project.io.protocols import classify_transport
from course_project.io.records import ByteStream
from course_project.io.scapy_adapter import ExtractedPacket, extract_packets
from course_project.models import InputKind


@dataclass(frozen=True, slots=True)
class PreprocessResult:
    """The gated, container-stripped input for downstream analysis."""

    container: InputKind
    protocol_hint: str | None
    stream: ByteStream  # bytes to analyze: raw data, or concatenated transport payloads
    packets: tuple[ExtractedPacket, ...] = ()
    error_category: str | None = None
    detail: str | None = None


def preprocess(stream: ByteStream) -> PreprocessResult:
    """Sniff the container, strip network layers for PCAP, classify the payload.

    Raw ``.dat/.bin`` inputs pass through unchanged. PCAP/PCAPNG inputs are
    parsed into transport payloads; the returned ``stream`` is those payloads
    concatenated (never the container), and ``protocol_hint`` records any known
    protocol (e.g. ``"dtls"``) so downstream can abstain accordingly.
    """
    container = detect_container(stream.data)
    if container in ("pcap", "pcapng"):
        result = extract_packets(stream.data)
        if result.status != "ok":
            return PreprocessResult(
                container=container,
                protocol_hint=None,
                stream=stream,
                error_category=result.error_category,
                detail=result.detail,
            )
        packets = result.packets
        payload = b"".join(p.payload for p in packets)
        return PreprocessResult(
            container=container,
            protocol_hint=classify_transport(list(packets)),
            stream=ByteStream(
                source_id=stream.source_id,
                data=payload,
                format="raw",
            ),
            packets=packets,
        )
    return PreprocessResult(container=container, protocol_hint=None, stream=stream)
