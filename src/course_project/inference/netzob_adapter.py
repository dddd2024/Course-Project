"""Netzob PRE baseline adapter (Track D).

Netzob is an optional third-party baseline backend: its alignment/split output
is converted at this adapter boundary into project-native
:class:`FieldHypothesis` candidates, and nothing else in the codebase imports
Netzob. When the library is missing, callers get an explicit
``dependency_unavailable`` result instead of a crash (see
``docs/architecture.md`` section 7 and ``docs/open-source-stack.md``).

The thin ``_call_netzob_split`` layer is written against the documented
Netzob 2.x public API (``Symbol`` / ``RawMessage`` / ``Format.splitAligned`` /
``getCells``). It is marked ``UPSTREAM_VALIDATION``: before this baseline
counts as integrated, it must be smoke-tested against a pinned version and
recorded in ``docs/dependency-register.md`` (upstream GPLv3). The conversion
and fallback layers below are fully unit-tested without the library. The same
boundary pattern applies to a future BinaryInferno adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from typing import Literal

from course_project.io.records import ByteStream
from course_project.models import FieldHypothesis, PacketCandidate

_ENUM_MAX_CARDINALITY = 8


@dataclass(frozen=True, slots=True)
class PREBaselineResult:
    """Project-native result of a third-party PRE baseline run."""

    backend: str
    status: Literal["ok", "unavailable", "failed"]
    error_category: str | None = None
    detail: str | None = None
    field_hypotheses: tuple[FieldHypothesis, ...] = ()


def is_netzob_available() -> bool:
    """Whether the optional Netzob dependency can be imported."""
    return find_spec("netzob") is not None


def run_netzob_baseline(
    stream: ByteStream,
    packets: list[PacketCandidate],
    *,
    min_support: int = 2,
) -> PREBaselineResult:
    """Run the Netzob ``splitAligned`` baseline and convert its output.

    Missing dependency -> ``status="unavailable"`` with error category
    ``dependency_unavailable``; a failing upstream call -> ``status="failed"``
    with the original error text. Failures are never converted into empty
    successful results.
    """
    if not is_netzob_available():
        return PREBaselineResult(
            backend="netzob",
            status="unavailable",
            error_category="dependency_unavailable",
            detail=(
                "netzob is not installed; pin a version, smoke-test and record "
                "it in docs/dependency-register.md before using this baseline"
            ),
        )

    messages, aligned_packets = _slice_messages(stream, packets)
    if not messages:
        return PREBaselineResult(
            backend="netzob",
            status="failed",
            error_category="invalid_input",
            detail="no packet with valid offsets inside the stream",
        )

    try:
        per_message_segments = _call_netzob_split(messages)
        hypotheses = convert_field_segments(
            messages,
            aligned_packets,
            per_message_segments,
            backend="netzob",
            min_support=min_support,
        )
    # Deliberately broad: any upstream failure must surface as a failed
    # result (with the original error text), never a crash or empty success.
    except Exception as exc:  # noqa: BLE001
        return PREBaselineResult(
            backend="netzob",
            status="failed",
            error_category="inference_failed",
            detail=f"{type(exc).__name__}: {exc}",
        )
    return PREBaselineResult(
        backend="netzob", status="ok", field_hypotheses=tuple(hypotheses)
    )


def convert_field_segments(
    messages: list[bytes],
    packets: list[PacketCandidate],
    per_message_segments: list[list[bytes]],
    *,
    backend: str = "netzob",
    min_support: int = 2,
) -> list[FieldHypothesis]:
    """Convert third-party per-message field segments into project-native
    :class:`FieldHypothesis` candidates.

    ``per_message_segments[i]`` lists the field byte-segments the backend
    produced for ``messages[i]`` (e.g. Netzob ``getCells`` rows). Field ``k``
    is matched by column index; messages whose row lacks column ``k`` reduce
    that candidate's support (index misalignment for skipped columns is a
    documented V1 limitation, visible via ``evidence["support"]``).

    ``offset``/``size`` are relative to the message start;
    ``evidence["sample_offsets"]`` carries absolute stream positions and
    ``evidence["backend"]`` tags the provenance for Track C.
    """
    if min_support < 1:
        raise ValueError("min_support must be >= 1")
    if len(per_message_segments) != len(messages):
        raise ValueError(
            f"expected one segment row per message, got {len(per_message_segments)} "
            f"rows for {len(messages)} messages"
        )
    if len(packets) != len(messages):
        raise ValueError("packets and messages must have the same length")

    max_fields = max((len(row) for row in per_message_segments), default=0)
    hypotheses: list[FieldHypothesis] = []
    for field_index in range(max_fields):
        contributors = [
            (i, row[field_index])
            for i, row in enumerate(per_message_segments)
            if field_index < len(row)
        ]
        if len(contributors) < min_support:
            continue
        starts = [
            sum(len(segment) for segment in per_message_segments[i][:field_index])
            for i, _ in contributors
        ]
        values = [_as_bytes(segment) for _, segment in contributors]
        sizes = {len(value) for value in values}
        offset = starts[0]

        if len(sizes) > 1:
            semantic = "unknown"
            size: int | None = None
            confidence = 0.5
            extra = {"variable_sizes": sorted(sizes)}
        else:
            size = sizes.pop()
            cardinality = len(set(values))
            if cardinality == 1:
                semantic = (
                    "magic" if (field_index == 0 and offset == 0) else "constant"
                )
                confidence = 1.0
                extra = {"value": values[0].hex()}
            elif cardinality <= _ENUM_MAX_CARDINALITY:
                semantic = "enum"
                confidence = 1.0 - (cardinality - 1) / 16.0
                extra = {
                    "cardinality": cardinality,
                    "distinct_values": [value.hex() for value in sorted(set(values))],
                }
            else:
                semantic = "unknown"
                confidence = 0.5
                extra = {"cardinality": cardinality}

        hypotheses.append(
            FieldHypothesis(
                field_id=(
                    f"{backend}-f{field_index}-{offset}-"
                    f"{size if size is not None else 'v'}"
                ),
                offset=offset,
                size=size,
                semantic_type=semantic,
                confidence=round(confidence, 6),
                evidence={
                    "backend": backend,
                    "field_index": field_index,
                    "support": len(contributors),
                    "sample_count": len(messages),
                    "sample_offsets": [
                        packets[i].start_offset + starts[j]
                        for j, (i, _) in enumerate(contributors)
                    ],
                    "starts_consistent": len(set(starts)) == 1,
                    **extra,
                },
            )
        )
    return hypotheses


def _call_netzob_split(messages: list[bytes]) -> list[list[bytes]]:
    """UPSTREAM_VALIDATION: thin live call into Netzob 2.x.

    Written against the documented public API; wrap-up via
    ``run_netzob_baseline`` surfaces any upstream error as a failed result.
    """
    from netzob.all import Format, RawMessage, Symbol

    raw_messages = [RawMessage(data=message) for message in messages]
    symbol = Symbol(messages=raw_messages, name="capture")
    Format.splitAligned(symbol, useSemantic=False, doInternalSlick=False)
    rows = symbol.getCells(encoded=False, styled=False)
    return [[_as_bytes(cell) for cell in row] for row in rows]


def _as_bytes(value: object) -> bytes:
    """Coerce a third-party cell value to bytes (defensive boundary helper)."""
    if isinstance(value, bytes):
        return value
    if isinstance(value, (bytearray, memoryview)):
        return bytes(value)
    if isinstance(value, str):
        return value.encode("latin-1")
    tobytes = getattr(value, "tobytes", None)
    if callable(tobytes):
        return bytes(tobytes())
    raise TypeError(f"cannot convert cell value of type {type(value).__name__} to bytes")


def _slice_messages(
    stream: ByteStream, packets: list[PacketCandidate]
) -> tuple[list[bytes], list[PacketCandidate]]:
    base = stream.offset_base
    messages: list[bytes] = []
    aligned: list[PacketCandidate] = []
    for packet in packets:
        start = packet.start_offset - base
        end = packet.end_offset - base
        if 0 <= start < end <= len(stream.data):
            messages.append(stream.data[start:end])
            aligned.append(packet)
    return messages, aligned
