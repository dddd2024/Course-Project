from __future__ import annotations

import json
from pathlib import Path

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


def _semantic_config() -> dict[str, object]:
    return {
        "mode": "evidencegraph",
        "stages": ["boundary", "inference", "evidence", "verification", "export"],
        "llmEnabled": False,
        "verificationEnabled": True,
        "behaviorEnabled": False,
        "optionalDependencyPolicy": "degrade",
    }


def test_delegated_backend_runs_real_length_sequence_verification(tmp_path: Path) -> None:
    sample = tmp_path / "sample.dat"
    sample_bytes = b"".join(
        _make_message(0x01, index + 1, b"P" * 8) for index in range(4)
    )
    sample.write_bytes(sample_bytes)
    state_dir = tmp_path / "state"

    result = TrackDBaselineBackend(
        state_dir=state_dir,
        semantic_backend=DeterministicTrackCSemanticBackend(),
    ).analyze(
        task_id="delegated-semantic",
        input_metadata=InputMetadata(
            input_id="input-delegated-semantic",
            kind="dat",
            size_bytes=len(sample_bytes),
        ),
        input_path=sample,
        config=_semantic_config(),
    )

    assert result.status == "completed"
    assert result.metrics["semanticExecuted"] is True
    assert result.metrics["semanticBackend"] == "track-a-delegated-track-c-semantic-v1"
    semantic_metrics = result.metrics["semanticMetrics"]
    assert semantic_metrics["verificationExecuted"] is True
    assert semantic_metrics["decisionCounts"]["accepted"] >= 2
    assert result.metrics["verifiedFieldCount"] >= 2
    assert any(finding.semantic_type == "length" for finding in result.findings)
    assert any(finding.semantic_type == "sequence" for finding in result.findings)
    assert all(finding.status in {"accepted", "rejected", "uncertain"} for finding in result.findings)

    candidate_evidence = {
        item.evidence_id: item
        for item in result.evidence
        if item.source_component == "track-d-field-candidate"
    }
    verification_evidence = [
        item
        for item in result.evidence
        if item.source_component == "track-c-executable-verifier"
    ]
    assert candidate_evidence
    assert verification_evidence
    for item in verification_evidence:
        assert len(item.parent_evidence_ids) == 1
        parent_id = item.parent_evidence_ids[0]
        assert parent_id in candidate_evidence
        assert item.independence_group == candidate_evidence[parent_id].independence_group

    schema_artifact = next(artifact for artifact in result.artifacts if artifact.type == "schema")
    schema = json.loads((state_dir / schema_artifact.ref).read_text(encoding="utf-8"))
    assert schema["fields"]
    assert {field["semanticType"] for field in schema["fields"]} >= {"length", "sequence"}


def test_delegated_backend_respects_disabled_verification(tmp_path: Path) -> None:
    sample = tmp_path / "sample.dat"
    payload = b"".join(_make_message(0x01, index + 1, b"P" * 8) for index in range(4))
    sample.write_bytes(payload)

    result = TrackDBaselineBackend(
        state_dir=tmp_path / "state",
        semantic_backend=DeterministicTrackCSemanticBackend(),
    ).analyze(
        task_id="verification-disabled",
        input_metadata=InputMetadata(
            input_id="input-verification-disabled",
            kind="dat",
            size_bytes=len(payload),
        ),
        input_path=sample,
        config={
            "mode": "baseline",
            "stages": ["boundary", "inference", "evidence"],
            "llmEnabled": False,
            "verificationEnabled": False,
            "behaviorEnabled": False,
            "optionalDependencyPolicy": "degrade",
        },
    )

    assert result.status == "partial"
    assert result.metrics["semanticExecuted"] is True
    assert result.metrics["verifiedFieldCount"] == 0
    assert result.findings == ()
    assert result.evidence == ()
    assert result.limitations
