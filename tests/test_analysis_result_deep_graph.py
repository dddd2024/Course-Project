from __future__ import annotations

from course_project.models import AnalysisResult, Evidence
from course_project.sidecar.serialization import analysis_result_to_dict


def test_deep_evidence_parent_chain_serializes_without_recursion_error() -> None:
    depth = 5_000
    evidence = []
    for index in range(depth):
        evidence_id = f"ev-{index:04d}"
        parents = () if index == 0 else (f"ev-{index - 1:04d}",)
        evidence.append(
            Evidence(
                evidence_id=evidence_id,
                source_component="deep-chain-test",
                method="synthetic",
                feature_family="provenance",
                parent_evidence_ids=parents,
            )
        )

    result = AnalysisResult(
        task_id="task-deep-evidence",
        status="completed",
        evidence=tuple(evidence),
    )

    payload = analysis_result_to_dict(result)

    assert len(payload["evidence"]) == depth
    assert payload["evidence"][-1]["parentEvidenceIds"] == [f"ev-{depth - 2:04d}"]
