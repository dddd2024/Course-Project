"""Transparent provenance-aware fusion for EvidenceGraph-PRE.

The policy intentionally stays simple and auditable. Hard dependencies are
collapsed using the repository's existing provenance semantics before any
support/conflict aggregation occurs. Independent components are then averaged
as heuristic strengths; no probability-independence assumption or learned
weight is introduced.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from math import isfinite
from typing import Literal

from course_project.evidence.dependency_collapse import (
    EvidenceContribution,
    collapse_dependent_evidence,
)
from course_project.models import DecisionStatus, Evidence, VerificationResult

EvidenceStance = Literal["support", "conflict", "neutral"]
POLICY_VERSION = "transparent-component-mean-v1"


class ProvenanceFusionError(ValueError):
    """Raised when evidence cannot be fused without ambiguous semantics."""


@dataclass(frozen=True, slots=True)
class FusionComponent:
    """One signed contribution after hard-dependent evidence is collapsed."""

    representative_evidence_id: str
    evidence_ids: tuple[str, ...]
    source_components: tuple[str, ...]
    sample_ids: tuple[str, ...]
    dependency_signals: tuple[str, ...]
    support_strength: float
    conflict_strength: float
    net_strength: float
    direct_support_evidence_ids: tuple[str, ...]
    derived_support_evidence_ids: tuple[str, ...]
    conflict_evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProvenanceFusionResult:
    """Auditable final decision for one protocol hypothesis."""

    hypothesis_id: str
    status: DecisionStatus
    policy: str
    support_score: float
    conflict_score: float
    margin: float
    verification_status: DecisionStatus
    raw_evidence_count: int
    effective_component_count: int
    direct_support_groups: int
    derived_support_records: int
    conflict_records: int
    neutral_records: int
    acceptance_support_threshold: float
    max_conflict_for_accept: float
    minimum_effective_components: int
    components: tuple[FusionComponent, ...]


def fuse_hypothesis_evidence(
    hypothesis_id: str,
    evidence: Iterable[Evidence],
    verification: VerificationResult,
    *,
    acceptance_support_threshold: float = 0.75,
    max_conflict_for_accept: float = 0.25,
    minimum_effective_components: int = 1,
) -> ProvenanceFusionResult:
    """Fuse provenance-tagged evidence into a conservative three-way decision.

    Policy:
    1. hard-collapse shared independence groups and parent/child chains;
    2. within each component, retain the strongest support and conflict and
       reduce them to one signed net contribution;
    3. average independent component contributions as transparent heuristic
       strengths;
    4. require executable verification to accept a hypothesis. Rejected
       verification vetoes the hypothesis; uncertain verification abstains.

    Non-verifier evidence defaults to support unless its observation explicitly
    declares ``stance`` as ``support``, ``conflict`` or ``neutral``. Verifier
    evidence derives its stance from canonical verification status: accepted is
    support, rejected is conflict with strength ``1 - support_ratio``, and
    uncertain is neutral.
    """

    _validate_inputs(
        hypothesis_id,
        verification,
        acceptance_support_threshold=acceptance_support_threshold,
        max_conflict_for_accept=max_conflict_for_accept,
        minimum_effective_components=minimum_effective_components,
    )

    records = tuple(evidence)
    collapse = collapse_dependent_evidence(records)
    by_id = {item.evidence_id: item for item in records}
    signals = {
        item.evidence_id: _classify_evidence(item, hypothesis_id, verification)
        for item in records
    }

    components = tuple(
        _build_component(contribution, by_id, signals)
        for contribution in collapse.contributions
    )
    component_count = len(components)
    denominator = component_count if component_count else 1
    support_score = sum(max(item.net_strength, 0.0) for item in components) / denominator
    conflict_score = sum(max(-item.net_strength, 0.0) for item in components) / denominator
    margin = support_score - conflict_score

    direct_support_groups = sum(
        bool(item.direct_support_evidence_ids) and item.net_strength > 0.0
        for item in components
    )
    derived_support_records = sum(
        stance == "support" and bool(by_id[evidence_id].parent_evidence_ids)
        for evidence_id, (stance, _) in signals.items()
    )
    conflict_records = sum(stance == "conflict" for stance, _ in signals.values())
    neutral_records = sum(stance == "neutral" for stance, _ in signals.values())

    status = _decision(
        verification.status,
        support_score=support_score,
        conflict_score=conflict_score,
        effective_component_count=component_count,
        acceptance_support_threshold=acceptance_support_threshold,
        max_conflict_for_accept=max_conflict_for_accept,
        minimum_effective_components=minimum_effective_components,
    )

    return ProvenanceFusionResult(
        hypothesis_id=hypothesis_id,
        status=status,
        policy=POLICY_VERSION,
        support_score=support_score,
        conflict_score=conflict_score,
        margin=margin,
        verification_status=verification.status,
        raw_evidence_count=len(records),
        effective_component_count=component_count,
        direct_support_groups=direct_support_groups,
        derived_support_records=derived_support_records,
        conflict_records=conflict_records,
        neutral_records=neutral_records,
        acceptance_support_threshold=acceptance_support_threshold,
        max_conflict_for_accept=max_conflict_for_accept,
        minimum_effective_components=minimum_effective_components,
        components=components,
    )


def _validate_inputs(
    hypothesis_id: str,
    verification: VerificationResult,
    *,
    acceptance_support_threshold: float,
    max_conflict_for_accept: float,
    minimum_effective_components: int,
) -> None:
    if not isinstance(hypothesis_id, str):
        raise TypeError("hypothesis_id must be a string")
    if not hypothesis_id.strip():
        raise ProvenanceFusionError("hypothesis_id must not be empty")
    if not isinstance(verification, VerificationResult):
        raise TypeError("verification must use course_project.models.VerificationResult")
    if verification.hypothesis_id != hypothesis_id:
        raise ProvenanceFusionError("verification hypothesis_id must match fusion hypothesis_id")
    if verification.status not in {"accepted", "rejected", "uncertain"}:
        raise ProvenanceFusionError("verification status is not canonical")
    _validate_probability(acceptance_support_threshold, "acceptance_support_threshold")
    _validate_probability(max_conflict_for_accept, "max_conflict_for_accept")
    if max_conflict_for_accept >= acceptance_support_threshold:
        raise ProvenanceFusionError(
            "max_conflict_for_accept must be lower than acceptance_support_threshold"
        )
    if (
        not isinstance(minimum_effective_components, int)
        or isinstance(minimum_effective_components, bool)
        or minimum_effective_components <= 0
    ):
        raise ProvenanceFusionError("minimum_effective_components must be a positive integer")


def _classify_evidence(
    item: Evidence,
    hypothesis_id: str,
    verification: VerificationResult,
) -> tuple[EvidenceStance, float]:
    if item.source_component == "track-c-executable-verifier":
        observed_hypothesis = item.observation.get("hypothesisId")
        if observed_hypothesis != hypothesis_id:
            raise ProvenanceFusionError(
                f"verifier evidence {item.evidence_id} targets a different hypothesis"
            )
        observed_status = item.observation.get("status")
        if observed_status != verification.status:
            raise ProvenanceFusionError(
                f"verifier evidence {item.evidence_id} disagrees with verification status"
            )
        if observed_status == "accepted":
            return "support", item.score
        if observed_status == "rejected":
            return "conflict", 1.0 - item.score
        if observed_status == "uncertain":
            return "neutral", 0.0
        raise ProvenanceFusionError(
            f"verifier evidence {item.evidence_id} has non-canonical status"
        )

    explicit_stance = item.observation.get("stance", "support")
    if explicit_stance not in {"support", "conflict", "neutral"}:
        raise ProvenanceFusionError(
            f"evidence {item.evidence_id} has unsupported stance: {explicit_stance!r}"
        )
    stance: EvidenceStance = explicit_stance
    return stance, item.score if stance != "neutral" else 0.0


def _build_component(
    contribution: EvidenceContribution,
    by_id: dict[str, Evidence],
    signals: dict[str, tuple[EvidenceStance, float]],
) -> FusionComponent:
    evidence_ids = contribution.evidence_ids
    records = tuple(by_id[evidence_id] for evidence_id in evidence_ids)

    support_ids = tuple(
        evidence_id for evidence_id in evidence_ids if signals[evidence_id][0] == "support"
    )
    conflict_ids = tuple(
        evidence_id for evidence_id in evidence_ids if signals[evidence_id][0] == "conflict"
    )
    support_strength = max(
        (signals[evidence_id][1] for evidence_id in support_ids), default=0.0
    )
    conflict_strength = max(
        (signals[evidence_id][1] for evidence_id in conflict_ids), default=0.0
    )
    net_strength = support_strength - conflict_strength

    direct_support_ids = tuple(
        evidence_id
        for evidence_id in support_ids
        if not by_id[evidence_id].parent_evidence_ids
    )
    derived_support_ids = tuple(
        evidence_id
        for evidence_id in support_ids
        if by_id[evidence_id].parent_evidence_ids
    )

    return FusionComponent(
        representative_evidence_id=contribution.representative_evidence_id,
        evidence_ids=evidence_ids,
        source_components=tuple(sorted({item.source_component for item in records})),
        sample_ids=contribution.sample_ids,
        dependency_signals=contribution.dependency_signals,
        support_strength=support_strength,
        conflict_strength=conflict_strength,
        net_strength=net_strength,
        direct_support_evidence_ids=direct_support_ids,
        derived_support_evidence_ids=derived_support_ids,
        conflict_evidence_ids=conflict_ids,
    )


def _decision(
    verification_status: DecisionStatus,
    *,
    support_score: float,
    conflict_score: float,
    effective_component_count: int,
    acceptance_support_threshold: float,
    max_conflict_for_accept: float,
    minimum_effective_components: int,
) -> DecisionStatus:
    if verification_status == "rejected":
        return "rejected"
    if verification_status != "accepted":
        return "uncertain"
    if effective_component_count < minimum_effective_components:
        return "uncertain"
    if conflict_score > max_conflict_for_accept:
        return "uncertain"
    if support_score >= acceptance_support_threshold:
        return "accepted"
    return "uncertain"


def _validate_probability(value: float, name: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{name} must be numeric")
    parsed = float(value)
    if not isfinite(parsed) or not 0.0 <= parsed <= 1.0:
        raise ProvenanceFusionError(f"{name} must be finite and in [0, 1]")
