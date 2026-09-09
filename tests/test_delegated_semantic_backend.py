from __future__ import annotations

import json
from pathlib import Path

from course_project.models import InputMetadata, VerifiedField
from course_project.sidecar import DeterministicTrackCSemanticBackend, TrackDBaselineBackend
from course_project.verification.provisional_parser import ParseSample, execute_provisional_schema


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


def _verified_fields(schema: dict) -> tuple[VerifiedField, ...]:
    return tuple(
        VerifiedField(
            field_id=str(item["fieldId"]),
            offset=int(item["offset"]),
            size=None if item["size"] is None else int(item["size"]),
            semantic_type=str(item["semanticType"]),
            interpretation=str(item["interpretation"]),
            verification_score=float(item["verificationScore"]),
            evidence_ids=tuple(str(value) for value in item.get("evidenceIds", ())),
        )
        for item in schema["fields"]
    )


def test_delegated_backend_runs_real_verification_and_global_selection(tmp_path: Path) -> None:
    messages = tuple(
        _make_message(0x01, index + 1, b"P" * 8) for index in range(4)
    )
    sample = tmp_path / "sample.dat"
    sample_bytes = b"".join(messages)
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
    assert semantic_metrics["fusionExecuted"] is True
    assert semantic_metrics["fusionPolicy"] == "transparent-component-mean-v1"
    assert semantic_metrics["globalSelectionExecuted"] is True
    assert semantic_metrics["globalSelectionPolicy"] == "pareto-overlap-abstention-v1"

    # The per-hypothesis scientific audit is preserved even when final schema
    # promotion abstains on mutually incompatible accepted ranges.
    assert semantic_metrics["decisionCounts"]["accepted"] >= 2
    assert semantic_metrics["verificationDecisionCounts"]["accepted"] >= 2
    assert semantic_metrics["fusionAcceptedHypothesisCount"] >= 2
    assert semantic_metrics["globalConflictGroupCount"] >= 1
    assert semantic_metrics["globalConflictHypothesisCount"] >= 2
    assert semantic_metrics["globalAbstainedHypothesisCount"] >= 2
    assert semantic_metrics["globalSelectionAudit"]
    assert any(
        item["reason"] == "ambiguous_overlap_conflict"
        for item in semantic_metrics["globalSelectionAudit"]
    )

    assert result.metrics["verifiedFieldCount"] >= 1
    assert result.metrics["verifiedFieldCount"] == semantic_metrics["globallySelectedFieldCount"]
    assert any(finding.semantic_type == "length" for finding in result.findings)
    assert any(finding.semantic_type == "sequence" for finding in result.findings)
    assert all(
        finding.status in {"accepted", "rejected", "uncertain"}
        for finding in result.findings
    )
    assert all("evidence" in finding.scores for finding in result.findings)
    assert all("verification" in finding.scores for finding in result.findings)
    assert any(
        finding.status == "accepted" and finding.scores.get("globalSelection") == 0.0
        for finding in result.findings
    )

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
    global_selection_evidence = [
        item
        for item in result.evidence
        if item.source_component == "track-c-global-selection"
    ]
    assert candidate_evidence
    assert verification_evidence
    assert global_selection_evidence
    assert any(item.observation["decision"] == "abstained" for item in global_selection_evidence)
    for item in verification_evidence:
        assert len(item.parent_evidence_ids) == 1
        parent_id = item.parent_evidence_ids[0]
        assert parent_id in candidate_evidence
        assert item.independence_group == candidate_evidence[parent_id].independence_group
    assert all(item.parent_evidence_ids for item in global_selection_evidence)

    evidence_by_id = {item.evidence_id: item for item in result.evidence}
    finding_producers = [
        {evidence_by_id[evidence_id].source_component for evidence_id in finding.evidence_ids}
        for finding in result.findings
    ]
    assert any(
        producers
        >= {
            "track-d-alignment",
            "track-d-field-candidate",
            "track-c-executable-verifier",
            "track-c-global-selection",
        }
        for producers in finding_producers
    )
    assert set(semantic_metrics["fusionEvidenceProducers"]) >= {
        "track-d-alignment",
        "track-d-field-candidate",
        "track-c-executable-verifier",
    }
    assert semantic_metrics["fusionEvidenceProducerCount"] >= 3
    assert semantic_metrics["fusionAudit"]

    schema_artifact = next(artifact for artifact in result.artifacts if artifact.type == "schema")
    schema = json.loads((state_dir / schema_artifact.ref).read_text(encoding="utf-8"))
    fields = _verified_fields(schema)
    assert fields

    # This is the #70 regression: final production output itself must now be a
    # structurally executable schema; the test does not prune overlaps first.
    report = execute_provisional_schema(
        fields,
        tuple(
            ParseSample(sample_id=f"message-{index}", payload=message)
            for index, message in enumerate(messages)
        ),
        corpus_id="synthetic-global-selection-regression",
        corpus_kind="synthetic",
    )
    assert report.parse_coverage == 1.0

    finite_fields = [field for field in fields if field.size is not None]
    for index, left in enumerate(finite_fields):
        assert left.size is not None
        left_end = left.offset + left.size
        for right in finite_fields[index + 1 :]:
            assert right.size is not None
            right_end = right.offset + right.size
            assert not (left.offset < right_end and right.offset < left_end)


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
