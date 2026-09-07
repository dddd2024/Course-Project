"""Deterministic ``.dat`` input normalization (Track D).

``load_dat`` / ``load_bin`` read a raw binary capture into a
:class:`ByteStream` without any protocol-semantic guessing. ``load_raw`` wraps
already-loaded bytes for the PCAP/transport-payload adapter that is added later.

See ``docs/design-v1.md`` section 5.1.
"""

from __future__ import annotations

from pathlib import Path

from course_project.io.records import ByteStream, InputFormat


class InputError(Exception):
    """Raised when raw input cannot be normalized into a ByteStream."""


def load_dat(path: str | Path, *, source_id: str | None = None) -> ByteStream:
    """Read a ``.dat`` capture as raw bytes into a deterministic ByteStream."""
    return _load_file(path, "dat", source_id)


def load_bin(path: str | Path, *, source_id: str | None = None) -> ByteStream:
    """Read a ``.bin`` capture as raw bytes into a deterministic ByteStream."""
    return _load_file(path, "bin", source_id)


def load_raw(
    data: bytes | bytearray | memoryview,
    *,
    source_id: str,
    format: InputFormat = "raw",
) -> ByteStream:
    """Wrap in-memory bytes into a ByteStream.

    Used by PCAP/transport-payload adapters so the rest of the pipeline only
    ever sees project-native records.
    """
    if isinstance(data, str):
        raise InputError("raw input must be bytes-like, not str")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise InputError(f"raw input must be bytes-like, got {type(data).__name__}")
    return ByteStream(source_id=source_id, data=bytes(data), format=format)


def _load_file(
    path: str | Path, format: InputFormat, source_id: str | None
) -> ByteStream:
    p = Path(path)
    if not p.exists():
        raise InputError(f"input file not found: {p}")
    if not p.is_file():
        raise InputError(f"input path is not a regular file: {p}")
    data = p.read_bytes()
    sid = source_id if source_id is not None else p.name
    return ByteStream(source_id=sid, data=data, format=format)
