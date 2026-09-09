import json

import pytest

from course_project.evidence.hypothesis_manager import HypothesisManager
from course_project.llm import (
    HypothesisGenerationError,
    HypothesisGenerator,
    MockLLMProvider,
)
from course_project.models import FieldCandidate


class StaticProvider:
    def __init__(self, response: object) -> None:
        self.response = response
        self.seen_candidate: FieldCandidate | None = None

    def complete(self, candidate: FieldCandidate) -> str:
        self.seen_candidate = candidate
        return self.response  # type: ignore[return-value]


class FailingProvider:
    def complete(self, candidate: FieldCandidate) -> str:
        raise RuntimeError("credentials unavailable")


class MutatingProvider:
    def complete(self, candidate: FieldCandidate) -> str:
        candidate.offset = 999
        candidate.size = 1
        candidate.evidence_ids = ("invented",)
        return response(proposal("length", "packet length"))


def make_candidate(**overrides: object) -> FieldCandidate:
    values: dict[str, object] = {
        "candidate_id": "candidate-1",
        "family_id": "family-1",
        "offset": 4,
        "size": 2,
        "candidate_types": ("sequence", "length"),
        "endian": "big",
        "score": 0.91,
        "evidence_ids": ("evidence-raw-1", "evidence-alignment-1"),
    }
    values.update(overrides)
    return FieldCandidate(**values)  # type: ignore[arg-type]


def response(*hypotheses: dict[str, object]) -> str:
    return json.dumps({"hypotheses": list(hypotheses)})


def proposal(
    semantic_type: str,
    interpretation: str,
    *,
    confidence: object = 0.8,
    parameters: object | None = None,
) -> dict[str, object]:
    return {
        "semantic_type": semantic_type,
        "interpretation": interpretation,
        "parameters": {} if parameters is None else parameters,
        "model_confidence": confidence,
    }


def test_default_mock_provider_is_deterministic_and_offline() -> None:
    candidate = make_candidate()
    generator = HypothesisGenerator()

    first = generator.generate(candidate)
    second = generator.generate(candidate)

    assert first == second
    assert [item.semantic_type for item in first] == ["length", "sequence"]
    assert all(item.offset == 4 and item.size == 2 for item in first)
    assert all(item.parameters == {"endian": "big"} for item in first)
    assert all(item.model_confidence == 0.5 for item in first)
    assert all(
        item.supporting_evidence_ids
        == ("evidence-raw-1", "evidence-alignment-1")
        for item in first
    )


def test_alternatives_for_one_field_are_mutually_competing() -> None:
    hypotheses = HypothesisGenerator().generate(make_candidate())

    first, second = hypotheses
    assert first.competing_hypothesis_ids == (second.hypothesis_id,)
    assert second.competing_hypothesis_ids == (first.hypothesis_id,)


def test_model_generated_hypotheses_remain_uncertain_until_verified() -> None:
    generated = HypothesisGenerator(MockLLMProvider(model_confidence=1.0)).generate(
        make_candidate()
    )
    manager = HypothesisManager()

    registered = manager.register_competing(generated)

    assert all(manager.status(item.hypothesis_id) == "uncertain" for item in registered)
    assert manager.accepted_hypotheses() == ()


def test_provider_controls_semantics_but_not_location_or_evidence() -> None:
    provider = StaticProvider(
        response(
            proposal(
                "length",
                "big-endian payload length",
                confidence=0.99,
                parameters={"endian": "big", "scope": "payload"},
            )
        )
    )
    candidate = make_candidate(offset=12, size=4, evidence_ids=("trusted-1",))

    hypothesis = HypothesisGenerator(provider).generate(candidate)[0]

    assert provider.seen_candidate == candidate
    assert provider.seen_candidate is not candidate
    assert hypothesis.offset == 12
    assert hypothesis.size == 4
    assert hypothesis.supporting_evidence_ids == ("trusted-1",)
    assert hypothesis.semantic_type == "length"
    assert hypothesis.model_confidence == 0.99


@pytest.mark.parametrize(
    "invalid_response",
    [
        "not json",
        '```json\n{"hypotheses": []}\n```',
        '{"hypotheses": [], "status": "accepted"}',
        '{"hypotheses": {}}',
        '{"hypotheses": [], "hypotheses": []}',
        '{"hypotheses": [{"semantic_type": "length"}]}',
        response(proposal("length", "packet length", confidence=True)),
        response(proposal("length", "packet length", confidence=-0.1)),
        response(proposal("length", "packet length", confidence=1.1)),
        response(proposal("length", "packet length", parameters=[])),
        (
            '{"hypotheses":[{"semantic_type":"length",'
            '"interpretation":"packet length","parameters":{},'
            '"model_confidence":NaN}]}'
        ),
    ],
)
def test_invalid_provider_output_fails_closed(invalid_response: str) -> None:
    with pytest.raises(HypothesisGenerationError):
        HypothesisGenerator(StaticProvider(invalid_response)).generate(make_candidate())


def test_provider_cannot_override_trusted_candidate_fields() -> None:
    untrusted = proposal("length", "packet length")
    untrusted["offset"] = 999
    untrusted["supporting_evidence_ids"] = ["invented"]

    with pytest.raises(HypothesisGenerationError, match="required schema"):
        HypothesisGenerator(StaticProvider(response(untrusted))).generate(make_candidate())


def test_provider_mutation_cannot_override_trusted_candidate_fields() -> None:
    candidate = make_candidate()

    hypothesis = HypothesisGenerator(MutatingProvider()).generate(candidate)[0]

    assert hypothesis.offset == 4
    assert hypothesis.size == 2
    assert hypothesis.supporting_evidence_ids == (
        "evidence-raw-1",
        "evidence-alignment-1",
    )
    assert candidate.offset == 4


def test_excessive_and_duplicate_hypotheses_fail_closed() -> None:
    repeated = proposal("length", "packet length")

    with pytest.raises(HypothesisGenerationError, match="too many"):
        HypothesisGenerator(
            StaticProvider(response(repeated, repeated, repeated)), max_hypotheses=2
        ).generate(make_candidate())
    with pytest.raises(HypothesisGenerationError, match="duplicate"):
        HypothesisGenerator(StaticProvider(response(repeated, repeated))).generate(
            make_candidate()
        )


def test_hypothesis_ids_are_stable_across_json_key_order() -> None:
    first_response = response(
        proposal(
            "length",
            "payload length",
            parameters={"scope": "payload", "endian": "big"},
        )
    )
    second_response = (
        '{"hypotheses":[{"model_confidence":0.8,'
        '"parameters":{"endian":"big","scope":"payload"},'
        '"interpretation":"payload length","semantic_type":"length"}]}'
    )

    first = HypothesisGenerator(StaticProvider(first_response)).generate(make_candidate())
    second = HypothesisGenerator(StaticProvider(second_response)).generate(make_candidate())

    assert first[0].hypothesis_id == second[0].hypothesis_id


def test_empty_response_is_a_valid_abstention() -> None:
    assert HypothesisGenerator(StaticProvider(response())).generate(make_candidate()) == ()
    assert HypothesisGenerator().generate(make_candidate(candidate_types=())) == ()


def test_provider_failure_is_reported_without_silent_success() -> None:
    with pytest.raises(HypothesisGenerationError, match="provider failed") as error:
        HypothesisGenerator(FailingProvider()).generate(make_candidate())

    assert isinstance(error.value.__cause__, RuntimeError)


@pytest.mark.parametrize(
    "candidate",
    [
        make_candidate(candidate_id=""),
        make_candidate(offset=-1),
        make_candidate(size=0),
        make_candidate(endian="middle"),
        make_candidate(candidate_types=("",)),
        make_candidate(evidence_ids=("",)),
    ],
)
def test_invalid_project_native_candidate_fails_before_provider(
    candidate: FieldCandidate,
) -> None:
    provider = StaticProvider(response())

    with pytest.raises(HypothesisGenerationError):
        HypothesisGenerator(provider).generate(candidate)

    assert provider.seen_candidate is None


def test_non_string_and_oversized_responses_fail_closed() -> None:
    with pytest.raises(HypothesisGenerationError, match="JSON string"):
        HypothesisGenerator(StaticProvider({})).generate(make_candidate())
    with pytest.raises(HypothesisGenerationError, match="size limit"):
        HypothesisGenerator(
            StaticProvider(response()), max_response_chars=4
        ).generate(make_candidate())


def test_mock_provider_validates_configured_confidence() -> None:
    with pytest.raises(ValueError, match="finite number"):
        MockLLMProvider(model_confidence=float("nan"))
    with pytest.raises(ValueError, match="finite number"):
        MockLLMProvider(model_confidence=1.01)
