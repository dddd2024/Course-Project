"""Canonical InputMetadata conversion for the public D->C boundary (Track D)."""

from __future__ import annotations

from course_project.io.containers import detect_container
from course_project.io.records import ByteStream
from course_project.models import InputKind, InputMetadata

_KIND_BY_FORMAT: dict[str, InputKind] = {
    "dat": "dat",
    "bin": "bin",
    "raw": "unknown",
}


def input_metadata(stream: ByteStream) -> InputMetadata:
    """Map a normalized ByteStream onto the frozen InputMetadata DTO.

    The real container kind is detected from magic bytes; the declared
    ``.dat/.bin`` format is kept in ``metadata["declared_format"]`` so a
    ``.dat`` that is actually a PCAP capture is surfaced as ``kind="pcap"``.
    """
    container = detect_container(stream.data)
    if container in ("pcap", "pcapng"):
        kind: InputKind = container
    else:
        kind = _KIND_BY_FORMAT.get(stream.format, "unknown")
    return InputMetadata(
        input_id=stream.source_id,
        kind=kind,
        size_bytes=stream.size,
        sha256=stream.sha256,
        direction_available=stream.direction is not None,
        timestamp_available=stream.timestamp is not None,
        metadata={
            "declared_format": stream.format,
            "container": container,
            "offset_base": stream.offset_base,
        },
    )
