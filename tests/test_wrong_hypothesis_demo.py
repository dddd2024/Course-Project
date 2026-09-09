from __future__ import annotations

from course_project.experiments.wrong_hypothesis_demo import (
    run_wrong_hypothesis_engineering_demo,
)


def test_wrong_hypothesis_demo_is_deterministic_and_network_free() -> None:
    first = run_wrong_hypothesis_engineering_demo()
    second = run_wrong_hypothesis_engineering_demo()

    assert first == second
    assert first.corpus_sha256 == (
        "1e4dd8dd10b41e3dbf4c9dfd6751947c2b1955275a4d704e3ec67ee405bc0019"
    )
    assert first.sample_count == 5
    assert first.provider == "engineering-deterministic-mock"
    assert first.provider_mode == "mock"
    assert first.network_access is False


def test_executable_verification_overrides_model_confidence() -> None:
    demo = run_wrong_hypothesis_engineering_demo()
    by_endian = {item.endian: item for item in demo.outcomes}

    assert set(by_endian) == {"big", "little"}
    correct = by_endian["big"]
    wrong = by_endian["little"]

    # The wrong interpretation is deliberately more attractive to the model.
    assert wrong.model_confidence == 0.93
    assert correct.model_confidence == 0.62
    assert wrong.model_confidence > correct.model_confidence
    assert demo.highest_confidence_hypothesis_id == wrong.hypothesis_id

    # Executable evidence, not model confidence, controls support.
    assert correct.verification_status == "accepted"
    assert correct.verification_score == 1.0
    assert correct.sample_count == 5
    assert correct.support_count == 5
    assert correct.violation_count == 0

    assert wrong.verification_status == "rejected"
    assert wrong.verification_score == 0.0
    assert wrong.sample_count == 5
    assert wrong.support_count == 0
    assert wrong.violation_count == 5

    assert demo.supported_hypothesis_ids == (correct.hypothesis_id,)
    assert wrong.hypothesis_id not in demo.supported_hypothesis_ids


def test_provider_materialization_preserves_provenance_and_competition() -> None:
    demo = run_wrong_hypothesis_engineering_demo()
    by_endian = {item.endian: item for item in demo.outcomes}
    correct = by_endian["big"]
    wrong = by_endian["little"]

    assert correct.supporting_evidence_ids == ("engineering-evidence:length-field",)
    assert wrong.supporting_evidence_ids == ("engineering-evidence:length-field",)
    assert correct.competing_hypothesis_ids == (wrong.hypothesis_id,)
    assert wrong.competing_hypothesis_ids == (correct.hypothesis_id,)
