import json

import pytest

from course_project.evidence import (
    FusionPolicy,
    SemanticWorkflow,
    SemanticWorkflowError,
)
from course_project.llm import HypothesisGenerator
from course_project.models import Evidence, FieldCandidate


class StaticProvider:
    def __init__(self, *proposals: dict[str, object]) -> None:
        self._response = json.dumps({"hypotheses": proposals})

    def complete(self, candidate: FieldCandidate) -> str:
        return self._response


class InvalidProvider:
    def complete(self, candidate: FieldCandidate) -> str:
        return "not-json"


def proposal(
    interpretation: str,
    *,
    semantic_type: str = "length",
    confidence: float = 0.9,
    **parameters: object,
) -> dict[str, object]:
    return {
        "semantic_type": semantic_type,
        "interpretation": interpretation,
        "parameters": parameters,
        "model_confidence": confidence,
    }


def roots() -> tuple[Evidence, Evidence]:
    return (
        Evidence(
            evidence_id="raw-boundary",
            source_component="boundary",
            method="repetition",
            feature_family="structure",
            score=0.95,
            independence_group="raw-boundary",
        ),
        Evidence(
            evidence_id="raw-alignment",
            source_component="alignment",
            method="column-correlation",
            feature_family="length",
            score=0.95,
            independence_group="raw-alignment",
        ),
    )


def candidate(**overrides: object) -> FieldCandidate:
    values: dict[str, object] = {
        "candidate_id": "field-length",
        "family_id": "family-1",
        "offset": 0,
        "size": 2,
        "candidate_types": ("length",),
        "endian": "big",
        "score": 0.9,
        "evidence_ids": ("raw-boundary", "raw-alignment"),
        "attributes": {"backend": "controlled-alignment"},
    }
    values.update(overrides)
    return FieldCandidate(**values)  # type: ignore[arg-type]


def length_messages() -> tuple[bytes, ...]:
    return tuple(
        (2 + payload_size).to_bytes(2, "big") + bytes(payload_size)
        for payload_size in range(2, 6)
    )


def workflow(*proposals: dict[str, object]) -> SemanticWorkflow:
    return SemanticWorkflow(
        HypothesisGenerator(StaticProvider(*proposals)),
        provider_name="static-test",
        model_name="fixture-v1",
    )


def test_complete_workflow_promotes_only_verified_and_fused_field() -> None:
    result = workflow(
        proposal("big-endian total message length", endian="big")
    ).analyze(
        (candidate(),),
        {"family-1": length_messages()},
        upstream_evidence=roots(),
    )

    assert result.limitations == ()
    assert len(result.hypotheses) == 1
    assert len(result.checks) == 1
    assert result.verification_results[0].status == "accepted"
    assert result.fusion_results[0].status == "accepted"
    assert len(result.verified_fields) == 1
    verified = result.verified_fields[0]
    assert verified.semantic_type == "length"
    assert verified.verification_score == 1.0
    assert set(verified.evidence_ids) <= {
        item.evidence_id for item in result.evidence
    }
    assert {item.source_component for item in result.evidence} == {
        "alignment",
        "boundary",
        "inference",
        "llm",
        "verification",
    }


def test_high_model_confidence_cannot_accept_without_verification() -> None:
    result = workflow(
        proposal(
            "big-endian total message length",
            confidence=1.0,
            endian="big",
        )
    ).analyze(
        (candidate(),),
        {"family-1": length_messages()},
        upstream_evidence=roots(),
        verification_enabled=False,
    )

    assert result.checks == ()
    assert result.verification_results == ()
    assert result.fusion_results[0].status == "uncertain"
    assert result.verified_fields == ()


def test_plausible_wrong_hypothesis_is_rejected_without_promotion() -> None:
    result = workflow(
        proposal("little-endian total message length", endian="little")
    ).analyze(
        (candidate(),),
        {"family-1": length_messages()},
        upstream_evidence=roots(),
    )

    assert result.verification_results[0].status == "rejected"
    assert result.fusion_results[0].status == "rejected"
    assert result.verified_fields == ()


def test_multiple_passing_competitors_force_abstention() -> None:
    result = workflow(
        proposal("total message length", endian="big"),
        proposal("frame length", endian="big"),
    ).analyze(
        (candidate(),),
        {"family-1": length_messages()},
        upstream_evidence=roots(),
    )

    assert len(result.verification_results) == 2
    assert all(item.status == "accepted" for item in result.verification_results)
    assert all(item.status == "uncertain" for item in result.fusion_results)
    assert result.verified_fields == ()
    assert "competing interpretations" in result.limitations[-1]


def test_invalid_provider_degrades_one_candidate_without_silent_success() -> None:
    result = SemanticWorkflow(
        HypothesisGenerator(InvalidProvider()), provider_name="invalid-test"
    ).analyze(
        (candidate(),),
        {"family-1": length_messages()},
        upstream_evidence=roots(),
    )

    assert result.hypotheses == ()
    assert result.verified_fields == ()
    assert len(result.limitations) == 1
    assert "strict JSON" in result.limitations[0]


def test_fail_policy_preserves_original_failure_as_cause() -> None:
    analyzer = SemanticWorkflow(
        HypothesisGenerator(InvalidProvider()), provider_name="invalid-test"
    )

    with pytest.raises(SemanticWorkflowError) as error:
        analyzer.analyze(
            (candidate(),),
            {"family-1": length_messages()},
            upstream_evidence=roots(),
            failure_policy="fail",
        )

    assert error.value.__cause__ is not None


def test_missing_corpus_and_llm_disabled_are_explicit_limitations() -> None:
    analyzer = workflow(proposal("packet length", endian="big"))

    missing = analyzer.analyze(
        (candidate(),), {}, upstream_evidence=roots()
    )
    disabled = analyzer.analyze(
        (candidate(),),
        {"family-1": length_messages()},
        upstream_evidence=roots(),
        llm_enabled=False,
    )

    assert "no message corpus" in missing.limitations[0]
    assert "LLM generation disabled" in disabled.limitations[0]
    assert disabled.verified_fields == ()


def test_single_independence_group_is_insufficient_for_acceptance() -> None:
    one_root = roots()[0]
    limited_candidate = candidate(evidence_ids=(one_root.evidence_id,))
    result = workflow(
        proposal("big-endian total message length", endian="big")
    ).analyze(
        (limited_candidate,),
        {"family-1": length_messages()},
        upstream_evidence=(one_root,),
    )

    assert result.verification_results[0].status == "accepted"
    assert result.fusion_results[0].status == "uncertain"
    assert result.verified_fields == ()


def test_configurable_policy_can_require_stronger_independent_support() -> None:
    analyzer = SemanticWorkflow(
        HypothesisGenerator(
            StaticProvider(proposal("packet length", endian="big"))
        ),
        provider_name="static-test",
        fusion_policy=FusionPolicy(minimum_independent_groups=3),
    )

    result = analyzer.analyze(
        (candidate(),),
        {"family-1": length_messages()},
        upstream_evidence=roots(),
    )

    assert result.fusion_results[0].status == "uncertain"
    assert result.verified_fields == ()


def test_duplicate_candidates_and_invalid_upstream_graph_fail_closed() -> None:
    analyzer = workflow(proposal("packet length", endian="big"))
    bad_parent = Evidence(
        evidence_id="derived",
        source_component="test",
        method="derived",
        feature_family="test",
        parent_evidence_ids=("missing",),
    )

    with pytest.raises(ValueError, match="unique"):
        analyzer.analyze((candidate(), candidate()), {"family-1": length_messages()})
    with pytest.raises(SemanticWorkflowError, match="upstream evidence"):
        analyzer.analyze(
            (candidate(),),
            {"family-1": length_messages()},
            upstream_evidence=(bad_parent,),
        )
