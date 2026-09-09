from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from course_project.evidence.global_selection import (
    FieldSelectionCandidate,
    select_globally_consistent_fields,
)
from course_project.evidence.provenance_fusion import (
    ProvenanceFusionResult,
    fuse_hypothesis_evidence,
)
from course_project.experiments.execution import (
    SyntheticMechanismCorpus,
    build_synthetic_mechanism_corpus,
)
from course_project.experiments.full_evidencegraph import (
    DETERMINISTIC_MECHANISM_MODEL_VERSION,
    DETERMINISTIC_MECHANISM_PROVIDER,
    DeterministicEvidenceGraphMechanismProvider,
    _constraint_satisfaction_rate,
    _provider_hypothesis_audit,
    _schema_execution,
    _schema_fields_from_result,
    _semantic_config,
    _validate_code_sha,
    _validate_full_result,
)
from course_project.experiments.no_provenance import _verification_from_evidence
from course_project.models import Evidence, InputMetadata, VerificationResult, VerifiedField
from course_project.sidecar import DeterministicTrackCSemanticBackend, TrackDBaselineBackend

SENSITIVITY_POLICY_VERSION = "fusion-threshold-grid-v1"
SUPPORT_THRESHOLDS = (0.65, 0.75, 0.85)
CONFLICT_THRESHOLDS = (0.15, 0.25, 0.35)
DEFAULT_SUPPORT_THRESHOLD = 0.75
DEFAULT_CONFLICT_THRESHOLD = 0.25


@dataclass(frozen=True, slots=True)
class ThresholdSensitivityPoint:
    acceptance_support_threshold: float
    max_conflict_for_accept: float
    accepted_hypothesis_count: int
    rejected_hypothesis_count: int
    uncertain_hypothesis_count: int
    selected_field_count: int
    selected_field_ranges: tuple[tuple[int, int, str], ...]
    global_conflict_group_count: int
    global_abstained_hypothesis_count: int
    schema_executable: bool
    parse_coverage: float
    constraint_satisfaction_rate: float
    verifier_rejected_hypothesis_count: int
    verifier_rejected_selected_count: int
    fusion_statuses: tuple[tuple[str, str], ...]
    decision_changed_from_default_count: int = 0
    selected_ranges_changed_from_default: bool = False


@dataclass(frozen=True, slots=True)
class ThresholdSensitivityExecution:
    corpus: SyntheticMechanismCorpus
    code_sha: str
    provider_request_count: int
    points: tuple[ThresholdSensitivityPoint, ...]
    default_point_matches_production: bool
    production_selected_field_ranges: tuple[tuple[int, int, str], ...]
    production_parse_coverage: float
    production_constraint_satisfaction_rate: float
    rejected_wrong_hypothesis_count: int
    summary: dict[str, object]


@dataclass(frozen=True, slots=True)
class _ReplayInput:
    hypothesis_id: str
    candidate_id: str
    offset: int
    size: int
    semantic_type: str
    interpretation: str
    verification: VerificationResult
    evidence: tuple[Evidence, ...]
    evidence_ids: tuple[str, ...]


def run_threshold_sensitivity_analysis(
    work_dir: Path,
    *,
    code_sha: str,
) -> ThresholdSensitivityExecution:
    """Replay only production fusion thresholds over one fixed full-method evidence state."""

    _validate_code_sha(code_sha)
    root = work_dir.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    corpus = build_synthetic_mechanism_corpus()
    capture_path = root / "capture.dat"
    capture_path.write_bytes(corpus.capture)

    input_metadata = InputMetadata(
        input_id=corpus.dataset.dataset_id,
        kind="dat",
        size_bytes=len(corpus.capture),
        sha256=corpus.dataset.sha256,
        metadata={"experimentScope": "synthetic-fusion-threshold-sensitivity"},
    )
    provider = DeterministicEvidenceGraphMechanismProvider()
    state_dir = root / "shared-full-method-state"
    result = TrackDBaselineBackend(
        state_dir=state_dir,
        semantic_backend=DeterministicTrackCSemanticBackend(llm_provider=provider),
    ).analyze(
        task_id="synthetic-threshold-sensitivity",
        input_metadata=input_metadata,
        input_path=capture_path,
        config=_semantic_config(),
    )
    semantic = _validate_full_result(
        result,
        expected_messages=len(corpus.messages),
        provider_request_count=len(provider.requests),
    )
    if semantic.get("fusionAcceptanceSupportThreshold") != DEFAULT_SUPPORT_THRESHOLD:
        raise ValueError("production support threshold no longer matches sensitivity default")
    if semantic.get("fusionMaxConflictForAccept") != DEFAULT_CONFLICT_THRESHOLD:
        raise ValueError("production conflict threshold no longer matches sensitivity default")

    provider_audit = _provider_hypothesis_audit(result.evidence, result.findings)
    replay_inputs = _materialize_replay_inputs(result.findings, result.evidence)
    production_fields = _schema_fields_from_result(result, state_dir=state_dir)
    production_ranges = _field_ranges(production_fields)
    production_schema = _schema_execution(production_fields, corpus)
    production_constraint = _constraint_satisfaction_rate(production_fields, result.evidence)

    raw_points = tuple(
        _replay_threshold_point(
            replay_inputs,
            result.evidence,
            corpus,
            acceptance_support_threshold=support_threshold,
            max_conflict_for_accept=conflict_threshold,
        )
        for support_threshold in SUPPORT_THRESHOLDS
        for conflict_threshold in CONFLICT_THRESHOLDS
    )
    if len(raw_points) != 9:
        raise ValueError("threshold sensitivity grid must contain exactly 9 points")

    default_point = next(
        (
            point
            for point in raw_points
            if point.acceptance_support_threshold == DEFAULT_SUPPORT_THRESHOLD
            and point.max_conflict_for_accept == DEFAULT_CONFLICT_THRESHOLD
        ),
        None,
    )
    if default_point is None:
        raise ValueError("production default threshold point is missing from sensitivity grid")

    production_fusion_status = _production_fusion_statuses(semantic)
    default_status = dict(default_point.fusion_statuses)
    default_matches = (
        default_status == production_fusion_status
        and default_point.selected_field_ranges == production_ranges
        and default_point.parse_coverage == production_schema.parse_coverage
        and default_point.constraint_satisfaction_rate == production_constraint
    )
    if not default_matches:
        raise ValueError("default threshold replay does not reproduce production full-method behavior")

    points = tuple(
        replace(
            point,
            decision_changed_from_default_count=sum(
                dict(point.fusion_statuses).get(hypothesis_id) != status
                for hypothesis_id, status in default_point.fusion_statuses
            ),
            selected_ranges_changed_from_default=(
                point.selected_field_ranges != default_point.selected_field_ranges
            ),
        )
        for point in raw_points
    )
    summary = _summarize(points)
    return ThresholdSensitivityExecution(
        corpus=corpus,
        code_sha=code_sha,
        provider_request_count=len(provider.requests),
        points=points,
        default_point_matches_production=True,
        production_selected_field_ranges=production_ranges,
        production_parse_coverage=production_schema.parse_coverage,
        production_constraint_satisfaction_rate=production_constraint,
        rejected_wrong_hypothesis_count=int(provider_audit["rejectedWrongHypothesisCount"]),
        summary=summary,
    )


def write_threshold_sensitivity_execution(
    execution: ThresholdSensitivityExecution,
    output_dir: Path,
) -> Path:
    """Write deterministic mechanism-only threshold-sensitivity evidence."""

    if not isinstance(execution, ThresholdSensitivityExecution):
        raise TypeError("execution must be ThresholdSensitivityExecution")
    target = output_dir.expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    payload = threshold_sensitivity_payload(execution)
    canonical = _canonical_json(payload)
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    (target / "threshold_sensitivity.json").write_text(canonical + "\n", encoding="utf-8")
    manifest = {
        "datasetId": execution.corpus.dataset.dataset_id,
        "datasetSha256": execution.corpus.dataset.sha256,
        "datasetVersion": execution.corpus.dataset.version,
        "analysis": "fusion_threshold_sensitivity",
        "resultScope": "mechanism",
        "formalBenchmark": False,
        "realLLMBenchmark": False,
        "optimizationPerformed": False,
        "model": {
            "provider": DETERMINISTIC_MECHANISM_PROVIDER,
            "version": DETERMINISTIC_MECHANISM_MODEL_VERSION,
        },
        "gridPointCount": len(execution.points),
        "scientificFingerprint": fingerprint,
    }
    (target / "threshold-sensitivity-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def threshold_sensitivity_payload(
    execution: ThresholdSensitivityExecution,
) -> dict[str, object]:
    if not isinstance(execution, ThresholdSensitivityExecution):
        raise TypeError("execution must be ThresholdSensitivityExecution")
    return {
        "analysis": "fusion_threshold_sensitivity",
        "policyVersion": SENSITIVITY_POLICY_VERSION,
        "resultScope": "mechanism",
        "formalBenchmark": False,
        "realLLMBenchmark": False,
        "optimizationPerformed": False,
        "bestThresholdSelected": False,
        "groundTruthDependentMetricsEvaluated": False,
        "dataset": {
            "id": execution.corpus.dataset.dataset_id,
            "sha256": execution.corpus.dataset.sha256,
            "version": execution.corpus.dataset.version,
        },
        "codeSha": execution.code_sha,
        "model": {
            "provider": DETERMINISTIC_MECHANISM_PROVIDER,
            "version": DETERMINISTIC_MECHANISM_MODEL_VERSION,
            "networkAccess": False,
        },
        "materialization": {
            "fullMethodExecutedOnce": True,
            "providerRequestCount": execution.provider_request_count,
            "verificationReusedAcrossGrid": True,
            "evidenceReusedAcrossGrid": True,
            "globalSelectionPolicyHeldConstant": True,
            "schemaExecutionPolicyHeldConstant": True,
        },
        "grid": {
            "acceptanceSupportThresholds": list(SUPPORT_THRESHOLDS),
            "maxConflictForAcceptThresholds": list(CONFLICT_THRESHOLDS),
            "pointCount": len(execution.points),
            "productionDefault": {
                "acceptanceSupportThreshold": DEFAULT_SUPPORT_THRESHOLD,
                "maxConflictForAccept": DEFAULT_CONFLICT_THRESHOLD,
            },
        },
        "defaultPointMatchesProduction": execution.default_point_matches_production,
        "production": {
            "selectedFieldRanges": [list(item) for item in execution.production_selected_field_ranges],
            "parseCoverage": execution.production_parse_coverage,
            "constraintSatisfactionRate": execution.production_constraint_satisfaction_rate,
            "rejectedWrongHypothesisCount": execution.rejected_wrong_hypothesis_count,
        },
        "points": [_point_payload(point) for point in execution.points],
        "summary": dict(execution.summary),
        "claimBoundary": (
            "Synthetic mechanism sensitivity only; no teacher-data accuracy, real-LLM quality, "
            "or synthetic-data threshold optimization claim."
        ),
    }


def threshold_sensitivity_fingerprint(execution: ThresholdSensitivityExecution) -> str:
    return hashlib.sha256(
        _canonical_json(threshold_sensitivity_payload(execution)).encode("utf-8")
    ).hexdigest()


def _materialize_replay_inputs(
    findings: tuple[Any, ...],
    evidence: tuple[Evidence, ...],
) -> tuple[_ReplayInput, ...]:
    evidence_by_id = {item.evidence_id: item for item in evidence}
    replay: list[_ReplayInput] = []
    for finding in findings:
        hypothesis_id = finding.finding_id.removeprefix("finding:")
        relevant = tuple(
            evidence_by_id[evidence_id]
            for evidence_id in finding.evidence_ids
            if evidence_id in evidence_by_id
            and evidence_by_id[evidence_id].source_component != "track-c-global-selection"
        )
        verifier_records = tuple(
            item for item in relevant if item.source_component == "track-c-executable-verifier"
        )
        candidate_records = tuple(
            item for item in relevant if item.source_component == "track-d-field-candidate"
        )
        provider_records = tuple(
            item
            for item in relevant
            if item.source_component == "track-c-llm-provider"
            and item.observation.get("hypothesisId") == hypothesis_id
        )
        if len(verifier_records) != 1 or len(candidate_records) != 1:
            raise ValueError(
                f"hypothesis {hypothesis_id!r} lacks exact candidate/verifier sensitivity mapping"
            )
        if len(provider_records) > 1:
            raise ValueError(f"hypothesis {hypothesis_id!r} maps to multiple provider records")

        verification = _verification_from_evidence(verifier_records[0], hypothesis_id)
        candidate = candidate_records[0]
        base_candidate_id = candidate.observation.get("candidateId")
        if not isinstance(base_candidate_id, str) or not base_candidate_id:
            raise ValueError("candidate evidence has no candidateId")
        if provider_records:
            provider_record = provider_records[0]
            offset = provider_record.observation.get("offset")
            size = provider_record.observation.get("size")
            interpretation = provider_record.observation.get("interpretation")
            candidate_id = f"llm-derived:{base_candidate_id}:{hypothesis_id}"
        else:
            offset = candidate.observation.get("offset")
            size = candidate.observation.get("size")
            interpretation = f"threshold sensitivity {finding.semantic_type} hypothesis"
            candidate_id = base_candidate_id
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ValueError("sensitivity hypothesis has invalid offset")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise ValueError("sensitivity hypothesis has invalid size")
        if not isinstance(interpretation, str) or not interpretation.strip():
            raise ValueError("sensitivity hypothesis has no interpretation")
        if not isinstance(finding.semantic_type, str) or not finding.semantic_type:
            raise ValueError("sensitivity finding has no semantic type")
        replay.append(
            _ReplayInput(
                hypothesis_id=hypothesis_id,
                candidate_id=candidate_id,
                offset=offset,
                size=size,
                semantic_type=finding.semantic_type,
                interpretation=interpretation,
                verification=verification,
                evidence=relevant,
                evidence_ids=tuple(sorted(item.evidence_id for item in relevant)),
            )
        )
    if not replay:
        raise ValueError("full method emitted no hypotheses for threshold sensitivity")
    return tuple(replay)


def _replay_threshold_point(
    replay_inputs: tuple[_ReplayInput, ...],
    full_evidence: tuple[Evidence, ...],
    corpus: SyntheticMechanismCorpus,
    *,
    acceptance_support_threshold: float,
    max_conflict_for_accept: float,
) -> ThresholdSensitivityPoint:
    fusions: list[tuple[_ReplayInput, ProvenanceFusionResult]] = []
    for item in replay_inputs:
        fusion = fuse_hypothesis_evidence(
            item.hypothesis_id,
            item.evidence,
            item.verification,
            acceptance_support_threshold=acceptance_support_threshold,
            max_conflict_for_accept=max_conflict_for_accept,
        )
        fusions.append((item, fusion))

    rejected_verifier = tuple(
        item for item in replay_inputs if item.verification.status == "rejected"
    )
    if any(
        fusion.status != "rejected"
        for item, fusion in fusions
        if item.verification.status == "rejected"
    ):
        raise ValueError("fusion threshold replay overrode an executable-verifier rejection")

    accepted = tuple((item, fusion) for item, fusion in fusions if fusion.status == "accepted")
    selection = select_globally_consistent_fields(
        FieldSelectionCandidate(
            hypothesis_id=item.hypothesis_id,
            candidate_id=item.candidate_id,
            offset=item.offset,
            size=item.size,
            fusion_margin=fusion.margin,
            support_score=fusion.support_score,
            conflict_score=fusion.conflict_score,
            verification_score=item.verification.score,
        )
        for item, fusion in accepted
    )
    selected_ids = set(selection.selected_hypothesis_ids)
    selected = tuple(
        (item, fusion)
        for item, fusion in accepted
        if item.hypothesis_id in selected_ids
    )
    fields = tuple(
        VerifiedField(
            field_id=f"threshold-sensitivity:{item.candidate_id}",
            offset=item.offset,
            size=item.size,
            semantic_type=item.semantic_type,
            interpretation=item.interpretation,
            verification_score=item.verification.score,
            evidence_ids=item.evidence_ids,
        )
        for item, _fusion in selected
    )
    selected_rejected = sum(
        item.verification.status == "rejected" for item, _fusion in selected
    )
    if selected_rejected:
        raise ValueError("globally selected field was rejected by executable verification")

    schema = _schema_execution(fields, corpus)
    constraint_rate = _constraint_satisfaction_rate(fields, full_evidence)
    statuses = tuple(sorted((item.hypothesis_id, fusion.status) for item, fusion in fusions))
    return ThresholdSensitivityPoint(
        acceptance_support_threshold=acceptance_support_threshold,
        max_conflict_for_accept=max_conflict_for_accept,
        accepted_hypothesis_count=sum(status == "accepted" for _, status in statuses),
        rejected_hypothesis_count=sum(status == "rejected" for _, status in statuses),
        uncertain_hypothesis_count=sum(status == "uncertain" for _, status in statuses),
        selected_field_count=len(fields),
        selected_field_ranges=_field_ranges(fields),
        global_conflict_group_count=selection.conflict_group_count,
        global_abstained_hypothesis_count=selection.abstained_hypothesis_count,
        schema_executable=schema.executable,
        parse_coverage=schema.parse_coverage,
        constraint_satisfaction_rate=constraint_rate,
        verifier_rejected_hypothesis_count=len(rejected_verifier),
        verifier_rejected_selected_count=selected_rejected,
        fusion_statuses=statuses,
    )


def _production_fusion_statuses(semantic: dict[str, Any]) -> dict[str, str]:
    rows = semantic.get("fusionAudit")
    if not isinstance(rows, list) or not rows:
        raise TypeError("production fusion audit is missing")
    statuses: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise TypeError("production fusion audit row must be an object")
        hypothesis_id = row.get("hypothesisId")
        status = row.get("status")
        if not isinstance(hypothesis_id, str) or status not in {
            "accepted",
            "rejected",
            "uncertain",
        }:
            raise ValueError("production fusion audit row is invalid")
        if hypothesis_id in statuses:
            raise ValueError("production fusion audit contains duplicate hypothesis ids")
        statuses[hypothesis_id] = str(status)
    return statuses


def _field_ranges(fields: tuple[VerifiedField, ...]) -> tuple[tuple[int, int, str], ...]:
    ranges: list[tuple[int, int, str]] = []
    for field in fields:
        if field.size is None:
            raise ValueError("threshold sensitivity requires fixed-width verified fields")
        ranges.append((field.offset, field.size, field.semantic_type))
    return tuple(sorted(ranges))


def _summarize(points: tuple[ThresholdSensitivityPoint, ...]) -> dict[str, object]:
    stable_points = tuple(
        point
        for point in points
        if point.decision_changed_from_default_count == 0
        and not point.selected_ranges_changed_from_default
    )
    parse_values = [point.parse_coverage for point in points]
    constraint_values = [point.constraint_satisfaction_rate for point in points]
    selected_counts = [point.selected_field_count for point in points]
    return {
        "pointCount": len(points),
        "stablePointCount": len(stable_points),
        "changedPointCount": len(points) - len(stable_points),
        "selectedFieldCountMin": min(selected_counts),
        "selectedFieldCountMax": max(selected_counts),
        "parseCoverageMin": min(parse_values),
        "parseCoverageMax": max(parse_values),
        "constraintSatisfactionRateMin": min(constraint_values),
        "constraintSatisfactionRateMax": max(constraint_values),
        "interpretation": (
            f"{len(stable_points)}/{len(points)} fixed grid points preserve the production-default "
            "fusion decisions and selected field ranges. Changes, if any, are sensitivity evidence "
            "only; no synthetic-data threshold optimum is selected."
        ),
    }


def _point_payload(point: ThresholdSensitivityPoint) -> dict[str, object]:
    return {
        "acceptanceSupportThreshold": point.acceptance_support_threshold,
        "maxConflictForAccept": point.max_conflict_for_accept,
        "decisionCounts": {
            "accepted": point.accepted_hypothesis_count,
            "rejected": point.rejected_hypothesis_count,
            "uncertain": point.uncertain_hypothesis_count,
        },
        "selectedFieldCount": point.selected_field_count,
        "selectedFieldRanges": [list(item) for item in point.selected_field_ranges],
        "globalConflictGroupCount": point.global_conflict_group_count,
        "globalAbstainedHypothesisCount": point.global_abstained_hypothesis_count,
        "schemaExecutable": point.schema_executable,
        "parseCoverage": point.parse_coverage,
        "constraintSatisfactionRate": point.constraint_satisfaction_rate,
        "verifierRejectedHypothesisCount": point.verifier_rejected_hypothesis_count,
        "verifierRejectedSelectedCount": point.verifier_rejected_selected_count,
        "decisionChangedFromDefaultCount": point.decision_changed_from_default_count,
        "selectedRangesChangedFromDefault": point.selected_ranges_changed_from_default,
        "fusionStatuses": [
            {"hypothesisId": hypothesis_id, "status": status}
            for hypothesis_id, status in point.fusion_statuses
        ],
    }


def _canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
