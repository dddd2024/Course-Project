from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from course_project.models import (
    AnalysisFinding,
    ByteLocation,
    Evidence,
    InputMetadata,
    VerifiedField,
)
from course_project.sidecar import SemanticAnalysis, SidecarRuntime, TrackDBaselineBackend
from course_project.sidecar.serialization import analysis_result_to_dict


def _make_message(msg_type: int, seq: int, payload: bytes) -> bytes:
    return (
        b"SYN1"
        + bytes([msg_type])
        + b"\x00\x00\x00"
        + bytes([seq])
        + (11 + len(payload)).to_bytes(2, "big")
        + payload
    )


def _write_sample(path: Path) -> bytes:
    payload = b"".join(_make_message(0x01, index + 1, b"P" * 8) for index in range(4))
    path.write_bytes(payload)
    return payload


def _semantic_config() -> dict[str, Any]:
    return {
        "mode": "evidencegraph",
        "stages": [
            "boundary",
            "inference",
            "evidence",
            "verification",
            "behavior",
            "export",
        ],
        "llmEnabled": False,
        "verificationEnabled": True,
        "behaviorEnabled": True,
        "optionalDependencyPolicy": "degrade",
    }


class _DeterministicSemanticBackend:
    def analyze(self, **kwargs: Any) -> SemanticAnalysis:
        input_metadata = kwargs["input_metadata"]
        messages = kwargs["messages"]
        field_candidates = kwargs["field_candidates"]
        sample_id = messages[0].message_id if messages else "sample-0"
        evidence = Evidence(
            evidence_id="evidence-length-1",
            source_component="test-semantic-backend",
            method="length-check",
            feature_family="length",
            score=0.95,
            observation={"fieldCandidateCount": len(field_candidates)},
            independence_group="length-executable",
            sample_ids=(sample_id,),
        )
        finding = AnalysisFinding(
            finding_id="finding-length-1",
            claim="Bytes 9-10 encode the message length.",
            status="accepted",
            evidence_ids=(evidence.evidence_id,),
            semantic_type="length",
            location=ByteLocation(
                input_id=input_metadata.input_id,
                offset=9,
                length=2,
            ),
            scores={"verification": 0.95},
        )
        verified = VerifiedField(
            field_id="field-length-1",
            offset=9,
            size=2,
            semantic_type="length",
            interpretation="big-endian total message length",
            verification_score=0.95,
            evidence_ids=(evidence.evidence_id,),
        )
        return SemanticAnalysis(
            producer="deterministic-test-semantic-v1",
            status="completed",
            findings=(finding,),
            evidence=(evidence,),
            verified_fields=(verified,),
            metrics={"verificationExecuted": True},
        )


class _InvalidSemanticBackend:
    def analyze(self, **kwargs: Any) -> SemanticAnalysis:
        del kwargs
        return SemanticAnalysis(
            producer="invalid-test-semantic-v1",
            verified_fields=(
                VerifiedField(
                    field_id="field-invalid",
                    offset=0,
                    size=1,
                    semantic_type="constant",
                    interpretation="invalid fixture",
                    verification_score=0.9,
                    evidence_ids=("missing-evidence",),
                ),
            ),
        )


def test_track_d_backend_composes_project_native_semantic_result(tmp_path: Path) -> None:
    sample = tmp_path / "sample.dat"
    sample_bytes = _write_sample(sample)
    state_dir = tmp_path / "state"
    backend = TrackDBaselineBackend(
        state_dir=state_dir,
        semantic_backend=_DeterministicSemanticBackend(),
    )

    result = backend.analyze(
        task_id="semantic-task",
        input_metadata=InputMetadata(
            input_id="input-semantic-test",
            kind="dat",
            size_bytes=len(sample_bytes),
        ),
        input_path=sample,
        config=_semantic_config(),
    )

    assert result.status == "completed"
    assert len(result.findings) == 1
    assert len(result.evidence) == 1
    assert result.metrics["trackDExecuted"] is True
    assert result.metrics["semanticExecuted"] is True
    assert result.metrics["semanticBackend"] == "deterministic-test-semantic-v1"
    assert result.metrics["verifiedFieldCount"] == 1
    assert result.limitations == ()

    artifacts_by_type = {artifact.type: artifact for artifact in result.artifacts}
    assert {"messages", "alignment", "statistics", "behavior", "evidence", "schema"} <= set(
        artifacts_by_type
    )
    schema_artifact = artifacts_by_type["schema"]
    schema = json.loads((state_dir / schema_artifact.ref).read_text(encoding="utf-8"))
    assert schema["schemaVersion"] == 1
    assert schema["fields"][0]["fieldId"] == "field-length-1"
    assert schema["fields"][0]["verificationScore"] == 0.95

    public_result = analysis_result_to_dict(result)
    assert public_result["status"] == "COMPLETED"
    assert public_result["findings"][0]["status"] == "ACCEPTED"
    assert public_result["findings"][0]["evidenceIds"] == ["evidence-length-1"]


def test_invalid_semantic_provenance_fails_closed_through_sidecar(tmp_path: Path) -> None:
    sample = tmp_path / "sample.dat"
    _write_sample(sample)
    state_dir = tmp_path / "state"
    runtime = SidecarRuntime(
        state_dir=state_dir,
        backend=TrackDBaselineBackend(
            state_dir=state_dir,
            semantic_backend=_InvalidSemanticBackend(),
        ),
        allowed_roots=(tmp_path,),
    )

    registered = runtime.handle(
        {
            "protocolVersion": 1,
            "id": "register-semantic",
            "method": "register_input",
            "params": {"sourceRef": str(sample)},
        }
    )
    input_ref = registered[0]["data"]["inputRef"]

    responses = runtime.handle(
        {
            "protocolVersion": 1,
            "id": "task-invalid-semantic",
            "method": "analyze",
            "params": {"inputRef": input_ref, **_semantic_config()},
        }
    )

    assert len(responses) == 1
    assert responses[0]["error"]["code"] == "inference_failed"
    assert responses[0]["error"]["details"]["exceptionType"] == "ValueError"
    assert not (state_dir / "tasks" / "task-invalid-semantic" / "analysis-result.json").exists()


def test_semantic_bridge_rejects_missing_evidence_reference(tmp_path: Path) -> None:
    sample = tmp_path / "sample.dat"
    sample_bytes = _write_sample(sample)
    backend = TrackDBaselineBackend(
        state_dir=tmp_path / "state",
        semantic_backend=_InvalidSemanticBackend(),
    )

    with pytest.raises(ValueError, match="missing evidence"):
        backend.analyze(
            task_id="semantic-invalid-direct",
            input_metadata=InputMetadata(
                input_id="input-invalid-semantic",
                kind="dat",
                size_bytes=len(sample_bytes),
            ),
            input_path=sample,
            config=_semantic_config(),
        )
