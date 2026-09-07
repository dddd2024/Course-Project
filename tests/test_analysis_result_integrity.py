from __future__ import annotations

from dataclasses import replace

import pytest

from course_project.models import (
    AnalysisFinding,
    AnalysisResult,
    ArtifactRef,
    ByteLocation,
    Evidence,
)
from course_project.sidecar.serialization import analysis_result_to_dict


def _evidence(
    evidence_id: str,
    *,
    parents: tuple[str, ...] = (),
    sample_ids: tuple[str, ...] = (),
) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        source_component="integrity-test",
        method="synthetic",
        feature_family="test",
        score=0.8,
        parent_evidence_ids=parents,
        sample_ids=sample_ids,
    )


def _valid_result() -> AnalysisResult:
    root = _evidence("ev-root", sample_ids=("sample-1",))
    derived = _evidence("ev-derived", parents=(root.evidence_id,))
    finding = AnalysisFinding(
        finding_id="finding-1",
        claim="verified test claim",
        status="accepted",
        evidence_ids=(derived.evidence_id,),
        location=ByteLocation(input_id="input-1", offset=0, length=4),
    )
    artifact = ArtifactRef(
        artifact_id="artifact-1",
        type="report",
        format="json",
        ref="tasks/task-integrity/report.json",
    )
    return AnalysisResult(
        task_id="task-integrity",
        status="completed",
        input_id="input-1",
        result_ref="tasks/task-integrity/analysis-result.json",
        findings=(finding,),
        evidence=(root, derived),
        artifacts=(artifact,),
    )


def test_valid_analysis_result_integrity_serializes() -> None:
    payload = analysis_result_to_dict(_valid_result())

    assert payload["taskId"] == "task-integrity"
    assert payload["findings"][0]["evidenceIds"] == ["ev-derived"]
    assert payload["evidence"][1]["parentEvidenceIds"] == ["ev-root"]
    assert payload["artifacts"][0]["ref"] == "tasks/task-integrity/report.json"


def test_duplicate_finding_ids_are_rejected() -> None:
    result = _valid_result()
    duplicate = replace(result.findings[0], claim="second claim")
    result.findings = (result.findings[0], duplicate)

    with pytest.raises(ValueError, match="finding IDs must be unique"):
        analysis_result_to_dict(result)


def test_evidence_parent_must_exist() -> None:
    result = _valid_result()
    result.evidence = (_evidence("ev-child", parents=("missing-parent",)),)
    result.findings = ()

    with pytest.raises(ValueError, match="references missing parents"):
        analysis_result_to_dict(result)


def test_evidence_parent_graph_must_be_acyclic() -> None:
    result = _valid_result()
    result.evidence = (
        _evidence("ev-a", parents=("ev-b",)),
        _evidence("ev-b", parents=("ev-a",)),
    )
    result.findings = ()

    with pytest.raises(ValueError, match="must be acyclic"):
        analysis_result_to_dict(result)


def test_duplicate_evidence_links_and_samples_are_rejected() -> None:
    result = _valid_result()
    result.findings = (
        replace(result.findings[0], evidence_ids=("ev-derived", "ev-derived")),
    )
    with pytest.raises(ValueError, match="evidenceIds must not contain duplicates"):
        analysis_result_to_dict(result)

    result = _valid_result()
    result.evidence = (
        _evidence("ev-root", sample_ids=("sample-1", "sample-1")),
    )
    result.findings = ()
    with pytest.raises(ValueError, match="sampleIds must not contain duplicates"):
        analysis_result_to_dict(result)


def test_finding_location_must_match_result_input() -> None:
    result = _valid_result()
    result.findings = (
        replace(
            result.findings[0],
            location=ByteLocation(input_id="input-other", offset=0, length=4),
        ),
    )

    with pytest.raises(ValueError, match="does not match AnalysisResult input_id"):
        analysis_result_to_dict(result)


def test_artifact_refs_must_be_task_local_and_controlled() -> None:
    result = _valid_result()
    result.artifacts = (
        replace(result.artifacts[0], ref="tasks/other-task/report.json"),
    )
    with pytest.raises(ValueError, match="must stay under tasks/task-integrity/"):
        analysis_result_to_dict(result)

    result = _valid_result()
    result.artifacts = (
        replace(result.artifacts[0], ref="../escape.json"),
    )
    with pytest.raises(ValueError, match="without traversal"):
        analysis_result_to_dict(result)


def test_result_ref_must_be_canonical_for_task() -> None:
    result = _valid_result()
    result.result_ref = "tasks/task-integrity/other-result.json"

    with pytest.raises(ValueError, match="resultRef must equal"):
        analysis_result_to_dict(result)


def test_duplicate_artifact_ids_are_rejected() -> None:
    result = _valid_result()
    duplicate = replace(result.artifacts[0], ref="tasks/task-integrity/report-2.json")
    result.artifacts = (result.artifacts[0], duplicate)

    with pytest.raises(ValueError, match="artifact IDs must be unique"):
        analysis_result_to_dict(result)
