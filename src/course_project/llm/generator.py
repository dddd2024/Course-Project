"""Structured LLM hypothesis generation behind a project-native boundary."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Protocol

from course_project.models import FieldCandidate, ProtocolHypothesis

_RESPONSE_KEYS = frozenset({"hypotheses"})
_PROPOSAL_KEYS = frozenset(
    {"semantic_type", "interpretation", "parameters", "model_confidence"}
)


class HypothesisGenerationError(ValueError):
    """Raised when a provider or its response cannot safely produce hypotheses."""


class HypothesisProvider(Protocol):
    """Provider boundary that exposes only project-native field candidates."""

    def complete(self, candidate: FieldCandidate) -> str:
        """Return one strict JSON response containing semantic proposals."""


@dataclass(frozen=True, slots=True)
class _SemanticProposal:
    semantic_type: str
    interpretation: str
    parameters: dict[str, Any]
    model_confidence: float


class MockLLMProvider:
    """Deterministic offline provider used by default and in baseline CI."""

    def __init__(self, *, model_confidence: float = 0.5) -> None:
        if (
            isinstance(model_confidence, bool)
            or not isinstance(model_confidence, (int, float))
            or not math.isfinite(float(model_confidence))
            or not 0.0 <= float(model_confidence) <= 1.0
        ):
            raise ValueError("model_confidence must be a finite number in [0, 1]")
        self._model_confidence = float(model_confidence)

    def complete(self, candidate: FieldCandidate) -> str:
        if not isinstance(candidate, FieldCandidate):
            raise TypeError("candidate must use course_project.models.FieldCandidate")

        parameters: dict[str, Any] = {}
        if candidate.endian is not None:
            parameters["endian"] = candidate.endian

        hypotheses = [
            {
                "semantic_type": semantic_type,
                "interpretation": f"candidate {semantic_type} field",
                "parameters": parameters,
                "model_confidence": self._model_confidence,
            }
            for semantic_type in sorted(set(candidate.candidate_types))
        ]
        return json.dumps(
            {"hypotheses": hypotheses},
            sort_keys=True,
            separators=(",", ":"),
        )


class HypothesisGenerator:
    """Turn untrusted semantic proposals into project-native hypotheses."""

    def __init__(
        self,
        provider: HypothesisProvider | None = None,
        *,
        max_hypotheses: int = 8,
        max_response_chars: int = 65_536,
    ) -> None:
        if (
            isinstance(max_hypotheses, bool)
            or not isinstance(max_hypotheses, int)
            or max_hypotheses <= 0
        ):
            raise ValueError("max_hypotheses must be positive")
        if (
            isinstance(max_response_chars, bool)
            or not isinstance(max_response_chars, int)
            or max_response_chars <= 0
        ):
            raise ValueError("max_response_chars must be positive")
        self._provider = provider if provider is not None else MockLLMProvider()
        self._max_hypotheses = max_hypotheses
        self._max_response_chars = max_response_chars

    def generate(self, candidate: FieldCandidate) -> tuple[ProtocolHypothesis, ...]:
        """Generate mutually competing, initially unverified hypotheses."""

        _validate_candidate(candidate)
        trusted_candidate = deepcopy(candidate)
        try:
            response = self._provider.complete(deepcopy(trusted_candidate))
        except Exception as exc:
            raise HypothesisGenerationError("hypothesis provider failed") from exc

        proposals = _parse_response(
            response,
            max_hypotheses=self._max_hypotheses,
            max_response_chars=self._max_response_chars,
        )
        hypothesis_ids = tuple(
            _hypothesis_id(trusted_candidate, proposal) for proposal in proposals
        )
        if len(set(hypothesis_ids)) != len(hypothesis_ids):
            raise HypothesisGenerationError(
                "provider response contains duplicate hypotheses"
            )

        hypotheses = []
        for hypothesis_id, proposal in zip(hypothesis_ids, proposals, strict=True):
            competitors = tuple(
                sorted(other_id for other_id in hypothesis_ids if other_id != hypothesis_id)
            )
            hypotheses.append(
                ProtocolHypothesis(
                    hypothesis_id=hypothesis_id,
                    offset=trusted_candidate.offset,
                    size=trusted_candidate.size,
                    semantic_type=proposal.semantic_type,
                    interpretation=proposal.interpretation,
                    parameters=proposal.parameters,
                    model_confidence=proposal.model_confidence,
                    supporting_evidence_ids=tuple(trusted_candidate.evidence_ids),
                    competing_hypothesis_ids=competitors,
                )
            )
        return tuple(hypotheses)


def _parse_response(
    response: str,
    *,
    max_hypotheses: int,
    max_response_chars: int,
) -> tuple[_SemanticProposal, ...]:
    if not isinstance(response, str):
        raise HypothesisGenerationError("provider response must be a JSON string")
    if len(response) > max_response_chars:
        raise HypothesisGenerationError("provider response exceeds the size limit")

    try:
        document = json.loads(
            response,
            object_pairs_hook=_strict_object,
            parse_constant=lambda value: _reject_json_constant(value),
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise HypothesisGenerationError("provider response is not strict JSON") from exc

    if not isinstance(document, dict) or set(document) != _RESPONSE_KEYS:
        raise HypothesisGenerationError(
            "provider response must contain only a hypotheses array"
        )
    raw_hypotheses = document["hypotheses"]
    if not isinstance(raw_hypotheses, list):
        raise HypothesisGenerationError("hypotheses must be an array")
    if len(raw_hypotheses) > max_hypotheses:
        raise HypothesisGenerationError("provider returned too many hypotheses")

    return tuple(
        _parse_proposal(raw_proposal, index)
        for index, raw_proposal in enumerate(raw_hypotheses)
    )


def _parse_proposal(raw_proposal: object, index: int) -> _SemanticProposal:
    if not isinstance(raw_proposal, dict) or set(raw_proposal) != _PROPOSAL_KEYS:
        raise HypothesisGenerationError(
            f"hypothesis {index} does not match the required schema"
        )

    semantic_type = raw_proposal["semantic_type"]
    interpretation = raw_proposal["interpretation"]
    parameters = raw_proposal["parameters"]
    confidence = raw_proposal["model_confidence"]

    if not isinstance(semantic_type, str) or not semantic_type.strip():
        raise HypothesisGenerationError(
            f"hypothesis {index} semantic_type must be a non-empty string"
        )
    if not isinstance(interpretation, str) or not interpretation.strip():
        raise HypothesisGenerationError(
            f"hypothesis {index} interpretation must be a non-empty string"
        )
    if not isinstance(parameters, dict):
        raise HypothesisGenerationError(
            f"hypothesis {index} parameters must be an object"
        )
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not math.isfinite(float(confidence))
        or not 0.0 <= float(confidence) <= 1.0
    ):
        raise HypothesisGenerationError(
            f"hypothesis {index} model_confidence must be a finite number in [0, 1]"
        )

    return _SemanticProposal(
        semantic_type=semantic_type.strip(),
        interpretation=interpretation.strip(),
        parameters=dict(parameters),
        model_confidence=float(confidence),
    )


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _validate_candidate(candidate: FieldCandidate) -> None:
    if not isinstance(candidate, FieldCandidate):
        raise TypeError("candidate must use course_project.models.FieldCandidate")
    if not isinstance(candidate.candidate_id, str) or not candidate.candidate_id:
        raise HypothesisGenerationError("candidate_id must not be empty")
    if (
        isinstance(candidate.offset, bool)
        or not isinstance(candidate.offset, int)
        or candidate.offset < 0
    ):
        raise HypothesisGenerationError("candidate offset must be non-negative")
    if candidate.size is not None and (
        isinstance(candidate.size, bool)
        or not isinstance(candidate.size, int)
        or candidate.size <= 0
    ):
        raise HypothesisGenerationError("candidate size must be positive or None")
    if candidate.endian not in (None, "big", "little"):
        raise HypothesisGenerationError("candidate endian must be big, little, or None")
    if not isinstance(candidate.candidate_types, tuple):
        raise HypothesisGenerationError("candidate_types must be a tuple")
    if any(not isinstance(item, str) or not item.strip() for item in candidate.candidate_types):
        raise HypothesisGenerationError(
            "candidate_types must contain only non-empty strings"
        )
    if not isinstance(candidate.evidence_ids, tuple):
        raise HypothesisGenerationError("evidence_ids must be a tuple")
    if any(not isinstance(item, str) or not item for item in candidate.evidence_ids):
        raise HypothesisGenerationError(
            "evidence_ids must contain only non-empty strings"
        )


def _hypothesis_id(
    candidate: FieldCandidate, proposal: _SemanticProposal
) -> str:
    identity: Mapping[str, object] = {
        "candidate_id": candidate.candidate_id,
        "offset": candidate.offset,
        "size": candidate.size,
        "semantic_type": proposal.semantic_type,
        "interpretation": proposal.interpretation,
        "parameters": proposal.parameters,
    }
    canonical = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]
    return f"hypothesis-{digest}"
