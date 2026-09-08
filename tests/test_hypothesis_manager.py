import pytest

from course_project.evidence.hypothesis_manager import (
    HypothesisManager,
    HypothesisManagerError,
)
from course_project.models import ProtocolHypothesis, VerificationResult


def make_hypothesis(
    hypothesis_id: str,
    interpretation: str,
    *,
    offset: int = 4,
    size: int | None = 2,
    confidence: float = 0.7,
) -> ProtocolHypothesis:
    return ProtocolHypothesis(
        hypothesis_id=hypothesis_id,
        offset=offset,
        size=size,
        semantic_type="length",
        interpretation=interpretation,
        model_confidence=confidence,
        supporting_evidence_ids=("evidence-1",),
    )


def test_competing_hypotheses_share_a_region_and_start_uncertain() -> None:
    manager = HypothesisManager()

    registered = manager.register_competing(
        (
            make_hypothesis("length-be", "big-endian packet length"),
            make_hypothesis("length-le", "little-endian packet length"),
            make_hypothesis("payload-be", "big-endian payload length"),
        )
    )

    assert [item.hypothesis_id for item in registered] == [
        "length-be",
        "length-le",
        "payload-be",
    ]
    assert manager.status("length-be") == "uncertain"
    assert {
        item.hypothesis_id for item in manager.competing_with("length-be")
    } == {"length-le", "payload-be"}


def test_register_competing_fails_atomically_for_different_regions() -> None:
    manager = HypothesisManager()

    with pytest.raises(HypothesisManagerError, match="same byte region"):
        manager.register_competing(
            (
                make_hypothesis("first", "packet length"),
                make_hypothesis("second", "packet type", offset=6),
            )
        )

    assert len(manager) == 0


def test_invalid_input_and_duplicate_ids_fail_closed() -> None:
    manager = HypothesisManager()
    manager.register(make_hypothesis("known", "packet length"))

    with pytest.raises(HypothesisManagerError, match="duplicate"):
        manager.register(make_hypothesis("known", "payload length"))
    with pytest.raises(HypothesisManagerError, match="model_confidence"):
        manager.register(
            make_hypothesis("invalid-confidence", "packet length", confidence=1.2)
        )

    assert len(manager) == 1


def test_model_confidence_alone_never_accepts_a_hypothesis() -> None:
    manager = HypothesisManager()
    manager.register(
        make_hypothesis("high-confidence", "packet length", confidence=1.0)
    )

    assert manager.status("high-confidence") == "uncertain"
    assert manager.accepted_hypotheses() == ()


def test_verification_controls_three_way_decision() -> None:
    manager = HypothesisManager()
    manager.register_competing(
        (
            make_hypothesis("correct", "big-endian packet length"),
            make_hypothesis("wrong", "little-endian packet length"),
        )
    )

    manager.record_verification(
        VerificationResult(
            hypothesis_id="correct",
            status="accepted",
            score=1.0,
            support_count=10,
            sample_count=10,
            tests={"checkType": "length"},
        )
    )
    manager.record_verification(
        VerificationResult(
            hypothesis_id="wrong",
            status="rejected",
            score=0.0,
            support_count=0,
            sample_count=10,
            tests={"checkType": "length"},
        )
    )

    assert manager.status("correct") == "accepted"
    assert manager.status("wrong") == "rejected"
    assert [item.hypothesis_id for item in manager.accepted_hypotheses()] == [
        "correct"
    ]


def test_acceptance_without_eligible_samples_is_rejected() -> None:
    manager = HypothesisManager()
    manager.register(make_hypothesis("untested", "packet length"))

    with pytest.raises(HypothesisManagerError, match="eligible samples"):
        manager.record_verification(
            VerificationResult(
                hypothesis_id="untested",
                status="accepted",
                score=1.0,
                support_count=0,
                sample_count=0,
            )
        )

    assert manager.status("untested") == "uncertain"
    assert manager.verification_result("untested") is None


def test_registered_hypotheses_are_defensive_copies() -> None:
    manager = HypothesisManager()
    original = make_hypothesis("stable", "packet length")
    original.parameters["endian"] = "big"

    manager.register(original)
    original.parameters["endian"] = "little"
    returned = manager.get("stable")
    returned.parameters["endian"] = "native"

    assert manager.get("stable").parameters == {"endian": "big"}


def test_decision_snapshot_is_deterministic() -> None:
    manager = HypothesisManager()
    manager.register_competing(
        (
            make_hypothesis("b", "little-endian packet length"),
            make_hypothesis("a", "big-endian packet length"),
        )
    )

    snapshot = manager.decision_snapshot()

    assert list(snapshot) == ["a", "b"]
    assert snapshot["a"] == {
        "status": "uncertain",
        "verificationScore": None,
        "competingHypothesisIds": ["b"],
    }
