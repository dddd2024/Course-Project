"""Project-native normalized input records (Track D, ``io`` layer).

The analysis engine needs one deterministic representation for raw binary input
before any protocol-semantic reasoning happens. These records are produced and
consumed inside the input layer only; they deliberately do NOT live in the
shared ``course_project.models`` contract so Track D can evolve them without a
cross-track contract migration.

See ``docs/design-v1.md`` section 5.1 and ``docs/architecture.md`` section 5.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

InputFormat = Literal["dat", "bin", "raw"]


@dataclass(frozen=True, slots=True)
class ByteStream:
    """A deterministic, offset-stable view over a block of raw input bytes.

    ``offset_base`` records the absolute offset of ``data[0]`` within the source
    file, so downstream modules (boundary detection, feature extraction) can
    slice the stream while keeping byte references stable to the original input.
    """

    source_id: str
    data: bytes
    format: InputFormat = "raw"
    offset_base: int = 0
    direction: str | None = None
    timestamp: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not self.source_id:
            raise ValueError("source_id must be a non-empty string")
        if isinstance(self.data, (bytearray, memoryview)):
            object.__setattr__(self, "data", bytes(self.data))
        elif not isinstance(self.data, bytes):
            raise TypeError("data must be bytes-like")
        if self.offset_base < 0:
            raise ValueError("offset_base must be >= 0")

    def __len__(self) -> int:
        return len(self.data)

    @property
    def size(self) -> int:
        """Number of bytes in this stream."""
        return len(self.data)

    @property
    def sha256(self) -> str:
        """Content hash for reproducibility checks and dataset identity."""
        return hashlib.sha256(self.data).hexdigest()

    def slice(self, start: int, end: int) -> ByteStream:
        """Return a sub-stream whose offsets stay absolute to the source."""
        if start < 0 or end < start or end > len(self.data):
            raise IndexError(
                f"invalid slice [{start}:{end}] for stream of length {len(self.data)}"
            )
        return ByteStream(
            source_id=self.source_id,
            data=self.data[start:end],
            format=self.format,
            offset_base=self.offset_base + start,
            direction=self.direction,
            timestamp=self.timestamp,
        )
