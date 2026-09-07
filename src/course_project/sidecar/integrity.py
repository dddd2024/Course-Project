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

    # Iterative three-color DFS avoids Python recursion limits on deep, valid provenance chains.
    # 0/unset = unvisited, 1 = active DFS path, 2 = fully processed.
    state: dict[str, int] = {}
    for root_id in evidence_ids:
        if state.get(root_id) == 2:
            continue
        state[root_id] = 1
        stack: list[tuple[str, int]] = [(root_id, 0)]
        while stack:
            evidence_id, parent_index = stack[-1]
            parents = parents_by_id[evidence_id]
            if parent_index >= len(parents):
                state[evidence_id] = 2
                stack.pop()
                continue

            parent_id = parents[parent_index]
            stack[-1] = (evidence_id, parent_index + 1)
            parent_state = state.get(parent_id, 0)
            if parent_state == 1:
                raise ValueError("evidence parent graph must be acyclic")
            if parent_state == 0:
                state[parent_id] = 1
                stack.append((parent_id, 0))

    return evidence_ids


def validate_analysis_result_integrity(result: AnalysisResult) -> None:
    """Validate cross-record invariants that JSON Schema cannot express by itself."""

    if not result.task_id:
        raise ValueError("AnalysisResult task_id must be non-empty")
    if result.input_id is not None and not result.input_id:
        raise ValueError("AnalysisResult input_id must be non-empty when present")

    evidence_ids = _validate_evidence_graph(result.evidence)

    _require_unique_nonempty(
        [item.finding_id for item in result.findings],
        label="finding IDs",
    )

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
        validate_controlled_ref(artifact.ref)

    if result.result_ref is not None:
        validate_controlled_ref(result.result_ref)
