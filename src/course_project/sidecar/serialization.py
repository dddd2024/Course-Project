from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from course_project.models import AnalysisFinding, AnalysisResult, ArtifactRef, Evidence

_DECISION_TO_PUBLIC = {
    "accepted": "ACCEPTED",
    "rejected": "REJECTED",
    "uncertain": "UNCERTAIN",
}
_TASK_STATUS_TO_PUBLIC = {
    "completed": "COMPLETED",
    "failed": "FAILED",
    "cancelled": "CANCELLED",
    "partial": "PARTIAL",
}
_ALLOWED_SCORE_KEYS = {"model", "evidence", "verification"}


def _check_score(value: float, label: str) -> float:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{label} must be within [0, 1]")
    return value


def validate_controlled_ref(ref: str) -> str:
    """Reject absolute/traversing references before exposing them to the desktop."""

    if not ref or "\\" in ref:
        raise ValueError("controlled refs must be non-empty POSIX-style relative paths")
    path = PurePosixPath(ref)
    if path.is_absolute() or ".." in path.parts or ":" in path.parts[0]:
        raise ValueError("controlled refs must not be absolute or contain traversal")
    return ref


def evidence_to_dict(evidence: Evidence) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "evidenceId": evidence.evidence_id,
        "sourceComponent": evidence.source_component,
        "method": evidence.method,
        "featureFamily": evidence.feature_family,
        "score": _check_score(evidence.score, f"evidence {evidence.evidence_id} score"),
        "observation": evidence.observation,
        "parentEvidenceIds": list(evidence.parent_evidence_ids),
        "independenceGroup": evidence.independence_group,
        "sampleIds": list(evidence.sample_ids),
    }
    return payload


def finding_to_dict(finding: AnalysisFinding) -> dict[str, Any]:
    unknown_score_keys = set(finding.scores) - _ALLOWED_SCORE_KEYS
    if unknown_score_keys:
        names = ", ".join(sorted(unknown_score_keys))
        raise ValueError(f"unsupported finding score keys: {names}")

    payload: dict[str, Any] = {
        "findingId": finding.finding_id,
        "claim": finding.claim,
        "status": _DECISION_TO_PUBLIC[finding.status],
        "evidenceIds": list(finding.evidence_ids),
    }
    if finding.semantic_type is not None:
        payload["semanticType"] = finding.semantic_type
    if finding.location is not None:
        payload["location"] = {
            "inputId": finding.location.input_id,
            "offset": finding.location.offset,
            "length": finding.location.length,
        }
    if finding.scores:
        payload["scores"] = {
            key: _check_score(value, f"finding {finding.finding_id} {key} score")
            for key, value in finding.scores.items()
        }
    return payload


def artifact_to_dict(artifact: ArtifactRef) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "artifactId": artifact.artifact_id,
        "type": artifact.type,
        "format": artifact.format,
        "ref": validate_controlled_ref(artifact.ref),
    }
    if artifact.count is not None:
        if artifact.count < 0:
            raise ValueError("artifact count cannot be negative")
        payload["count"] = artifact.count
    if artifact.metadata:
        payload["metadata"] = artifact.metadata
    return payload


def analysis_result_to_dict(result: AnalysisResult) -> dict[str, Any]:
    """Convert project-native result DTOs into the frozen cross-language JSON shape."""

    evidence_ids = [item.evidence_id for item in result.evidence]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("evidence IDs must be unique within an AnalysisResult")
    available_evidence = set(evidence_ids)
    for finding in result.findings:
        missing = set(finding.evidence_ids) - available_evidence
        if missing:
            names = ", ".join(sorted(missing))
            raise ValueError(f"finding {finding.finding_id} references missing evidence: {names}")

    artifact_ids = [item.artifact_id for item in result.artifacts]
    if len(artifact_ids) != len(set(artifact_ids)):
        raise ValueError("artifact IDs must be unique within an AnalysisResult")

    payload: dict[str, Any] = {
        "protocolVersion": 1,
        "taskId": result.task_id,
        "status": _TASK_STATUS_TO_PUBLIC[result.status],
        "findings": [finding_to_dict(item) for item in result.findings],
        "evidence": [evidence_to_dict(item) for item in result.evidence],
        "artifacts": [artifact_to_dict(item) for item in result.artifacts],
        "metrics": result.metrics,
        "limitations": list(result.limitations),
    }
    if result.input_id is not None:
        payload["inputId"] = result.input_id
    if result.result_ref is not None:
        payload["resultRef"] = validate_controlled_ref(result.result_ref)
    return payload
