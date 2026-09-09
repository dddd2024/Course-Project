from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from course_project.llm import (
    HypothesisProposal,
    LLMHypothesisRequest,
    LLMProviderResult,
    materialize_hypotheses,
)
from course_project.models import InputMetadata
from course_project.sidecar import DeterministicTrackCSemanticBackend, TrackDBaselineBackend


def _make_message(msg_type: int, seq: int, payload: bytes) -> bytes:
    return (
        b"SYN1"
        + bytes([msg_type])
        + b"\x00\x00\x00"
        + bytes([seq])
        + (11 + len(payload)).to_bytes(2, "big")
        + payload
    )


def _sample(tmp_path: Path) -> tuple[Path, bytes]:
    messages = tuple(_make_message(0x01, index + 1, b"P" * (8 + index)) for index in range(5))
    payload = b"".join(messages)
    path = tmp_path / "sample.dat"
    path.write_bytes(payload)
    return path, payload


def _config(*, llm_enabled: bool) -> dict[str, object]:
    return {
        "mode": "evidencegraph",
        "stages": ["boundary", "inference", "evidence", "verification", "export"],
        "llmEnabled": llm_enabled,
        "verificationEnabled": True,
        "behaviorEnabled": False,
        "optionalDependencyPolicy": "degrade",
    }


def _run(
    tmp_path: Path,
    *,
    backend: DeterministicTrackCSemanticBackend,
    llm_enabled: bool,
):
    sample, payload = _sample(tmp_path)
    return TrackDBaselineBackend(
        state_dir=tmp_path / "state",
        semantic_backend=backend,
    ).analyze(
        task_id="production-llm-path",
        input_metadata=InputMetadata(
            input_id="input-production-llm-path",
            kind="dat",
            size_bytes=len(payload),
        ),
        input_path=sample,
        config=_config(llm_enabled=llm_enabled),
    )


class StructuralLengthProvider:
    provider_name = "structural-length-test"
    mode = "mock"

    def __init__(self) -> None:
        self.requests: list[LLMHypothesisRequest] = []

    def propose(self, request: LLMHypothesisRequest) -> LLMProviderResult:
        self.requests.append(request)
        candidate = request.context["candidate"]
        candidate_types = set(candidate["candidateTypes"])
        if "length" not in candidate_types or candidate["size"] is None:
            return LLMProviderResult(
                provider=self.provider_name,
                mode="mock",
                metadata={"networkAccess": False, "configured": True},
            )

        endian = candidate["declaredEndian"]
        if endian not in {"big", "little"}:
            return LLMProviderResult(provider=self.provider_name, mode="mock")
        match_hint = candidate["matchHint"]
        if match_hint == "total":
            parameters: dict[str, Any] = {"endian": endian, "target": "full_message"}
        elif match_hint == "payload_after":
            parameters = {
                "endian": endian,
                "target": "payload",
                "header_size": candidate["offset"] + candidate["size"],
            }
        else:
            return LLMProviderResult(provider=self.provider_name, mode="mock")

        proposals = [
            HypothesisProposal(
                offset=candidate["offset"],
                size=candidate["size"],
                semantic_type="length",
                interpretation="provider correct endian length",
                parameters=parameters,
                model_confidence=0.61,
                supporting_evidence_ids=request.allowed_evidence_ids,
            )
        ]
        if candidate["size"] > 1:
            wrong = dict(parameters)
            wrong["endian"] = "little" if endian == "big" else "big"
            proposals.append(
                HypothesisProposal(
                    offset=candidate["offset"],
                    size=candidate["size"],
                    semantic_type="length",
                    interpretation="provider deliberately wrong endian length",
                    parameters=wrong,
                    model_confidence=0.97,
                    supporting_evidence_ids=request.allowed_evidence_ids,
                )
            )

        return LLMProviderResult(
            provider=self.provider_name,
            mode="mock",
            hypotheses=materialize_hypotheses(
                provider_name=self.provider_name,
                request=request,
                proposals=tuple(proposals),
            ),
            metadata={
                "networkAccess": False,
                "configured": True,
                "secretLikeValue": "must-not-be-persisted",
            },
        )


class OutOfRegionProvider:
    provider_name = "out-of-region-test"
    mode = "mock"

    def propose(self, request: LLMHypothesisRequest) -> LLMProviderResult:
        candidate = request.context["candidate"]
        hypothesis = materialize_hypotheses(
            provider_name=self.provider_name,
            request=request,
            proposals=(
                HypothesisProposal(
                    offset=candidate["offset"] + 1,
                    size=candidate["size"],
                    semantic_type="length",
                    interpretation="out of requested region",
                    parameters={"endian": "big", "target": "full_message"},
                    model_confidence=0.99,
                    supporting_evidence_ids=request.allowed_evidence_ids,
                ),
            ),
        )
        return LLMProviderResult(
            provider=self.provider_name,
            mode="mock",
            hypotheses=hypothesis,
        )


def test_llm_disabled_never_resolves_provider_and_preserves_deterministic_path(
    tmp_path: Path,
) -> None:
    def forbidden_factory():
        raise AssertionError("LLM provider factory was resolved while llmEnabled=false")

    result = _run(
        tmp_path,
        backend=DeterministicTrackCSemanticBackend(llm_provider_factory=forbidden_factory),
        llm_enabled=False,
    )

    assert result.status == "completed"
    assert result.metrics["semanticExecuted"] is True
    semantic = result.metrics["semanticMetrics"]
    assert "llmRequested" not in semantic
    assert not any(item.source_component == "track-c-llm-provider" for item in result.evidence)


def test_llm_hypotheses_enter_real_verification_fusion_and_ignore_confidence_rank(
    tmp_path: Path,
) -> None:
    provider = StructuralLengthProvider()
    result = _run(
        tmp_path,
        backend=DeterministicTrackCSemanticBackend(llm_provider=provider),
        llm_enabled=True,
    )

    semantic = result.metrics["semanticMetrics"]
    assert semantic["llmRequested"] is True
    assert semantic["llmExecuted"] is True
    assert semantic["llmRequestCount"] == len(provider.requests)
    assert semantic["llmSuccessfulRequestCount"] == len(provider.requests)
    assert semantic["llmHypothesisCount"] >= 2
    assert semantic["llmUnverifiableHypothesisCount"] == 0
    assert semantic["llmContextPolicy"] == "structural-summary-v1"

    # The integration sanitizes provider metadata again rather than trusting an
    # arbitrary provider implementation to avoid persisting credentials/secrets.
    metadata_json = json.dumps(semantic["llmProviderMetadata"], sort_keys=True)
    assert "secretLikeValue" not in metadata_json
    assert "must-not-be-persisted" not in metadata_json

    for request in provider.requests:
        context = request.context
        assert context["privacy"]["wholePayloadIncluded"] is False
        assert context["sampleCountIncluded"] <= 16
        for sample in context["samples"]:
            assert set(sample) <= {
                "sampleId",
                "messageLength",
                "fieldAvailable",
                "fieldByteCount",
                "fieldBytesHex",
                "fieldBytesTruncated",
                "fieldUnsignedBigEndian",
                "fieldUnsignedLittleEndian",
            }
            assert "payload" not in sample

    llm_evidence = [
        item for item in result.evidence if item.source_component == "track-c-llm-provider"
    ]
    assert llm_evidence
    candidate_evidence = {
        item.evidence_id: item
        for item in result.evidence
        if item.source_component == "track-d-field-candidate"
    }
    for item in llm_evidence:
        assert len(item.parent_evidence_ids) == 1
        parent = candidate_evidence[item.parent_evidence_ids[0]]
        assert item.independence_group == parent.independence_group

    evidence_by_hypothesis = {
        item.observation["hypothesisId"]: item
        for item in llm_evidence
        if "hypothesisId" in item.observation
    }
    findings = {
        finding.finding_id.removeprefix("finding:"): finding for finding in result.findings
    }
    correct = [
        (hypothesis_id, evidence)
        for hypothesis_id, evidence in evidence_by_hypothesis.items()
        if evidence.observation["interpretation"] == "provider correct endian length"
        and hypothesis_id in findings
        and findings[hypothesis_id].status == "accepted"
    ]
    wrong = [
        (hypothesis_id, evidence)
        for hypothesis_id, evidence in evidence_by_hypothesis.items()
        if evidence.observation["interpretation"] == "provider deliberately wrong endian length"
        and hypothesis_id in findings
        and findings[hypothesis_id].status == "rejected"
    ]
    assert correct, "at least one provider length hypothesis should be executable and accepted"
    assert wrong, "at least one higher-confidence wrong-endian hypothesis should be rejected"
    assert max(item.observation["modelConfidence"] for _, item in wrong) > max(
        item.observation["modelConfidence"] for _, item in correct
    )

    # LLM hypotheses reach both fusion and final global-selection audit when they
    # are individually accepted. They may conservatively abstain against another
    # accepted interpretation of the same range; that is the intended policy.
    llm_ids = set(evidence_by_hypothesis)
    fusion_ids = {item["hypothesisId"] for item in semantic["fusionAudit"]}
    selection_ids = {item["hypothesisId"] for item in semantic["globalSelectionAudit"]}
    assert llm_ids & fusion_ids
    assert {hypothesis_id for hypothesis_id, _ in correct} & selection_ids


def test_out_of_region_llm_output_fails_closed_without_llm_evidence(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        backend=DeterministicTrackCSemanticBackend(llm_provider=OutOfRegionProvider()),
        llm_enabled=True,
    )

    semantic = result.metrics["semanticMetrics"]
    assert semantic["llmExecuted"] is True
    assert semantic["llmHypothesisCount"] == 0
    assert semantic["llmOutOfScopeHypothesisCount"] >= 1
    assert not any(item.source_component == "track-c-llm-provider" for item in result.evidence)
    assert result.status == "partial"
    assert any("outside the requested executable field region" in item for item in result.limitations)


def test_missing_live_provider_configuration_fails_closed_but_keeps_deterministic_findings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "COURSE_PROJECT_LLM_ENDPOINT",
        "COURSE_PROJECT_LLM_MODEL",
        "COURSE_PROJECT_LLM_API_KEY_ENV",
        "COURSE_PROJECT_LLM_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    result = _run(
        tmp_path,
        backend=DeterministicTrackCSemanticBackend(),
        llm_enabled=True,
    )

    semantic = result.metrics["semanticMetrics"]
    assert semantic["llmRequested"] is True
    assert semantic["llmExecuted"] is False
    assert semantic["llmProviderFailureCount"] == 1
    assert semantic["llmHypothesisCount"] == 0
    assert result.findings, "deterministic verification should still run after live-provider failure"
    assert result.status == "partial"
    assert any("provider could not be initialized" in item for item in result.limitations)
