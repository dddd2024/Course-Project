"""Column-wise message alignment within a family (Track D).

Aligned messages are profiled column by column up to the shortest message:
``constant`` (one value), ``enum`` (few distinct values) or ``variable``.
Length differences beyond the shortest message are reported as a variable
tail, which usually corresponds to a variable-length payload.

See ``docs/design-v1.md`` section 5.4.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ColumnKind = Literal["constant", "enum", "variable"]

_ENUM_MAX_CARDINALITY = 8


@dataclass(frozen=True, slots=True)
class AlignmentRegion:
    """Column profile at one byte offset across the aligned messages."""

    offset: int
    kind: ColumnKind
    cardinality: int
    distinct_values: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class MessageFamily:
    """Cluster alignment summary: stable/variable regions and length range."""

    cluster_id: int
    message_count: int
    min_length: int
    max_length: int
    regions: tuple[AlignmentRegion, ...]
    has_variable_tail: bool


def align_family(messages: list[bytes], *, cluster_id: int = 0) -> MessageFamily:
    """Align the messages of one family column by column."""
    if not messages:
        raise ValueError("cannot align an empty family")
    min_len = min(len(m) for m in messages)
    max_len = max(len(m) for m in messages)
    regions = []
    for offset in range(min_len):
        values = sorted({m[offset] for m in messages})
        cardinality = len(values)
        if cardinality == 1:
            kind: ColumnKind = "constant"
        elif cardinality <= _ENUM_MAX_CARDINALITY:
            kind = "enum"
        else:
            kind = "variable"
        regions.append(
            AlignmentRegion(
                offset=offset,
                kind=kind,
                cardinality=cardinality,
                distinct_values=tuple(values),
            )
        )
    return MessageFamily(
        cluster_id=cluster_id,
        message_count=len(messages),
        min_length=min_len,
        max_length=max_len,
        regions=tuple(regions),
        has_variable_tail=max_len > min_len,
    )
