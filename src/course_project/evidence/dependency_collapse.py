"""Conservative dependency collapse for provenance-tagged evidence.

This module deliberately stops before final EvidenceGraph-PRE fusion.  It only
answers the narrower question required by the provenance contract: which
records are demonstrably dependent and therefore must not be counted as
independent support.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from course_project.models import Evidence


class EvidenceDependencyError(ValueError):
    """Raised when evidence provenance is unsafe to collapse or fuse."""


@dataclass(frozen=True, slots=True)
class EvidenceContribution:
    """One effective contribution after hard dependencies are collapsed."""

    representative_evidence_id: str
    evidence_ids: tuple[str, ...]
    independence_groups: tuple[str, ...]
    sample_ids: tuple[str, ...]
    effective_score: float
    raw_score_total: float
    dependency_signals: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidenceCollapseResult:
    """Auditable before/after summary for dependency collapse."""

    contributions: tuple[EvidenceContribution, ...]
    raw_count: int
    effective_count: int
    raw_support_total: float
    effective_support_total: float


class _DisjointSet:
    def __init__(self, evidence_ids: Iterable[str]) -> None:
        self._parent = {evidence_id: evidence_id for evidence_id in evidence_ids}

    def find(self, evidence_id: str) -> str:
        parent = self._parent[evidence_id]
        if parent != evidence_id:
            self._parent[evidence_id] = self.find(parent)
        return self._parent[evidence_id]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        # Lexical root selection makes the component representation deterministic.
        if left_root < right_root:
            self._parent[right_root] = left_root
        else:
            self._parent[left_root] = right_root


def collapse_dependent_evidence(evidence: Iterable[Evidence]) -> EvidenceCollapseResult:
    """Collapse hard-dependent evidence into conservative effective contributions.

    Two records are hard-dependent when either:

    * they explicitly share an ``independence_group``; or
    * one is derived from the other through ``parent_evidence_ids``.

    Dependency is transitive.  Each connected component contributes at most its
    strongest member score.  Scores are intentionally *not* added within a
    component because doing so would double-count correlated support.

    ``sample_ids`` are preserved for later coverage/ablation analysis, but sample
    overlap alone is not interpreted as a dependency claim by this primitive.
    """

    records = tuple(evidence)
    if not records:
        return EvidenceCollapseResult((), 0, 0, 0.0, 0.0)

    by_id: dict[str, Evidence] = {}
    for item in records:
        _validate_record(item)
        if item.evidence_id in by_id:
            raise EvidenceDependencyError(f"duplicate evidence_id: {item.evidence_id}")
        by_id[item.evidence_id] = item

    _validate_parent_references(by_id)
    _validate_parent_graph_is_acyclic(by_id)

    groups: dict[str, list[str]] = defaultdict(list)
    for item in records:
        assert item.independence_group is not None
        groups[item.independence_group].append(item.evidence_id)

    components = _DisjointSet(by_id)
    for member_ids in groups.values():
        anchor = member_ids[0]
        for member_id in member_ids[1:]:
            components.union(anchor, member_id)

    for item in records:
        for parent_id in item.parent_evidence_ids:
            components.union(item.evidence_id, parent_id)

    members_by_root: dict[str, list[str]] = defaultdict(list)
    for evidence_id in sorted(by_id):
        members_by_root[components.find(evidence_id)].append(evidence_id)

    contributions = tuple(
        _build_contribution(tuple(sorted(member_ids)), by_id)
        for _, member_ids in sorted(members_by_root.items())
    )
    raw_support_total = sum(item.score for item in records)
    effective_support_total = sum(item.effective_score for item in contributions)

    if effective_support_total > raw_support_total + 1e-12:
        raise AssertionError("dependency collapse must not increase total support")

    return EvidenceCollapseResult(
        contributions=contributions,
        raw_count=len(records),
        effective_count=len(contributions),
        raw_support_total=raw_support_total,
        effective_support_total=effective_support_total,
    )


def _validate_record(item: Evidence) -> None:
    if not isinstance(item, Evidence):
        raise TypeError("evidence must use course_project.models.Evidence")
    if not item.evidence_id:
        raise EvidenceDependencyError("evidence_id must not be empty")
    if not item.source_component:
        raise EvidenceDependencyError(f"evidence {item.evidence_id} source_component is required")
    if not item.method:
        raise EvidenceDependencyError(f"evidence {item.evidence_id} method is required")
    if not item.feature_family:
        raise EvidenceDependencyError(f"evidence {item.evidence_id} feature_family is required")
    if not 0.0 <= item.score <= 1.0:
        raise EvidenceDependencyError(f"evidence {item.evidence_id} score must be in [0, 1]")
    if item.independence_group is None or not item.independence_group.strip():
        raise EvidenceDependencyError(
            f"evidence {item.evidence_id} independence_group is required for dependency collapse"
        )
    if len(set(item.parent_evidence_ids)) != len(item.parent_evidence_ids):
        raise EvidenceDependencyError(
            f"evidence {item.evidence_id} contains duplicate parent_evidence_ids"
        )


def _validate_parent_references(by_id: dict[str, Evidence]) -> None:
    for item in by_id.values():
        for parent_id in item.parent_evidence_ids:
            if parent_id == item.evidence_id:
                raise EvidenceDependencyError(f"evidence {item.evidence_id} cannot parent itself")
            if parent_id not in by_id:
                raise EvidenceDependencyError(
                    f"evidence {item.evidence_id} references unknown parent {parent_id}"
                )


def _validate_parent_graph_is_acyclic(by_id: dict[str, Evidence]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(evidence_id: str) -> None:
        if evidence_id in visited:
            return
        if evidence_id in visiting:
            raise EvidenceDependencyError("evidence parent graph contains a cycle")
        visiting.add(evidence_id)
        for parent_id in by_id[evidence_id].parent_evidence_ids:
            visit(parent_id)
        visiting.remove(evidence_id)
        visited.add(evidence_id)

    for evidence_id in sorted(by_id):
        visit(evidence_id)


def _build_contribution(
    evidence_ids: tuple[str, ...], by_id: dict[str, Evidence]
) -> EvidenceContribution:
    records = tuple(by_id[evidence_id] for evidence_id in evidence_ids)
    representative = min(records, key=lambda item: (-item.score, item.evidence_id))

    group_counts: dict[str, int] = defaultdict(int)
    for item in records:
        assert item.independence_group is not None
        group_counts[item.independence_group] += 1

    dependency_signals: list[str] = []
    if any(count > 1 for count in group_counts.values()):
        dependency_signals.append("shared_independence_group")
    if any(item.parent_evidence_ids for item in records):
        dependency_signals.append("parent_link")

    return EvidenceContribution(
        representative_evidence_id=representative.evidence_id,
        evidence_ids=evidence_ids,
        independence_groups=tuple(sorted(group_counts)),
        sample_ids=tuple(sorted({sample_id for item in records for sample_id in item.sample_ids})),
        effective_score=representative.score,
        raw_score_total=sum(item.score for item in records),
        dependency_signals=tuple(dependency_signals),
    )
