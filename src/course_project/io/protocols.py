"""Known-protocol pre-identification for transport payloads (Track D, io layer).

Recognizes DTLS record structure so a known, encrypted protocol is surfaced as
such and the pipeline abstains from unknown-protocol field inference on it.
Recognition is structural (content type + version), never decryption.

See ``docs/design-v1.md`` sections 2 and 5.1.
"""

from __future__ import annotations

from dataclasses import dataclass

from course_project.io.scapy_adapter import ExtractedPacket

_DTLS_CONTENT_TYPES = (0x14, 0x15, 0x16, 0x17)
_DTLS_VERSIONS = (0xFEFD, 0xFEFF, 0xFEFE)


@dataclass(frozen=True, slots=True)
class DtlsRecord:
    """A parsed DTLS record header; the fragment is ciphertext and is NOT decrypted."""

    content_type: int
    version: int
    epoch: int
    sequence_number: int
    length: int
    fragment: bytes


def parse_dtls_record(data: bytes) -> DtlsRecord | None:
    """Parse a single DTLS record; return None when the header doesn't match.

    A DTLS record header is 13 bytes: content_type(1) version(2) epoch(2)
    sequence_number(6) length(2). Content type and version are checked; the
    fragment (``length`` bytes) is returned verbatim as ciphertext.
    """
    if len(data) < 13:
        return None
    content_type = data[0]
    version = int.from_bytes(data[1:3], "big")
    if content_type not in _DTLS_CONTENT_TYPES or version not in _DTLS_VERSIONS:
        return None
    epoch = int.from_bytes(data[3:5], "big")
    sequence_number = int.from_bytes(data[5:11], "big")
    length = int.from_bytes(data[11:13], "big")
    if 13 + length > len(data):
        return None  # truncated record
    return DtlsRecord(
        content_type=content_type,
        version=version,
        epoch=epoch,
        sequence_number=sequence_number,
        length=length,
        fragment=data[13 : 13 + length],
    )


def classify_transport(packets: list[ExtractedPacket]) -> str | None:
    """Return ``"dtls"`` when most UDP payloads parse as DTLS records, else None."""
    udp_payloads = [p.payload for p in packets if p.transport == "udp" and p.payload]
    if not udp_payloads:
        return None
    dtls_count = sum(1 for payload in udp_payloads if parse_dtls_record(payload) is not None)
    return "dtls" if dtls_count / len(udp_payloads) >= 0.5 else None
