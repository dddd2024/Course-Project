from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from course_project.models import ProtocolHypothesis

ProviderMode = Literal["mock", "offline", "live"]


@dataclass(frozen=True, slots=True)
class LLMHypothesisRequest:
    """Provider-neutral input for structured protocol-hypothesis generation."""

    request_id: str
    input_id: str
    allowed_evidence_ids: tuple[str, ...] = ()
    context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HypothesisProposal:
    """Structured provider output before promotion to a project-native hypothesis."""

    offset: int
    size: int | None
    semantic_type: str
    interpretation: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    model_confidence: float = 0.0
    supporting_evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LLMProviderResult:
    """Provider-neutral result containing only project-native hypotheses."""

    provider: str
    mode: ProviderMode
    hypotheses: tuple[ProtocolHypothesis, ...] = ()
    limitations: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class LLMHypothesisProvider(Protocol):
    """Boundary implemented by offline mocks and future real-provider adapters."""

    provider_name: str
    mode: ProviderMode

    def propose(self, request: LLMHypothesisRequest) -> LLMProviderResult:
        """Return structured project-native protocol hypotheses."""


class DeterministicMockLLMProvider:
    """Network-free provider backed by deterministic structured test responses."""

    mode: ProviderMode = "mock"

    def __init__(
        self,
        responses: Mapping[str, Sequence[HypothesisProposal]],
        *,
        provider_name: str = "deterministic-mock",
    ) -> None:
        self.provider_name = _require_text(provider_name, "provider_name")
        self._responses = {
            request_id: tuple(proposals)
            for request_id, proposals in responses.items()
        }
        for request_id in self._responses:
            _require_text(request_id, "mock response request_id")

    def propose(self, request: LLMHypothesisRequest) -> LLMProviderResult:
        _validate_request(request)
        proposals = self._responses.get(request.request_id)
        if proposals is None:
            return LLMProviderResult(
                provider=self.provider_name,
                mode=self.mode,
                limitations=(
                    f"No deterministic mock response configured for {request.request_id!r}.",
                ),
                metadata={"networkAccess": False, "configured": False},
            )

        hypotheses = materialize_hypotheses(
            provider_name=self.provider_name,
            request=request,
            proposals=proposals,
        )
        return LLMProviderResult(
            provider=self.provider_name,
            mode=self.mode,
            hypotheses=hypotheses,
            metadata={"networkAccess": False, "configured": True},
        )


class OfflineNoopLLMProvider:
    """Explicit fail-closed provider for deployments where LLM use is disabled."""

    mode: ProviderMode = "offline"

    def __init__(self, *, provider_name: str = "offline-noop") -> None:
        self.provider_name = _require_text(provider_name, "provider_name")

    def propose(self, request: LLMHypothesisRequest) -> LLMProviderResult:
        _validate_request(request)
        return LLMProviderResult(
            provider=self.provider_name,
            mode=self.mode,
            limitations=(
                "LLM provider is disabled; offline mode performs no network access.",
            ),
            metadata={"networkAccess": False},
        )


def materialize_hypotheses(
    *,
    provider_name: str,
    request: LLMHypothesisRequest,
    proposals: Sequence[HypothesisProposal],
) -> tuple[ProtocolHypothesis, ...]:
    """Validate structured proposals and create deterministic project-native DTOs."""

    provider_name = _require_text(provider_name, "provider_name")
    _validate_request(request)
    allowed_evidence_ids = set(request.allowed_evidence_ids)

    hypotheses: list[ProtocolHypothesis] = []
    seen_ids: set[str] = set()
    for proposal in proposals:
        normalized = _normalize_proposal(proposal, allowed_evidence_ids)
        hypothesis_id = _hypothesis_id(provider_name, request, normalized)
        if hypothesis_id in seen_ids:
            raise ValueError("duplicate structured LLM proposal")
        seen_ids.add(hypothesis_id)
        hypotheses.append(
            ProtocolHypothesis(
                hypothesis_id=hypothesis_id,
                offset=normalized.offset,
                size=normalized.size,
                semantic_type=normalized.semantic_type,
                interpretation=normalized.interpretation,
                parameters=dict(normalized.parameters),
                model_confidence=normalized.model_confidence,
                supporting_evidence_ids=normalized.supporting_evidence_ids,
            )
        )

    by_region: dict[tuple[int, int | None], list[ProtocolHypothesis]] = {}
    for hypothesis in hypotheses:
        by_region.setdefault((hypothesis.offset, hypothesis.size), []).append(hypothesis)

    for region_hypotheses in by_region.values():
        if len(region_hypotheses) < 2:
            continue
        ids = tuple(item.hypothesis_id for item in region_hypotheses)
        for hypothesis in region_hypotheses:
            hypothesis.competing_hypothesis_ids = tuple(
                hypothesis_id
                for hypothesis_id in ids
                if hypothesis_id != hypothesis.hypothesis_id
            )

    return tuple(hypotheses)


def _validate_request(request: LLMHypothesisRequest) -> None:
    _require_text(request.request_id, "request_id")
    _require_text(request.input_id, "input_id")
    if len(set(request.allowed_evidence_ids)) != len(request.allowed_evidence_ids):
        raise ValueError("allowed_evidence_ids must not contain duplicates")
    for evidence_id in request.allowed_evidence_ids:
        _require_text(evidence_id, "allowed evidence id")
    _json_copy(request.context, "request context")


def _normalize_proposal(
    proposal: HypothesisProposal,
    allowed_evidence_ids: set[str],
) -> HypothesisProposal:
    if isinstance(proposal.offset, bool) or not isinstance(proposal.offset, int):
        raise TypeError("proposal offset must be an integer")
    if proposal.offset < 0:
        raise ValueError("proposal offset must be non-negative")
    if proposal.size is not None:
        if isinstance(proposal.size, bool) or not isinstance(proposal.size, int):
            raise TypeError("proposal size must be an integer or None")
        if proposal.size <= 0:
            raise ValueError("proposal size must be positive when provided")

    semantic_type = _require_text(proposal.semantic_type, "proposal semantic_type")
    interpretation = _require_text(proposal.interpretation, "proposal interpretation")
    confidence = _probability(proposal.model_confidence, "proposal model_confidence")
    parameters = _json_copy(proposal.parameters, "proposal parameters")
    if not isinstance(parameters, dict):
        raise TypeError("proposal parameters must be a JSON object")

    supporting_ids = tuple(proposal.supporting_evidence_ids)
    if len(set(supporting_ids)) != len(supporting_ids):
        raise ValueError("supporting_evidence_ids must not contain duplicates")
    for evidence_id in supporting_ids:
        _require_text(evidence_id, "supporting evidence id")
        if evidence_id not in allowed_evidence_ids:
            raise ValueError(
                f"proposal references evidence outside the request: {evidence_id!r}"
            )

    return HypothesisProposal(
        offset=proposal.offset,
        size=proposal.size,
        semantic_type=semantic_type,
        interpretation=interpretation,
        parameters=parameters,
        model_confidence=confidence,
        supporting_evidence_ids=supporting_ids,
    )


def _hypothesis_id(
    provider_name: str,
    request: LLMHypothesisRequest,
    proposal: HypothesisProposal,
) -> str:
    payload = {
        "provider": provider_name,
        "requestId": request.request_id,
        "inputId": request.input_id,
        "proposal": {
            "offset": proposal.offset,
            "size": proposal.size,
            "semanticType": proposal.semantic_type,
            "interpretation": proposal.interpretation,
            "parameters": proposal.parameters,
            "modelConfidence": proposal.model_confidence,
            "supportingEvidenceIds": list(proposal.supporting_evidence_ids),
        },
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return f"llm:{hashlib.sha256(encoded).hexdigest()[:20]}"


def _json_copy(value: Any, label: str) -> Any:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must contain only JSON-compatible values") from exc
    return json.loads(encoded)


def _probability(value: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be numeric")
    normalized = float(value)
    if not math.isfinite(normalized) or not 0.0 <= normalized <= 1.0:
        raise ValueError(f"{label} must be within [0, 1]")
    return normalized


def _require_text(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()
