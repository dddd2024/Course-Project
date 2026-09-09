"""Global structural-consistency selection for verified protocol fields.

Per-hypothesis executable verification and provenance-aware fusion answer whether
one interpretation is individually supportable.  Exporting a protocol schema has
an additional invariant: promoted byte ranges must be mutually compatible.

This module deliberately keeps those two decision layers separate.  It never
rewrites verification/fusion history.  Instead it applies a conservative final
promotion policy to already-accepted hypotheses:

* candidates without overlap are selected;
* an overlapping connected component gets one winner only when that candidate
  scientifically dominates every other member;
* otherwise the whole ambiguous component abstains.

No identifier, insertion order, random choice or arbitrary scalar weighting is
used to break scientific ties.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from math import isfinite
from typing import Literal

SelectionDecision = Literal["selected", "abstained"]
POLICY_VERSION = "pareto-overlap-abstention-v1"
_EPSILON = 1e-12


class GlobalSelectionError(ValueError):
    """Raised when a field-selection input is structurally invalid."""


@dataclass(frozen=True, slots=True)
class FieldSelectionCandidate:
    """Scientific scores and byte range for one fusion-accepted hypothesis."""

    hypothesis_id: str
    candidate_id: str
    offset: int
    size: int
    fusion_margin: float
    support_score: float
    conflict_score: float
    verification_score: float

    def __post_init__(self) -> None:
        if not self.hypothesis_id.strip():
            raise GlobalSelectionError("hypothesis_id must be non-empty")
        if not self.candidate_id.strip():
            raise GlobalSelectionError("candidate_id must be non-empty")
        if self.offset < 0:
            raise GlobalSelectionError("offset must be non-negative")
        if self.size <= 0:
            raise GlobalSelectionError("size must be positive")
        for name, value in (
            ("fusion_margin", self.fusion_margin),
            ("support_score", self.support_score),
            ("conflict_score", self.conflict_score),
            ("verification_score", self.verification_score),
        ):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise TypeError(f"{name} must be numeric")
            if not isfinite(float(value)):
                raise GlobalSelectionError(f"{name} must be finite")
        if not 0.0 <= self.support_score <= 1.0:
            raise GlobalSelectionError("support_score must be within [0, 1]")
        if not 0.0 <= self.conflict_score <= 1.0:
            raise GlobalSelectionError("conflict_score must be within [0, 1]")
        if not 0.0 <= self.verification_score <= 1.0:
            raise GlobalSelectionError("verification_score must be within [0, 1]")

    @property
    def end_offset(self) -> int:
        return self.offset + self.size


@dataclass(frozen=True, slots=True)
class FieldSelectionDecision:
    """Final schema-promotion decision for one accepted hypothesis."""

    hypothesis_id: str
    candidate_id: str
    decision: SelectionDecision
    reason: str
    conflict_hypothesis_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GlobalFieldSelectionResult:
    """Auditable final non-overlapping promotion result."""

    policy: str
    selected_hypothesis_ids: tuple[str, ...]
    decisions: tuple[FieldSelectionDecision, ...]
    conflict_group_count: int
    conflict_hypothesis_count: int
    abstained_hypothesis_count: int


def select_globally_consistent_fields(
    candidates: Iterable[FieldSelectionCandidate],
) -> GlobalFieldSelectionResult:
    """Select a deterministic non-overlapping subset without arbitrary tie breaks."""

    records = tuple(candidates)
    if any(not isinstance(item, FieldSelectionCandidate) for item in records):
        raise TypeError("candidates must contain FieldSelectionCandidate objects")

    by_id: dict[str, FieldSelectionCandidate] = {}
    candidate_ids: set[str] = set()
    for item in records:
        if item.hypothesis_id in by_id:
            raise GlobalSelectionError(f"duplicate hypothesis_id: {item.hypothesis_id}")
        if item.candidate_id in candidate_ids:
            raise GlobalSelectionError(f"duplicate candidate_id: {item.candidate_id}")
        by_id[item.hypothesis_id] = item
        candidate_ids.add(item.candidate_id)

    overlaps = {item.hypothesis_id: set[str]() for item in records}
    ordered = sorted(records, key=lambda item: (item.offset, item.end_offset, item.hypothesis_id))
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            if right.offset >= left.end_offset:
                break
            if _overlaps(left, right):
                overlaps[left.hypothesis_id].add(right.hypothesis_id)
                overlaps[right.hypothesis_id].add(left.hypothesis_id)

    decisions: list[FieldSelectionDecision] = []
    selected: set[str] = set()

    for item in ordered:
        if not overlaps[item.hypothesis_id]:
            selected.add(item.hypothesis_id)
            decisions.append(
                FieldSelectionDecision(
                    hypothesis_id=item.hypothesis_id,
                    candidate_id=item.candidate_id,
                    decision="selected",
                    reason="no_overlap_conflict",
                    conflict_hypothesis_ids=(),
                )
            )

    conflict_ids = {item_id for item_id, peers in overlaps.items() if peers}
    components = _connected_components(conflict_ids, overlaps)
    for component in components:
        members = tuple(by_id[item_id] for item_id in component)
        winner = _unique_component_dominator(members, overlaps)
        if winner is None:
            for item in members:
                peers = tuple(sorted(overlaps[item.hypothesis_id] & set(component)))
                decisions.append(
                    FieldSelectionDecision(
                        hypothesis_id=item.hypothesis_id,
                        candidate_id=item.candidate_id,
                        decision="abstained",
                        reason="ambiguous_overlap_conflict",
                        conflict_hypothesis_ids=peers,
                    )
                )
            continue

        selected.add(winner.hypothesis_id)
        for item in members:
            peers = tuple(sorted(overlaps[item.hypothesis_id] & set(component)))
            if item.hypothesis_id == winner.hypothesis_id:
                decisions.append(
                    FieldSelectionDecision(
                        hypothesis_id=item.hypothesis_id,
                        candidate_id=item.candidate_id,
                        decision="selected",
                        reason="unique_scientific_dominator",
                        conflict_hypothesis_ids=peers,
                    )
                )
            else:
                decisions.append(
                    FieldSelectionDecision(
                        hypothesis_id=item.hypothesis_id,
                        candidate_id=item.candidate_id,
                        decision="abstained",
                        reason="dominated_overlap_conflict",
                        conflict_hypothesis_ids=peers,
                    )
                )

    normalized_decisions = tuple(
        sorted(decisions, key=lambda item: (by_id[item.hypothesis_id].offset, item.hypothesis_id))
    )
    _validate_selected_non_overlapping(selected, by_id)
    return GlobalFieldSelectionResult(
        policy=POLICY_VERSION,
        selected_hypothesis_ids=tuple(
            sorted(selected, key=lambda item_id: (by_id[item_id].offset, item_id))
        ),
        decisions=normalized_decisions,
        conflict_group_count=len(components),
        conflict_hypothesis_count=len(conflict_ids),
        abstained_hypothesis_count=sum(
            item.decision == "abstained" for item in normalized_decisions
        ),
    )


def _connected_components(
    conflict_ids: set[str], overlaps: dict[str, set[str]]
) -> tuple[tuple[str, ...], ...]:
    remaining = set(conflict_ids)
    components: list[tuple[str, ...]] = []
    while remaining:
        root = min(remaining)
        stack = [root]
        component: set[str] = set()
        while stack:
            current = stack.pop()
            if current in component:
                continue
            component.add(current)
            stack.extend(sorted(overlaps[current] & remaining, reverse=True))
        remaining -= component
        components.append(tuple(sorted(component)))
    return tuple(components)


def _unique_component_dominator(
    members: tuple[FieldSelectionCandidate, ...],
    overlaps: dict[str, set[str]],
) -> FieldSelectionCandidate | None:
    """Return one principled winner only if it resolves the whole conflict group."""

    winners: list[FieldSelectionCandidate] = []
    member_ids = {item.hypothesis_id for item in members}
    for candidate in members:
        # A component-wide winner must actually conflict with every other member;
        # otherwise selecting it would not resolve the full connected ambiguity.
        if (overlaps[candidate.hypothesis_id] & member_ids) != (
            member_ids - {candidate.hypothesis_id}
        ):
            continue
        if all(
            candidate.hypothesis_id == other.hypothesis_id
            or _scientifically_dominates(candidate, other)
            for other in members
        ):
            winners.append(candidate)
    return winners[0] if len(winners) == 1 else None


def _scientifically_dominates(
    left: FieldSelectionCandidate, right: FieldSelectionCandidate
) -> bool:
    """Pareto dominance over transparent scientific signals, not IDs/order."""

    no_worse = (
        left.fusion_margin + _EPSILON >= right.fusion_margin
        and left.support_score + _EPSILON >= right.support_score
        and left.verification_score + _EPSILON >= right.verification_score
        and left.conflict_score <= right.conflict_score + _EPSILON
    )
    strictly_better = (
        left.fusion_margin > right.fusion_margin + _EPSILON
        or left.support_score > right.support_score + _EPSILON
        or left.verification_score > right.verification_score + _EPSILON
        or left.conflict_score + _EPSILON < right.conflict_score
    )
    return no_worse and strictly_better


def _overlaps(left: FieldSelectionCandidate, right: FieldSelectionCandidate) -> bool:
    return left.offset < right.end_offset and right.offset < left.end_offset


def _validate_selected_non_overlapping(
    selected: set[str], by_id: dict[str, FieldSelectionCandidate]
) -> None:
    records = sorted(
        (by_id[item_id] for item_id in selected),
        key=lambda item: (item.offset, item.end_offset, item.hypothesis_id),
    )
    for previous, current in zip(records, records[1:]):
        if _overlaps(previous, current):
            raise GlobalSelectionError(
                "global selection produced overlapping promoted fields"
            )
