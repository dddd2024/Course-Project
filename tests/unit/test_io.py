from __future__ import annotations

from hashlib import sha256

import pytest

from course_project.io import (
    ByteStream,
    InputError,
    load_bin,
    load_dat,
    load_raw,
)

RAW = b"\x00\x01\x02\xfe\xff"


def test_load_raw_wraps_bytes() -> None:
    stream = load_raw(RAW, source_id="sample-1")
    assert stream.source_id == "sample-1"
    assert stream.data == RAW
    assert len(stream) == len(RAW)
    assert stream.size == len(RAW)
    assert stream.offset_base == 0
    assert stream.format == "raw"
    assert stream.direction is None
    assert stream.timestamp is None


def test_load_raw_accepts_bytearray_and_memoryview() -> None:
    from_ba = load_raw(bytearray(RAW), source_id="ba")
    from_mv = load_raw(memoryview(RAW), source_id="mv")
    assert from_ba.data == RAW
    assert from_mv.data == RAW
    assert from_ba.data == from_mv.data


def test_load_raw_is_deterministic() -> None:
    first = load_raw(RAW, source_id="sample-1")
    second = load_raw(RAW, source_id="sample-1")
    assert first == second
    assert first.sha256 == second.sha256 == sha256(RAW).hexdigest()


def test_load_dat_reads_file_bytes(tmp_path) -> None:
    path = tmp_path / "capture.dat"
    path.write_bytes(RAW)
    stream = load_dat(path)
    assert stream.data == RAW
    assert stream.source_id == "capture.dat"
    assert stream.format == "dat"


def test_load_dat_allows_source_id_override(tmp_path) -> None:
    path = tmp_path / "capture.dat"
    path.write_bytes(RAW)
    stream = load_dat(path, source_id="task-demo-001")
    assert stream.source_id == "task-demo-001"


def test_load_bin_reads_file_bytes(tmp_path) -> None:
    path = tmp_path / "capture.bin"
    path.write_bytes(RAW)
    assert load_bin(path).format == "bin"
    assert load_bin(path).data == RAW


def test_load_raw_empty_bytes_is_valid() -> None:
    stream = load_raw(b"", source_id="empty")
    assert stream.data == b""
    assert stream.size == 0
    assert len(stream) == 0


def test_slice_preserves_absolute_offset() -> None:
    stream = load_raw(RAW, source_id="s", format="dat")
    part = stream.slice(2, 4)
    assert part.data == RAW[2:4]
    assert part.offset_base == 2
    assert part.source_id == "s"
    assert part.format == "dat"


def test_slice_rejects_invalid_bounds() -> None:
    stream = load_raw(RAW, source_id="s")
    with pytest.raises(IndexError):
        stream.slice(-1, 2)
    with pytest.raises(IndexError):
        stream.slice(3, 2)
    with pytest.raises(IndexError):
        stream.slice(0, len(RAW) + 1)


def test_load_dat_missing_file_raises(tmp_path) -> None:
    with pytest.raises(InputError):
        load_dat(tmp_path / "does-not-exist.dat")


def test_load_dat_directory_raises(tmp_path) -> None:
    with pytest.raises(InputError):
        load_dat(tmp_path)


def test_load_raw_rejects_str() -> None:
    with pytest.raises(InputError):
        load_raw("not bytes", source_id="bad")  # type: ignore[arg-type]


def test_byte_stream_requires_non_empty_source_id() -> None:
    with pytest.raises(ValueError):
        ByteStream(source_id="", data=b"\x00")
