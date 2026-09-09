"""Naive and provenance-aware evidence fusion with explicit abstention."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from course_project.evidence.graph import EvidenceGraph
from course_project.models import (
    DecisionStatus,
    Evidence,
    ProtocolHypothesis,
    VerificationResult,
)


class FusionError(ValueError):
    """Raised when evidence cannot be fused without violating invariants."""


@dataclass(frozen=True, slots=True)
class FusionPolicy:
    """Transparent thresholds for provenance-aware fusion."""

    accept_threshold: float = 0.8
    reject_threshold: float = 0.2
    minimum_independent_groups: int = 2
    derived_weight: float = 0.25
    require_accepted_verification: bool = True

    def __post_init__(self) -> None:
        if not 0.0 <= self.reject_threshold < self.accept_threshold <= 1.0:
            raise FusionError(
                "thresholds must satisfy 0 <= reject < accept <= 1"
            )
        if self.minimum_independent_groups <= 0:
            raise FusionError("minimum_independent_groups must be positive")
        if not 0.0 <= self.derived_weight <= 1.0:
            raise FusionError("derived_weight must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class FusionResult:
    """Auditable result shared by the baseline and full fusion strategies."""

    hypothesis_id: str
    method: str
    status: DecisionStatus
    evidence_score: float
    verification_score: float | None
    evidence_count: int
    independent_group_count: int
    direct_support_groups: tuple[str, ...]
    direct_conflict_groups: tuple[str, ...]
    derived_support_count: int
    derived_conflict_count: int
    supporting_evidence_ids: tuple[str, ...]
    conflicting_evidence_ids: tuple[str, ...]


def naive_vote(
    hypothesis: ProtocolHypothesis,
    evidence: Iterable[Evidence],
    *,
    conflicting_evidence_ids: Iterable[str] = (),
    accept_threshold: float = 0.6,
    reject_threshold: float = 0.4,
    minimum_votes: int = 2,
) -> FusionResult:
    """Count every evidence record as an independent vote.

    This intentionally naive baseline ignores dependencies and evidence
    strengths so experiments can measure the benefit of provenance handling.
    """

    if minimum_votes <= 0:
        raise FusionError("minimum_votes must be positive")
    _validate_thresholds(accept_threshold, reject_threshold)
    graph = _graph_from(evidence)
    support_ids, conflict_ids = _vote_ids(
        hypothesis, graph, conflicting_evidence_ids
    )
    vote_count = len(support_ids) + len(conflict_ids)
    score = len(support_ids) / vote_count if vote_count else 0.5
    status = _score_decision(
        score,
        vote_count,
        minimum_count=minimum_votes,
        accept_threshold=accept_threshold,
        reject_threshold=reject_threshold,
    )
    return FusionResult(
        hypothesis_id=hypothesis.hypothesis_id,
        method="naive_vote",
        status=status,
        evidence_score=score,
        verification_score=None,
        evidence_count=vote_count,
        independent_group_count=0,
        direct_support_groups=(),
        direct_conflict_groups=(),
        derived_support_count=_derived_count(graph, support_ids),
        derived_conflict_count=_derived_count(graph, conflict_ids),
        supporting_evidence_ids=support_ids,
        conflicting_evidence_ids=conflict_ids,
    )


def provenance_aware_fusion(
    hypothesis: ProtocolHypothesis,
    evidence: Iterable[Evidence],
    *,
    conflicting_evidence_ids: Iterable[str] = (),
    verification: VerificationResult | None = None,
    policy: FusionPolicy | None = None,
) -> FusionResult:
    """Collapse dependent evidence by root group and apply abstention policy."""

    active_policy = policy or FusionPolicy()
    graph = _graph_from(evidence)
    support_ids, conflict_ids = _vote_ids(
        hypothesis, graph, conflicting_evidence_ids
    )
    _validate_verification(hypothesis, verification)

    support_weights, direct_support = _group_weights(
        graph, support_ids, active_policy.derived_weight
    )
    conflict_weights, direct_conflict = _group_weights(
        graph, conflict_ids, active_policy.derived_weight
    )
    all_groups = set(support_weights) | set(conflict_weights)
    if all_groups:
        signed_sum = sum(
            support_weights.get(group_id, 0.0)
            - conflict_weights.get(group_id, 0.0)
            for group_id in all_groups
        )
        score = 0.5 + signed_sum / (2.0 * len(all_groups))
        score = min(1.0, max(0.0, score))
    else:
        score = 0.5

    status = _provenance_decision(
        score,
        len(all_groups),
        verification=verification,
        policy=active_policy,
    )
    return FusionResult(
        hypothesis_id=hypothesis.hypothesis_id,
        method="provenance_aware",
        status=status,
        evidence_score=score,
        verification_score=verification.score if verification is not None else None,
        evidence_count=len(support_ids) + len(conflict_ids),
        independent_group_count=len(all_groups),
        direct_support_groups=tuple(sorted(direct_support)),
        direct_conflict_groups=tuple(sorted(direct_conflict)),
        derived_support_count=_derived_count(graph, support_ids),
        derived_conflict_count=_derived_count(graph, conflict_ids),
        supporting_evidence_ids=support_ids,
        conflicting_evidence_ids=conflict_ids,
    )


def _graph_from(evidence: Iterable[Evidence]) -> EvidenceGraph:
    graph = EvidenceGraph()
    try:
        graph.register_many(evidence)
    except (TypeError, ValueError) as exc:
        raise FusionError(str(exc)) from exc
    return graph


def _vote_ids(
    hypothesis: ProtocolHypothesis,
    graph: EvidenceGraph,
    conflicting_evidence_ids: Iterable[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    support_ids = tuple(dict.fromkeys(hypothesis.supporting_evidence_ids))
    conflict_ids = tuple(dict.fromkeys(conflicting_evidence_ids))
    overlap = set(support_ids) & set(conflict_ids)
    if overlap:
        names = ", ".join(sorted(overlap))
        raise FusionError(f"evidence cannot both support and conflict: {names}")
    for evidence_id in support_ids + conflict_ids:
        if graph.get_evidence(evidence_id) is None:
            raise FusionError(f"unknown evidence_id: {evidence_id}")
    return support_ids, conflict_ids


def _group_weights(
    graph: EvidenceGraph,
    evidence_ids: tuple[str, ...],
    derived_weight: float,
) -> tuple[dict[str, float], set[str]]:
    weights: dict[str, float] = defaultdict(float)
    direct_groups: set[str] = set()
    for evidence_id in evidence_ids:
        item = graph.get_evidence(evidence_id)
        assert item is not None
        root_ids = graph.root_evidence_ids(evidence_id)
        group_ids = {
            root.independence_group or f"evidence:{root_id}"
            for root_id in root_ids
            if (root := graph.get_evidence(root_id)) is not None
        }
        if not group_ids:
            continue
        weight = item.score
        if item.parent_evidence_ids:
            weight *= derived_weight
        else:
            direct_groups.update(group_ids)
        contribution = weight / len(group_ids)
        for group_id in group_ids:
            weights[group_id] = max(weights[group_id], contribution)
    return dict(weights), direct_groups


def _derived_count(graph: EvidenceGraph, evidence_ids: tuple[str, ...]) -> int:
    return sum(
        1
        for evidence_id in evidence_ids
        if (
            (item := graph.get_evidence(evidence_id)) is not None
            and item.parent_evidence_ids
        )
    )


def _validate_verification(
    hypothesis: ProtocolHypothesis,
    verification: VerificationResult | None,
) -> None:
    if verification is None:
        return
    if verification.hypothesis_id != hypothesis.hypothesis_id:
        raise FusionError("verification result belongs to a different hypothesis")
    if verification.status not in {"accepted", "rejected", "uncertain"}:
        raise FusionError("verification status is not canonical")
    if not 0.0 <= verification.score <= 1.0:
        raise FusionError("verification score must be in [0, 1]")
    if verification.sample_count < 0 or verification.support_count < 0:
        raise FusionError("verification counts must be non-negative")
    if verification.support_count > verification.sample_count:
        raise FusionError("verification support_count exceeds sample_count")
    if verification.status == "accepted" and verification.sample_count == 0:
        raise FusionError("accepted verification requires eligible samples")


def _provenance_decision(
    score: float,
    group_count: int,
    *,
    verification: VerificationResult | None,
    policy: FusionPolicy,
) -> DecisionStatus:
    evidence_status = _score_decision(
        score,
        group_count,
        minimum_count=policy.minimum_independent_groups,
        accept_threshold=policy.accept_threshold,
        reject_threshold=policy.reject_threshold,
    )
    if verification is not None and verification.status == "rejected":
        return "rejected"
    if evidence_status == "rejected":
        return "rejected"
    if evidence_status != "accepted":
        return "uncertain"
    if policy.require_accepted_verification and (
        verification is None or verification.status != "accepted"
    ):
        return "uncertain"
    return "accepted"


def _score_decision(
    score: float,
    count: int,
    *,
    minimum_count: int,
    accept_threshold: float,
    reject_threshold: float,
) -> DecisionStatus:
    if count < minimum_count:
        return "uncertain"
    if score >= accept_threshold:
        return "accepted"
    if score <= reject_threshold:
        return "rejected"
    return "uncertain"


def _validate_thresholds(accept_threshold: float, reject_threshold: float) -> None:
    if not 0.0 <= reject_threshold < accept_threshold <= 1.0:
        raise FusionError("thresholds must satisfy 0 <= reject < accept <= 1")
