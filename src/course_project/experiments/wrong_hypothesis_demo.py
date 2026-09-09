"""Executable engineering example: verification overrides model confidence.

This module intentionally uses the deterministic mock provider. It demonstrates the
project mechanism without network access, API credentials, teacher data, or a live-LLM
performance claim.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

from course_project.llm import (
    DeterministicMockLLMProvider,
    HypothesisProposal,
    LLMHypothesisRequest,
)
from course_project.verification import verification_result, verify_length

VerificationStatus = Literal["accepted", "rejected", "uncertain"]

_REQUEST_ID = "engineering-wrong-length-hypothesis-v1"
_INPUT_ID = "synthetic-wrong-hypothesis-v1"
_EVIDENCE_ID = "engineering-evidence:length-field"


@dataclass(frozen=True, slots=True)
class EngineeringHypothesisOutcome:
    """One model proposal paired with its executable verification result."""

    hypothesis_id: str
    interpretation: str
    endian: str
    model_confidence: float
    verification_status: VerificationStatus
    verification_score: float
    sample_count: int
    support_count: int
    violation_count: int
    supporting_evidence_ids: tuple[str, ...]
    competing_hypothesis_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WrongHypothesisEngineeringDemo:
    """Deterministic audit record for the confidence-vs-verification example."""

    corpus_sha256: str
    sample_count: int
    provider: str
    provider_mode: str
    network_access: bool
    highest_confidence_hypothesis_id: str
    supported_hypothesis_ids: tuple[str, ...]
    outcomes: tuple[EngineeringHypothesisOutcome, ...]


def run_wrong_hypothesis_engineering_demo() -> WrongHypothesisEngineeringDemo:
    """Show that a plausible higher-confidence wrong endian guess is rejected.

    The fixed corpus stores total message length as an unsigned two-byte big-endian
    field at offset zero. The mock provider deliberately proposes the correct
    big-endian interpretation with lower model confidence and a wrong little-endian
    interpretation with higher confidence. Both proposals pass through the normal
    ``LLMHypothesisProvider`` materialization boundary before the same executable
    verifier evaluates them.
    """

    messages = _fixed_messages()
    request = LLMHypothesisRequest(
        request_id=_REQUEST_ID,
        input_id=_INPUT_ID,
        allowed_evidence_ids=(_EVIDENCE_ID,),
        context={
            "sampleCount": len(messages),
            "field": {"offset": 0, "size": 2},
            "claimBoundary": "engineering-mechanism-only",
        },
    )
    provider = DeterministicMockLLMProvider(
        {
            _REQUEST_ID: (
                HypothesisProposal(
                    offset=0,
                    size=2,
                    semantic_type="length",
                    interpretation="big-endian total message length",
                    parameters={"endian": "big", "target": "full_message"},
                    model_confidence=0.62,
                    supporting_evidence_ids=(_EVIDENCE_ID,),
                ),
                HypothesisProposal(
                    offset=0,
                    size=2,
                    semantic_type="length",
                    interpretation="little-endian total message length",
                    parameters={"endian": "little", "target": "full_message"},
                    model_confidence=0.93,
                    supporting_evidence_ids=(_EVIDENCE_ID,),
                ),
            )
        },
        provider_name="engineering-deterministic-mock",
    )
    provider_result = provider.propose(request)

    outcomes: list[EngineeringHypothesisOutcome] = []
    for hypothesis in provider_result.hypotheses:
        check = verify_length(hypothesis, messages)
        result = verification_result(check)
        endian = hypothesis.parameters.get("endian")
        if endian not in {"big", "little"}:
            raise RuntimeError("engineering hypothesis lost its endian parameter")
        outcomes.append(
            EngineeringHypothesisOutcome(
                hypothesis_id=hypothesis.hypothesis_id,
                interpretation=hypothesis.interpretation,
                endian=str(endian),
                model_confidence=hypothesis.model_confidence,
                verification_status=result.status,
                verification_score=result.score,
                sample_count=result.sample_count,
                support_count=result.support_count,
                violation_count=check.violation_count,
                supporting_evidence_ids=hypothesis.supporting_evidence_ids,
                competing_hypothesis_ids=hypothesis.competing_hypothesis_ids,
            )
        )

    if not outcomes:
        raise RuntimeError("engineering provider emitted no hypotheses")
    highest_confidence = max(
        outcomes,
        key=lambda item: (item.model_confidence, item.hypothesis_id),
    )
    supported = tuple(
        item.hypothesis_id
        for item in outcomes
        if item.verification_status == "accepted"
    )
    return WrongHypothesisEngineeringDemo(
        corpus_sha256=hashlib.sha256(b"".join(messages)).hexdigest(),
        sample_count=len(messages),
        provider=provider_result.provider,
        provider_mode=provider_result.mode,
        network_access=bool(provider_result.metadata.get("networkAccess")),
        highest_confidence_hypothesis_id=highest_confidence.hypothesis_id,
        supported_hypothesis_ids=supported,
        outcomes=tuple(outcomes),
    )


def _fixed_messages() -> tuple[bytes, ...]:
    messages: list[bytes] = []
    for payload_size in range(3, 8):
        payload = b"P" * payload_size
        total = 4 + len(payload)
        messages.append(total.to_bytes(2, "big") + b"\x01\x00" + payload)
    return tuple(messages)
