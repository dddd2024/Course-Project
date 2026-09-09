from __future__ import annotations

import socket

import pytest

from course_project.llm.provider import (
    DeterministicMockLLMProvider,
    HypothesisProposal,
    LLMHypothesisProvider,
    LLMHypothesisRequest,
    LLMProviderResult,
    OfflineNoopLLMProvider,
)
from course_project.models import ProtocolHypothesis


def _request() -> LLMHypothesisRequest:
    return LLMHypothesisRequest(
        request_id="request-1",
        input_id="input-1",
        allowed_evidence_ids=("e-field", "e-alignment"),
        context={"familyId": "family-1", "sampleCount": 8},
    )


def _proposals() -> tuple[HypothesisProposal, ...]:
    return (
        HypothesisProposal(
            offset=2,
            size=2,
            semantic_type="length",
            interpretation="little-endian payload length",
            parameters={"endian": "little", "target": "payload"},
            model_confidence=0.82,
            supporting_evidence_ids=("e-field",),
        ),
        HypothesisProposal(
            offset=2,
            size=2,
            semantic_type="sequence",
            interpretation="little-endian incrementing sequence",
            parameters={"endian": "little", "step": 1},
            model_confidence=0.61,
            supporting_evidence_ids=("e-alignment",),
        ),
    )


def test_mock_provider_is_deterministic_and_links_competing_hypotheses() -> None:
    provider = DeterministicMockLLMProvider({"request-1": _proposals()})

    first = provider.propose(_request())
    second = provider.propose(_request())

    assert isinstance(provider, LLMHypothesisProvider)
    assert first == second
    assert first.provider == "deterministic-mock"
    assert first.mode == "mock"
    assert first.metadata == {"networkAccess": False, "configured": True}
    assert len(first.hypotheses) == 2
    assert all(isinstance(item, ProtocolHypothesis) for item in first.hypotheses)

    length, sequence = first.hypotheses
    assert length.hypothesis_id != sequence.hypothesis_id
    assert length.competing_hypothesis_ids == (sequence.hypothesis_id,)
    assert sequence.competing_hypothesis_ids == (length.hypothesis_id,)
    assert length.model_confidence == pytest.approx(0.82)
    assert sequence.model_confidence == pytest.approx(0.61)
    assert not hasattr(length, "verification_score")
    assert not hasattr(sequence, "verification_score")


def test_offline_provider_performs_no_network_work(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("offline provider attempted network access")

    monkeypatch.setattr(socket, "create_connection", fail_network)

    result = OfflineNoopLLMProvider().propose(_request())

    assert result.mode == "offline"
    assert result.hypotheses == ()
    assert result.metadata == {"networkAccess": False}
    assert result.limitations == (
        "LLM provider is disabled; offline mode performs no network access.",
    )


def test_mock_provider_fails_closed_on_unknown_evidence_reference() -> None:
    provider = DeterministicMockLLMProvider(
        {
            "request-1": (
                HypothesisProposal(
                    offset=0,
                    size=1,
                    semantic_type="magic",
                    interpretation="message type byte",
                    model_confidence=0.5,
                    supporting_evidence_ids=("not-allowed",),
                ),
            )
        }
    )

    with pytest.raises(ValueError, match="outside the request"):
        provider.propose(_request())


def test_mock_provider_rejects_non_json_structured_values() -> None:
    provider = DeterministicMockLLMProvider(
        {
            "request-1": (
                HypothesisProposal(
                    offset=0,
                    size=1,
                    semantic_type="enum",
                    interpretation="enum candidate",
                    parameters={"invalid": object()},
                    model_confidence=0.4,
                ),
            )
        }
    )

    with pytest.raises(ValueError, match="JSON-compatible"):
        provider.propose(_request())


def test_mock_provider_rejects_invalid_model_confidence() -> None:
    provider = DeterministicMockLLMProvider(
        {
            "request-1": (
                HypothesisProposal(
                    offset=0,
                    size=1,
                    semantic_type="enum",
                    interpretation="enum candidate",
                    model_confidence=1.2,
                ),
            )
        }
    )

    with pytest.raises(ValueError, match=r"within \[0, 1\]"):
        provider.propose(_request())


def test_missing_mock_response_is_explicit_and_fail_closed() -> None:
    result = DeterministicMockLLMProvider({}).propose(_request())

    assert result.hypotheses == ()
    assert result.metadata == {"networkAccess": False, "configured": False}
    assert result.limitations == (
        "No deterministic mock response configured for 'request-1'.",
    )


def test_future_real_adapter_can_implement_provider_protocol() -> None:
    class FutureRealProvider:
        provider_name = "future-real"
        mode = "live"

        def propose(self, request: LLMHypothesisRequest) -> LLMProviderResult:
            return LLMProviderResult(
                provider=self.provider_name,
                mode="live",
                metadata={"requestId": request.request_id},
            )

    provider = FutureRealProvider()

    assert isinstance(provider, LLMHypothesisProvider)
    assert provider.propose(_request()).provider == "future-real"
