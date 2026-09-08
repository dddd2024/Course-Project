from copy import deepcopy

import pytest

from course_project.evidence import (
    EvidenceGraph,
    EvidenceProductionError,
    evidence_from_executable_check,
    evidence_from_field_candidate,
    evidence_from_llm_hypothesis,
)
from course_project.models import ExecutableCheck, FieldCandidate, ProtocolHypothesis


def candidate(**overrides: object) -> FieldCandidate:
    values: dict[str, object] = {
        "candidate_id": "candidate-1",
        "family_id": "family-1",
        "offset": 4,
        "size": 2,
        "candidate_types": ("length", "sequence"),
        "endian": "big",
        "score": 0.85,
        "evidence_ids": (),
        "attributes": {"backend": "alignment", "support": 5},
    }
    values.update(overrides)
    return FieldCandidate(**values)  # type: ignore[arg-type]


def hypothesis(*parents: str, **overrides: object) -> ProtocolHypothesis:
    values: dict[str, object] = {
        "hypothesis_id": "hypothesis-1",
        "offset": 4,
        "size": 2,
        "semantic_type": "length",
        "interpretation": "big-endian payload length",
        "parameters": {"endian": "big", "target": "payload"},
        "model_confidence": 0.9,
        "supporting_evidence_ids": parents,
        "competing_hypothesis_ids": ("hypothesis-2",),
    }
    values.update(overrides)
    return ProtocolHypothesis(**values)  # type: ignore[arg-type]


def check(*parents: str, **overrides: object) -> ExecutableCheck:
    values: dict[str, object] = {
        "check_id": "check:hypothesis-1:length",
        "hypothesis_id": "hypothesis-1",
        "check_type": "length",
        "sample_count": 5,
        "support_count": 5,
        "violation_count": 0,
        "score": 1.0,
        "result": "accepted",
        "evidence_ids": parents,
    }
    values.update(overrides)
    return ExecutableCheck(**values)  # type: ignore[arg-type]


def test_field_candidate_becomes_direct_provenance_evidence() -> None:
    produced = evidence_from_field_candidate(
        candidate(candidate_types=("length",)), sample_ids=("m1", "m2")
    )

    assert produced.source_component == "inference"
    assert produced.method == "alignment"
    assert produced.feature_family == "length"
    assert produced.parent_evidence_ids == ()
    assert produced.independence_group == "field-candidate:alignment:family-1"
    assert produced.sample_ids == ("m1", "m2")
    assert produced.observation["candidateId"] == "candidate-1"


def test_llm_and_verification_evidence_retain_the_complete_parent_chain() -> None:
    direct = evidence_from_field_candidate(candidate())
    llm = evidence_from_llm_hypothesis(
        hypothesis(direct.evidence_id), provider="mock", model="offline-v1"
    )
    verification = evidence_from_executable_check(check(llm.evidence_id))
    graph = EvidenceGraph()

    graph.register_many((direct, llm, verification))

    assert [
        item.evidence_id for item in graph.trace_provenance(verification.evidence_id)
    ] == [direct.evidence_id, llm.evidence_id, verification.evidence_id]
    assert llm.independence_group is None
    assert verification.independence_group is None
    assert graph.independence_groups((llm.evidence_id, verification.evidence_id)) == {
        "field-candidate:alignment:family-1": (
            llm.evidence_id,
            verification.evidence_id,
        )
    }


def test_evidence_ids_are_deterministic_and_mapping_order_independent() -> None:
    first = candidate(attributes={"backend": "alignment", "a": 1, "b": 2})
    second = candidate(attributes={"b": 2, "a": 1, "backend": "alignment"})

    assert evidence_from_field_candidate(first).evidence_id == (
        evidence_from_field_candidate(second).evidence_id
    )


def test_produced_evidence_does_not_alias_mutable_input_data() -> None:
    source = candidate(attributes={"backend": "alignment", "nested": {"value": 1}})
    before = deepcopy(source.attributes)

    produced = evidence_from_field_candidate(source)
    source.attributes["nested"]["value"] = 99  # type: ignore[index]

    assert produced.observation["attributes"] == before


def test_existing_candidate_evidence_is_preserved_as_parentage() -> None:
    produced = evidence_from_field_candidate(
        candidate(evidence_ids=("upstream-1", "upstream-2"))
    )

    assert produced.parent_evidence_ids == ("upstream-1", "upstream-2")
    assert produced.independence_group is None


@pytest.mark.parametrize(
    "invalid_candidate",
    [
        candidate(candidate_id=""),
        candidate(offset=-1),
        candidate(size=0),
        candidate(score=float("nan")),
        candidate(evidence_ids=("same", "same")),
        candidate(attributes={"backend": "alignment", "bad": object()}),
    ],
)
def test_invalid_field_candidates_fail_closed(
    invalid_candidate: FieldCandidate,
) -> None:
    with pytest.raises(EvidenceProductionError):
        evidence_from_field_candidate(invalid_candidate)


def test_derived_evidence_requires_parent_provenance() -> None:
    with pytest.raises(EvidenceProductionError, match="at least one parent"):
        evidence_from_llm_hypothesis(hypothesis(), provider="mock")
    with pytest.raises(EvidenceProductionError, match="at least one parent"):
        evidence_from_executable_check(check())


@pytest.mark.parametrize(
    "invalid_hypothesis, provider, model",
    [
        (hypothesis("parent", model_confidence=1.1), "mock", None),
        (hypothesis("parent", parameters={"bad": float("nan")}), "mock", None),
        (hypothesis("parent"), "", None),
        (hypothesis("parent"), "mock", ""),
    ],
)
def test_invalid_llm_evidence_fails_closed(
    invalid_hypothesis: ProtocolHypothesis,
    provider: str,
    model: str | None,
) -> None:
    with pytest.raises(EvidenceProductionError):
        evidence_from_llm_hypothesis(
            invalid_hypothesis, provider=provider, model=model
        )


@pytest.mark.parametrize(
    "invalid_check",
    [
        check("parent", score=-0.1),
        check("parent", sample_count=4),
        check("parent", support_count=-1, violation_count=6),
        check("parent", result="maybe"),
        check("parent", evidence_ids=("same", "same")),
    ],
)
def test_invalid_verification_evidence_fails_closed(
    invalid_check: ExecutableCheck,
) -> None:
    with pytest.raises(EvidenceProductionError):
        evidence_from_executable_check(invalid_check)
