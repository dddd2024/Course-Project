from __future__ import annotations

import pytest

from course_project.evidence import (
    POLICY_VERSION,
    ProvenanceFusionError,
    fuse_hypothesis_evidence,
)
from course_project.models import DecisionStatus, Evidence, VerificationResult

HYPOTHESIS_ID = "hypothesis:test"


def _verification(status: DecisionStatus, score: float) -> VerificationResult:
    return VerificationResult(
        hypothesis_id=HYPOTHESIS_ID,
        status=status,
        score=score,
        support_count=9 if status == "accepted" else 1,
        sample_count=10,
    )


def _evidence(
    evidence_id: str,
    score: float,
    group: str,
    *,
    source: str = "test-source",
    parents: tuple[str, ...] = (),
    stance: str | None = None,
) -> Evidence:
    observation: dict[str, object] = {}
    if stance is not None:
        observation["stance"] = stance
    return Evidence(
        evidence_id=evidence_id,
        source_component=source,
        method="fixture",
        feature_family="length",
        score=score,
        observation=observation,
        parent_evidence_ids=parents,
        independence_group=group,
        sample_ids=("m1", "m2", "m3"),
    )


def _verifier(status: DecisionStatus, score: float, *, parent: str = "candidate") -> Evidence:
    return Evidence(
        evidence_id="verification",
        source_component="track-c-executable-verifier",
        method="length",
        feature_family="length",
        score=score,
        observation={"hypothesisId": HYPOTHESIS_ID, "status": status},
        parent_evidence_ids=(parent,),
        independence_group="field-region",
        sample_ids=("m1", "m2", "m3"),
    )


def test_dependent_candidate_and_verifier_contribute_once() -> None:
    candidate = _evidence("candidate", 0.80, "field-region")
    verifier = _verifier("accepted", 0.95)

    result = fuse_hypothesis_evidence(
        HYPOTHESIS_ID,
        (candidate, verifier),
        _verification("accepted", 0.95),
    )

    assert result.status == "accepted"
    assert result.policy == POLICY_VERSION
    assert result.raw_evidence_count == 2
    assert result.effective_component_count == 1
    assert result.support_score == pytest.approx(0.95)
    assert result.direct_support_groups == 1
    assert result.derived_support_records == 1
    assert result.components[0].evidence_ids == ("candidate", "verification")
    assert "shared_independence_group" in result.components[0].dependency_signals
    assert "parent_link" in result.components[0].dependency_signals


def test_independent_alignment_component_is_fused_without_probability_multiplication() -> None:
    candidate = _evidence("candidate", 0.80, "field-region")
    verifier = _verifier("accepted", 0.95)
    alignment = _evidence(
        "alignment",
        0.70,
        "alignment-family",
        source="track-d-alignment",
    )

    result = fuse_hypothesis_evidence(
        HYPOTHESIS_ID,
        (alignment, verifier, candidate),
        _verification("accepted", 0.95),
    )

    assert result.status == "accepted"
    assert result.effective_component_count == 2
    assert result.support_score == pytest.approx((0.95 + 0.70) / 2)
    assert result.conflict_score == 0.0
    assert result.direct_support_groups == 2


def test_strong_independent_conflict_forces_abstention_even_after_accepted_verification() -> None:
    candidate = _evidence("candidate", 0.80, "field-region")
    verifier = _verifier("accepted", 0.95)
    conflict = _evidence("conflict", 0.90, "independent-conflict", stance="conflict")

    result = fuse_hypothesis_evidence(
        HYPOTHESIS_ID,
        (candidate, verifier, conflict),
        _verification("accepted", 0.95),
    )

    assert result.status == "uncertain"
    assert result.support_score == pytest.approx(0.475)
    assert result.conflict_score == pytest.approx(0.45)
    assert result.conflict_records == 1


def test_rejected_executable_verification_vetoes_high_non_verifier_support() -> None:
    candidate = _evidence("candidate", 0.99, "field-region")
    verifier = _verifier("rejected", 0.20)
    alignment = _evidence("alignment", 0.99, "alignment-family")

    result = fuse_hypothesis_evidence(
        HYPOTHESIS_ID,
        (candidate, verifier, alignment),
        _verification("rejected", 0.20),
    )

    assert result.status == "rejected"
    assert result.verification_status == "rejected"
    assert result.conflict_records == 1


def test_uncertain_executable_verification_preserves_abstention() -> None:
    candidate = _evidence("candidate", 0.99, "field-region")
    verifier = _verifier("uncertain", 0.80)
    alignment = _evidence("alignment", 0.99, "alignment-family")

    result = fuse_hypothesis_evidence(
        HYPOTHESIS_ID,
        (candidate, verifier, alignment),
        _verification("uncertain", 0.80),
    )

    assert result.status == "uncertain"
    assert result.neutral_records == 1


def test_fusion_is_order_invariant() -> None:
    records = (
        _evidence("candidate", 0.80, "field-region"),
        _verifier("accepted", 0.95),
        _evidence("alignment", 0.70, "alignment-family"),
    )
    verification = _verification("accepted", 0.95)

    forward = fuse_hypothesis_evidence(HYPOTHESIS_ID, records, verification)
    reverse = fuse_hypothesis_evidence(HYPOTHESIS_ID, tuple(reversed(records)), verification)

    assert forward == reverse


def test_empty_evidence_fails_closed_to_uncertain() -> None:
    result = fuse_hypothesis_evidence(
        HYPOTHESIS_ID,
        (),
        _verification("accepted", 1.0),
    )

    assert result.status == "uncertain"
    assert result.effective_component_count == 0
    assert result.support_score == 0.0


def test_non_verifier_explicit_stance_must_be_canonical() -> None:
    malformed = _evidence("candidate", 0.8, "field-region", stance="maybe")

    with pytest.raises(ProvenanceFusionError, match="unsupported stance"):
        fuse_hypothesis_evidence(
            HYPOTHESIS_ID,
            (malformed,),
            _verification("accepted", 0.95),
        )


def test_verifier_evidence_must_target_the_same_hypothesis() -> None:
    candidate = _evidence("candidate", 0.8, "field-region")
    verifier = _verifier("accepted", 0.95)
    verifier.observation["hypothesisId"] = "hypothesis:other"

    with pytest.raises(ProvenanceFusionError, match="different hypothesis"):
        fuse_hypothesis_evidence(
            HYPOTHESIS_ID,
            (candidate, verifier),
            _verification("accepted", 0.95),
        )


def test_threshold_configuration_fails_closed() -> None:
    with pytest.raises(ProvenanceFusionError, match="lower than"):
        fuse_hypothesis_evidence(
            HYPOTHESIS_ID,
            (),
            _verification("accepted", 1.0),
            acceptance_support_threshold=0.5,
            max_conflict_for_accept=0.5,
        )
