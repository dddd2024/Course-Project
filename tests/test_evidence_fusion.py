import pytest

from course_project.evidence import (
    FusionError,
    FusionPolicy,
    naive_vote,
    provenance_aware_fusion,
)
from course_project.models import Evidence, ProtocolHypothesis, VerificationResult


def evidence(
    evidence_id: str,
    *,
    score: float = 0.9,
    parents: tuple[str, ...] = (),
    group: str | None = None,
    source: str = "features",
) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        source_component=source,
        method="controlled-test",
        feature_family="length",
        score=score,
        parent_evidence_ids=parents,
        independence_group=group,
        sample_ids=("message-1",),
    )


def hypothesis(*support_ids: str) -> ProtocolHypothesis:
    return ProtocolHypothesis(
        hypothesis_id="length-be",
        offset=4,
        size=2,
        semantic_type="length",
        interpretation="big-endian full-message length",
        model_confidence=0.99,
        supporting_evidence_ids=tuple(support_ids),
    )


def verification(
    status: str = "accepted",
    *,
    score: float = 1.0,
) -> VerificationResult:
    return VerificationResult(
        hypothesis_id="length-be",
        status=status,
        score=score,
        support_count=10 if status == "accepted" else 0,
        sample_count=10,
        tests={"checkType": "length"},
    )


def test_dependent_restatement_changes_naive_but_not_provenance_vote() -> None:
    records = (
        evidence("raw-support", group="capture-support"),
        evidence(
            "llm-restatement",
            score=0.95,
            parents=("raw-support",),
            group="llm-output",
            source="llm",
        ),
        evidence("raw-conflict", group="capture-conflict"),
    )
    candidate = hypothesis("raw-support", "llm-restatement")

    naive = naive_vote(
        candidate,
        records,
        conflicting_evidence_ids=("raw-conflict",),
    )
    fused = provenance_aware_fusion(
        candidate,
        records,
        conflicting_evidence_ids=("raw-conflict",),
        verification=verification(),
    )

    assert naive.status == "accepted"
    assert naive.evidence_score == pytest.approx(2 / 3)
    assert naive.evidence_count == 3
    assert naive.independent_group_count == 0
    assert fused.status == "uncertain"
    assert fused.evidence_score == pytest.approx(0.5)
    assert fused.independent_group_count == 2
    assert fused.derived_support_count == 1
    assert fused.direct_support_groups == ("capture-support",)


def test_independent_support_plus_verification_is_accepted() -> None:
    records = (
        evidence("length-correlation", score=0.9, group="length-analysis"),
        evidence("alignment", score=0.8, group="alignment-analysis"),
        evidence(
            "llm-derived",
            score=1.0,
            parents=("alignment",),
            group="llm-output",
            source="llm",
        ),
    )
    candidate = hypothesis("length-correlation", "alignment", "llm-derived")

    result = provenance_aware_fusion(
        candidate,
        records,
        verification=verification(score=0.98),
    )

    assert result.status == "accepted"
    assert result.independent_group_count == 2
    assert result.evidence_score == pytest.approx(0.925)
    assert result.verification_score == 0.98
    assert result.derived_support_count == 1


def test_strong_evidence_without_verification_abstains() -> None:
    records = (
        evidence("first", score=1.0, group="group-1"),
        evidence("second", score=1.0, group="group-2"),
    )

    result = provenance_aware_fusion(
        hypothesis("first", "second"),
        records,
    )

    assert result.evidence_score == 1.0
    assert result.status == "uncertain"
    assert result.verification_score is None


def test_rejected_verification_rejects_the_hypothesis() -> None:
    records = (
        evidence("first", score=1.0, group="group-1"),
        evidence("second", score=1.0, group="group-2"),
    )

    result = provenance_aware_fusion(
        hypothesis("first", "second"),
        records,
        verification=verification("rejected", score=0.0),
    )

    assert result.status == "rejected"


def test_insufficient_independent_groups_abstain() -> None:
    records = (
        evidence("root", score=1.0, group="one-source"),
        evidence("derived", score=1.0, parents=("root",), source="llm"),
    )

    result = provenance_aware_fusion(
        hypothesis("root", "derived"),
        records,
        verification=verification(),
    )

    assert result.independent_group_count == 1
    assert result.status == "uncertain"


def test_thresholds_trade_accepted_coverage_for_stricter_risk() -> None:
    records = (
        evidence("first", score=0.8, group="group-1"),
        evidence("second", score=0.8, group="group-2"),
    )
    candidate = hypothesis("first", "second")

    normal = provenance_aware_fusion(
        candidate,
        records,
        verification=verification(),
    )
    strict = provenance_aware_fusion(
        candidate,
        records,
        verification=verification(),
        policy=FusionPolicy(accept_threshold=0.95),
    )

    assert normal.status == "accepted"
    assert strict.status == "uncertain"
    assert normal.evidence_score == strict.evidence_score == pytest.approx(0.9)


def test_overlap_unknown_evidence_and_wrong_verification_fail_closed() -> None:
    records = (evidence("known", group="group-1"),)
    candidate = hypothesis("known")

    with pytest.raises(FusionError, match="both support and conflict"):
        provenance_aware_fusion(
            candidate,
            records,
            conflicting_evidence_ids=("known",),
        )
    with pytest.raises(FusionError, match="unknown evidence_id"):
        provenance_aware_fusion(hypothesis("missing"), records)

    wrong_verification = VerificationResult(
        hypothesis_id="different",
        status="accepted",
        score=1.0,
        support_count=3,
        sample_count=3,
    )
    with pytest.raises(FusionError, match="different hypothesis"):
        provenance_aware_fusion(
            candidate,
            records,
            verification=wrong_verification,
        )

    empty_acceptance = VerificationResult(
        hypothesis_id="length-be",
        status="accepted",
        score=1.0,
        support_count=0,
        sample_count=0,
    )
    with pytest.raises(FusionError, match="eligible samples"):
        provenance_aware_fusion(
            candidate,
            records,
            verification=empty_acceptance,
        )


def test_missing_parent_and_duplicate_evidence_fail_closed() -> None:
    with pytest.raises(FusionError, match="unknown parent"):
        provenance_aware_fusion(
            hypothesis("derived"),
            (evidence("derived", parents=("missing",)),),
        )

    duplicate_records = (
        evidence("duplicate", group="group-1"),
        evidence("duplicate", group="group-2"),
    )
    with pytest.raises(FusionError, match="duplicate evidence_id"):
        provenance_aware_fusion(hypothesis("duplicate"), duplicate_records)
