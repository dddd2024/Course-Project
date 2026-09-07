from __future__ import annotations

from pathlib import PurePosixPath

from course_project.models import AnalysisResult, Evidence


def validate_controlled_ref(ref: str) -> str:
    """Reject absolute/traversing references before exposing them to the desktop."""

    if not ref or "\\" in ref:
        raise ValueError("controlled refs must be non-empty POSIX-style relative paths")
    path = PurePosixPath(ref)
    if (
        not path.parts
        or path == PurePosixPath(".")
        or path.is_absolute()
        or ".." in path.parts
        or ":" in path.parts[0]
    ):
        raise ValueError("controlled refs must be normal relative paths without traversal")
    return ref


def validate_task_local_ref(ref: str, *, task_id: str, label: str) -> str:
    """Require a controlled ref to stay inside one task's result directory."""

    validate_controlled_ref(ref)
    path = PurePosixPath(ref)
    expected_prefix = ("tasks", task_id)
    if len(path.parts) < 3 or path.parts[:2] != expected_prefix:
        raise ValueError(f"{label} must stay under tasks/{task_id}/")
    return ref


def _require_unique_nonempty(values: list[str], *, label: str) -> set[str]:
    if any(not value for value in values):
        raise ValueError(f"{label} must be non-empty")
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique within an AnalysisResult")
    return set(values)


def _validate_evidence_graph(evidence: tuple[Evidence, ...]) -> set[str]:
    evidence_ids = _require_unique_nonempty(
        [item.evidence_id for item in evidence],
        label="evidence IDs",
    )
    parents_by_id: dict[str, tuple[str, ...]] = {}

    for item in evidence:
        parents = item.parent_evidence_ids
        if len(parents) != len(set(parents)):
            raise ValueError(
                f"evidence {item.evidence_id} parentEvidenceIds must not contain duplicates"
            )
        missing = set(parents) - evidence_ids
        if missing:
            names = ", ".join(sorted(missing))
            raise ValueError(f"evidence {item.evidence_id} references missing parents: {names}")
        if item.evidence_id in parents:
            raise ValueError(f"evidence {item.evidence_id} cannot reference itself as a parent")
        if len(item.sample_ids) != len(set(item.sample_ids)):
            raise ValueError(f"evidence {item.evidence_id} sampleIds must not contain duplicates")
        parents_by_id[item.evidence_id] = parents

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(evidence_id: str) -> None:
        if evidence_id in visiting:
            raise ValueError("evidence parent graph must be acyclic")
        if evidence_id in visited:
            return
        visiting.add(evidence_id)
        for parent_id in parents_by_id[evidence_id]:
            visit(parent_id)
        visiting.remove(evidence_id)
        visited.add(evidence_id)

    for evidence_id in evidence_ids:
        visit(evidence_id)

    return evidence_ids


def validate_analysis_result_integrity(result: AnalysisResult) -> None:
    """Validate cross-record invariants that JSON Schema cannot express by itself."""

    if not result.task_id:
        raise ValueError("AnalysisResult task_id must be non-empty")
    if result.input_id is not None and not result.input_id:
        raise ValueError("AnalysisResult input_id must be non-empty when present")

    evidence_ids = _validate_evidence_graph(result.evidence)

    finding_ids = _require_unique_nonempty(
        [item.finding_id for item in result.findings],
        label="finding IDs",
    )
    del finding_ids

    for finding in result.findings:
        if not finding.claim:
            raise ValueError(f"finding {finding.finding_id} claim must be non-empty")
        if len(finding.evidence_ids) != len(set(finding.evidence_ids)):
            raise ValueError(
                f"finding {finding.finding_id} evidenceIds must not contain duplicates"
            )
        missing = set(finding.evidence_ids) - evidence_ids
        if missing:
            names = ", ".join(sorted(missing))
            raise ValueError(f"finding {finding.finding_id} references missing evidence: {names}")

        location = finding.location
        if location is not None:
            if location.offset < 0 or location.length < 0:
                raise ValueError(f"finding {finding.finding_id} location must be non-negative")
            if result.input_id is None:
                raise ValueError(
                    f"finding {finding.finding_id} has a location but AnalysisResult has no input_id"
                )
            if location.input_id != result.input_id:
                raise ValueError(
                    f"finding {finding.finding_id} location inputId does not match AnalysisResult input_id"
                )

    _require_unique_nonempty(
        [item.artifact_id for item in result.artifacts],
        label="artifact IDs",
    )
    for artifact in result.artifacts:
        validate_task_local_ref(
            artifact.ref,
            task_id=result.task_id,
            label=f"artifact {artifact.artifact_id} ref",
        )

    if result.result_ref is not None:
        validate_task_local_ref(result.result_ref, task_id=result.task_id, label="resultRef")
        expected = f"tasks/{result.task_id}/analysis-result.json"
        if result.result_ref != expected:
            raise ValueError(f"resultRef must equal {expected}")
