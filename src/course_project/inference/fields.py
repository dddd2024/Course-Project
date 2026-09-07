"""Protocol field-candidate inference from aligned families (Track D).

Field candidates are emitted as shared-contract :class:`FieldHypothesis`
objects. ``offset``/``size`` are relative to the start of the messages in the
family; ``evidence["sample_offsets"]`` carries the absolute stream offsets of
the same field in every sample message so downstream verification can locate
real bytes.

Candidates are deliberately allowed to overlap and compete — deciding between
competing interpretations is Track C's verification job, not Track D's.

See ``docs/design-v1.md`` section 5.5.
"""

from __future__ import annotations

from collections.abc import Callable
from itertools import pairwise
from typing import Literal

from course_project.inference.alignment import (
    ColumnKind,
    FamilyProfile,
    align_family,
)
from course_project.inference.clustering import cluster_messages
from course_project.io.records import ByteStream
from course_project.models import FieldHypothesis, PacketCandidate

Endian = Literal["big", "little"]
_ENUM_MAX_CARDINALITY = 8
_LENGTH_SUPPORT = 0.9
_SEQUENCE_STEP_SUPPORT = 0.9
_TIMESTAMP_MAX_DELTA = 1_000_000
_TIMESTAMP_PLAUSIBLE_RATIO = 0.8


def infer_fields(
    stream: ByteStream,
    packets: list[PacketCandidate],
    *,
    header_len: int = 8,
    cluster_threshold: float = 0.9,
) -> list[FieldHypothesis]:
    """Cluster aligned message families and emit field candidates.

    Messages are sliced from ``stream`` using each packet's (absolute) offsets;
    families are clustered by header similarity, aligned column-wise and then
    inspected for magic/constant, enum, length, sequence, timestamp, unknown
    and payload candidates.
    """
    base = stream.offset_base
    messages: list[bytes] = []
    aligned_packets: list[PacketCandidate] = []
    for packet in packets:
        start = packet.start_offset - base
        end = packet.end_offset - base
        if 0 <= start < end <= len(stream.data):
            messages.append(stream.data[start:end])
            aligned_packets.append(packet)
    if not messages:
        return []

    labels = cluster_messages(
        messages, header_len=header_len, threshold=cluster_threshold
    )
    families: dict[int, list[int]] = {}
    for index, label in enumerate(labels):
        families.setdefault(label, []).append(index)

    hypotheses: list[FieldHypothesis] = []
    for cluster_id in sorted(families):
        indices = families[cluster_id]
        family_messages = [messages[i] for i in indices]
        family_packets = [aligned_packets[i] for i in indices]
        family = align_family(family_messages, cluster_id=cluster_id)
        hypotheses.extend(
            _family_field_candidates(cluster_id, family, family_messages, family_packets)
        )
    hypotheses.extend(_cross_family_candidates(messages, labels, aligned_packets))
    return hypotheses


def _family_field_candidates(
    cluster_id: int,
    family: FamilyProfile,
    messages: list[bytes],
    packets: list[PacketCandidate],
) -> list[FieldHypothesis]:
    out: list[FieldHypothesis] = []

    def add(
        semantic: str,
        offset: int,
        size: int | None,
        endian: Endian | None,
        confidence: float,
        evidence: dict,
        tag: str = "",
    ) -> None:
        out.append(
            FieldHypothesis(
                field_id=(
                    f"c{cluster_id}-{semantic}-{tag or 'x'}-{offset}-"
                    f"{size if size is not None else 'v'}-{endian or 'x'}"
                ),
                offset=offset,
                size=size,
                semantic_type=semantic,
                endian=endian,
                confidence=round(confidence, 6),
                evidence={
                    **evidence,
                    "cluster_id": cluster_id,
                    "sample_offsets": [p.start_offset + offset for p in packets],
                },
            )
        )

    # constant runs: magic at the start, generic constant fields elsewhere
    for start, length in _kind_runs(family, "constant"):
        semantic = "magic" if start == 0 else "constant"
        add(
            semantic,
            start,
            length,
            None,
            1.0,
            {
                "value": messages[0][start : start + length].hex(),
                "support": family.message_count,
            },
        )

    # enum regions (small discrete value sets, e.g. message types)
    for region in family.regions:
        if region.kind == "enum":
            add(
                "enum",
                region.offset,
                1,
                None,
                1.0 - (region.cardinality - 1) / 16.0,
                {
                    "cardinality": region.cardinality,
                    "distinct_values": [hex(v) for v in region.distinct_values],
                },
            )

    total_length_fields = _length_candidates(family, messages, add)
    _sequence_candidates(family, messages, add)
    _timestamp_candidates(family, messages, add)

    # merged variable column runs
    for start, length in _kind_runs(family, "variable"):
        add(
            "unknown",
            start,
            length,
            None,
            0.5,
            {
                "run_length": length,
                "max_cardinality": max(
                    r.cardinality for r in family.regions[start : start + length]
                ),
            },
        )

    # variable-length tail beyond the common prefix; when an accepted
    # length(total) field exists, its end is better evidence for the payload
    # start than the family's minimum message length
    if family.has_variable_tail:
        if total_length_fields:
            derived_offset = min(
                offset + size for offset, size, _ in total_length_fields
            )
            best_support = max(support for _, _, support in total_length_fields)
            add(
                "payload",
                derived_offset,
                None,
                None,
                round(best_support, 6),
                {
                    "derived_from_length": True,
                    "length_offsets": sorted(
                        {offset for offset, _, _ in total_length_fields}
                    ),
                    "max_length": family.max_length,
                },
                tag="derived",
            )
        else:
            add(
                "payload",
                family.min_length,
                None,
                None,
                0.8,
                {
                    "min_length": family.min_length,
                    "max_length": family.max_length,
                },
            )

    return out


def _cross_family_candidates(
    messages: list[bytes],
    labels: list[int],
    packets: list[PacketCandidate],
) -> list[FieldHypothesis]:
    """Enum candidates from comparing families instead of messages within one.

    A byte column that is constant inside every family but differs across
    multi-message families with small cardinality is the classic message-type
    signal (``enum``). Candidates carry ``evidence["cross_family"] = True`` so
    Track C can provenance-tag them separately.
    """
    min_len = min(len(m) for m in messages) if messages else 0
    if min_len == 0:
        return []

    family_sizes: dict[int, int] = {}
    for label in labels:
        family_sizes[label] = family_sizes.get(label, 0) + 1
    big_families = {label for label, size in family_sizes.items() if size >= 2}
    if len(big_families) < 2:
        return []

    out: list[FieldHypothesis] = []
    for offset in range(min_len):
        by_family: dict[int, set[int]] = {}
        for message, label in zip(messages, labels):
            if label in big_families:
                by_family.setdefault(label, set()).add(message[offset])
        if not all(len(values) == 1 for values in by_family.values()):
            continue
        distinct = set().union(*by_family.values())
        if not 2 <= len(distinct) <= _ENUM_MAX_CARDINALITY:
            continue
        out.append(
            FieldHypothesis(
                field_id=f"x-enum-cross-{offset}-1-x",
                offset=offset,
                size=1,
                semantic_type="enum",
                confidence=round(1.0 - (len(distinct) - 1) / 16.0, 6),
                evidence={
                    "cross_family": True,
                    "cardinality": len(distinct),
                    "distinct_values": [hex(v) for v in sorted(distinct)],
                    "families": sorted(by_family),
                    "support": sum(
                        family_sizes[label] for label in by_family
                    ),
                    "sample_offsets": [p.start_offset + offset for p in packets],
                },
            )
        )
    return out


def _length_candidates(
    family: FamilyProfile,
    messages: list[bytes],
    add: Callable[..., None],
) -> list[tuple[int, int, float]]:
    """Emit length candidates; return accepted ``(offset, size, support)``
    triples for the ``total`` match so callers can derive the payload start."""
    accepted: list[tuple[int, int, float]] = []
    for size in (1, 2, 4):
        if family.min_length < size:
            continue
        for endian in ("big", "little"):
            if size == 1 and endian == "little":
                continue  # endian is meaningless for a single byte
            for offset in range(family.min_length - size + 1):
                pairs = []
                for message in messages:
                    if offset + size <= len(message):
                        pairs.append(
                            (
                                message,
                                int.from_bytes(message[offset : offset + size], endian),
                            )
                        )
                if not pairs:
                    continue
                support_total = sum(
                    value == len(m) for m, value in pairs
                ) / len(pairs)
                support_after = sum(
                    value == len(m) - offset - size for m, value in pairs
                ) / len(pairs)
                if support_total >= _LENGTH_SUPPORT:
                    add(
                        "length",
                        offset,
                        size,
                        endian,
                        support_total,
                        {
                            "match": "total",
                            "support": support_total,
                            "sample_count": len(pairs),
                        },
                        tag="total",
                    )
                    accepted.append((offset, size, support_total))
                if support_after >= _LENGTH_SUPPORT:
                    add(
                        "length",
                        offset,
                        size,
                        endian,
                        support_after,
                        {
                            "match": "payload_after",
                            "support": support_after,
                            "sample_count": len(pairs),
                        },
                        tag="after",
                    )
    return accepted


def _sequence_candidates(
    family: FamilyProfile,
    messages: list[bytes],
    add: Callable[..., None],
) -> None:
    for size in (1, 2, 4):
        if family.min_length < size:
            continue
        for endian in ("big", "little"):
            if size == 1 and endian == "little":
                continue  # endian is meaningless for a single byte
            for offset in range(family.min_length - size + 1):
                if _starts_or_ends_on_constant(family, offset, size):
                    continue  # padded wide reading (e.g. zero bytes widening a seq)
                values = _read_values(messages, offset, size, endian)
                if len(values) < 2:
                    continue
                steps = [b - a for a, b in pairwise(values)]
                if all(step == 0 for step in steps):
                    continue
                step_support = sum(step == 1 for step in steps) / len(steps)
                if step_support >= _SEQUENCE_STEP_SUPPORT:
                    add(
                        "sequence",
                        offset,
                        size,
                        endian,
                        step_support,
                        {
                            "step_support": step_support,
                            "first": values[0],
                            "last": values[-1],
                            "sample_count": len(values),
                        },
                    )


def _timestamp_candidates(
    family: FamilyProfile,
    messages: list[bytes],
    add: Callable[..., None],
) -> None:
    size = 4
    if family.min_length < size:
        return
    for endian in ("big", "little"):
        for offset in range(family.min_length - size + 1):
            if _starts_or_ends_on_constant(family, offset, size):
                continue  # padded wide reading
            values = _read_values(messages, offset, size, endian)
            if len(values) < 2:
                continue
            diffs = [b - a for a, b in pairwise(values)]
            if not diffs or all(diff == 0 for diff in diffs):
                continue
            if any(diff < 0 for diff in diffs):
                continue
            plausible = sum(
                1 <= diff <= _TIMESTAMP_MAX_DELTA for diff in diffs
            ) / len(diffs)
            if plausible >= _TIMESTAMP_PLAUSIBLE_RATIO and any(
                diff > 1 for diff in diffs
            ):
                add(
                    "timestamp",
                    offset,
                    size,
                    endian,
                    plausible,
                    {
                        "monotonic": True,
                        "plausible_ratio": plausible,
                        "first": values[0],
                        "last": values[-1],
                    },
                )


def _starts_or_ends_on_constant(
    family: FamilyProfile, offset: int, size: int
) -> bool:
    """True when a numeric reading is padded by constant columns.

    Zero-filled reserved bytes widen a 1-byte sequence into a plausible
    2/4-byte one; skipping ranges whose first or last byte lies on a constant
    column removes those degenerate readings.
    """
    for column in (offset, offset + size - 1):
        if _region_kind(family, column) == "constant":
            return True
    return False


def _region_kind(family: FamilyProfile, offset: int) -> ColumnKind | None:
    if 0 <= offset < len(family.regions):
        return family.regions[offset].kind
    return None


def _read_values(
    messages: list[bytes], offset: int, size: int, endian: str
) -> list[int]:
    values = []
    for message in messages:
        if offset + size <= len(message):
            values.append(int.from_bytes(message[offset : offset + size], endian))
    return values


def _kind_runs(family: FamilyProfile, kind: ColumnKind) -> list[tuple[int, int]]:
    """Contiguous ``(start_offset, length)`` runs of regions with the given kind."""
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, region in enumerate(family.regions):
        if region.kind == kind:
            if start is None:
                start = index
        elif start is not None:
            runs.append((start, index - start))
            start = None
    if start is not None:
        runs.append((start, len(family.regions) - start))
    return runs
