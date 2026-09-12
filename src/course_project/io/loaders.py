"""Deterministic raw-file normalization for Track D.

``load_dat`` / ``load_bin`` can read either the complete file or a bounded
prefix.  The bounded mode keeps large unknown captures from being materialized
in memory before protocol inference starts.
"""

from __future__ import annotations

from pathlib import Path

from course_project.io.records import ByteStream, InputFormat


class InputError(Exception):
    """Raised when raw input cannot be normalized into a ByteStream."""


def load_dat(
    path: str | Path,
    *,
    source_id: str | None = None,
    max_bytes: int | None = None,
) -> ByteStream:
    """Read a ``.dat`` capture, optionally limiting it to a prefix."""
    return _load_file(path, "dat", source_id, max_bytes=max_bytes)


def load_bin(
    path: str | Path,
    *,
    source_id: str | None = None,
    max_bytes: int | None = None,
) -> ByteStream:
    """Read a ``.bin`` capture, optionally limiting it to a prefix."""
    return _load_file(path, "bin", source_id, max_bytes=max_bytes)


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
    path: str | Path,
    format: InputFormat,
    source_id: str | None,
    *,
    max_bytes: int | None,
) -> ByteStream:
    p = Path(path)
    if not p.exists():
        raise InputError(f"input file not found: {p}")
    if not p.is_file():
        raise InputError(f"input path is not a regular file: {p}")
    if max_bytes is not None and (
        not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1
    ):
        raise InputError("max_bytes must be a positive integer or None")
    with p.open("rb") as handle:
        data = handle.read() if max_bytes is None else handle.read(max_bytes)
    sid = source_id if source_id is not None else p.name
    return ByteStream(source_id=sid, data=data, format=format)
