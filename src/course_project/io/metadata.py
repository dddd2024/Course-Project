"""Canonical InputMetadata conversion for the public D->C boundary (Track D)."""

from __future__ import annotations

from course_project.io.records import ByteStream
from course_project.models import InputKind, InputMetadata

_KIND_BY_FORMAT: dict[str, InputKind] = {
    "dat": "dat",
    "bin": "bin",
    "raw": "unknown",
}


def input_metadata(stream: ByteStream) -> InputMetadata:
    """Map a normalized ByteStream onto the frozen InputMetadata DTO."""
    return InputMetadata(
        input_id=stream.source_id,
        kind=_KIND_BY_FORMAT.get(stream.format, "unknown"),
        size_bytes=stream.size,
        sha256=stream.sha256,
        direction_available=stream.direction is not None,
        timestamp_available=stream.timestamp is not None,
        metadata={"format": stream.format, "offset_base": stream.offset_base},
    )
