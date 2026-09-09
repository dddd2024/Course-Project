from __future__ import annotations

import json
import platform
from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter
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
    scientific_record_fingerprint,
)
from course_project.experiments.full_evidencegraph import (
    DETERMINISTIC_MECHANISM_MODEL_VERSION,
    DETERMINISTIC_MECHANISM_PROVIDER,
    DeterministicEvidenceGraphMechanismProvider,
    _schema_execution,
    _semantic_config,
    _validate_code_sha,
    _validate_full_result,
)
from course_project.experiments.no_provenance import (
    _control_fusion_audit,
    _verification_from_evidence,
)
from course_project.experiments.records import (
    DatasetIdentity,
    DependencyVersion,
    ExperimentRecord,
    MetricRecord,
    canonical_record_json,
    metric_for_dataset,
)
from course_project.models import Evidence, InputMetadata, VerificationResult, VerifiedField
from course_project.sidecar import DeterministicTrackCSemanticBackend, TrackDBaselineBackend

NO_VERIFICATION_POLICY_VERSION = "transparent-component-mean-no-verifier-v1"
_ACCEPTANCE_SUPPORT_THRESHOLD = 0.75
_MAX_CONFLICT_FOR_ACCEPT = 0.25
_GROUND_TRUTH_METRICS = (
    "packet_boundary_f1",
    "field_boundary_f1",
    "field_semantic_accuracy",
    "false_hypothesis_rate",
    "restoration_accuracy",
    "accepted_field_coverage",
    "risk_coverage",
)


@dataclass(frozen=True, slots=True)
class NoVerificationAblationExecution:
    """Auditable no-verification replay over exact production evidence."""

    corpus: SyntheticMechanismCorpus
    record: ExperimentRecord
    audit: dict[str, object]


@dataclass(frozen=True, slots=True)
class _ReplayCandidate:
    hypothesis_id: str
    candidate_id: str
    offset: int
    size: int
    semantic_type: str
    interpretation: str
    fusion: ProvenanceFusionResult
    evidence_ids: tuple[str, ...]
    control_verification_status: str


def fuse_hypothesis_evidence_without_verification(
    hypothesis_id: str,
    evidence: tuple[Evidence, ...],
    *,
    acceptance_support_threshold: float = _ACCEPTANCE_SUPPORT_THRESHOLD,
    max_conflict_for_accept: float = _MAX_CONFLICT_FOR_ACCEPT,
    minimum_effective_components: int = 1,
) -> ProvenanceFusionResult:
    """Reuse production provenance collapse while deliberately removing verifier gating.

    Executable-verifier records are removed before fusion. An explicit UNCERTAIN
    placeholder is passed only because the production fusion API requires a
    VerificationResult; the experiment then applies the same support/conflict
    thresholds without the verification veto/acceptance gate.
    """

    filtered = tuple(
        item for item in evidence if item.source_component != "track-c-executable-verifier"
    )
    placeholder = VerificationResult(
        hypothesis_id=hypothesis_id,
        status="uncertain",
        score=0.0,
        support_count=0,
        sample_count=0,
        tests={"experimentOnly": "verification-disabled"},
    )
    production_aggregation = fuse_hypothesis_evidence(
        hypothesis_id,
        filtered,
        placeholder,
        acceptance_support_threshold=acceptance_support_threshold,
        max_conflict_for_accept=max_conflict_for_accept,
        minimum_effective_components=minimum_effective_components,
    )
    status = _decision_without_verification(
        support_score=production_aggregation.support_score,
        conflict_score=production_aggregation.conflict_score,
        effective_component_count=production_aggregation.effective_component_count,
        acceptance_support_threshold=acceptance_support_threshold,
        max_conflict_for_accept=max_conflict_for_accept,
        minimum_effective_components=minimum_effective_components,
    )
    return replace(
        production_aggregation,
        status=status,
        policy=NO_VERIFICATION_POLICY_VERSION,
        verification_status="uncertain",
    )


def run_no_verification_ablation(
    work_dir: Path,
    *,
    code_sha: str,
) -> NoVerificationAblationExecution:
    """Execute a one-factor replay that removes executable verification only."""

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
        metadata={"experimentScope": "synthetic-no-verification-ablation"},
    )
    provider = DeterministicEvidenceGraphMechanismProvider()
    state_dir = root / "shared-production-state"
    result = TrackDBaselineBackend(
        state_dir=state_dir,
        semantic_backend=DeterministicTrackCSemanticBackend(llm_provider=provider),
    ).analyze(
        task_id="synthetic-ablation-no-verification",
        input_metadata=input_metadata,
        input_path=capture_path,
        config=_semantic_config(),
    )
    semantic = _validate_full_result(
        result,
        expected_messages=len(corpus.messages),
        provider_request_count=len(provider.requests),
    )
    control_fusion_audit = _control_fusion_audit(semantic)

    replay_started = perf_counter()
    replay_candidates, replay_fusions, control_verification = _replay_without_verification(
        result.findings,
        result.evidence,
    )
    accepted = tuple(
        item for item in replay_candidates if item.fusion.status == "accepted"
    )
    selection = select_globally_consistent_fields(
        FieldSelectionCandidate(
            hypothesis_id=item.hypothesis_id,
            candidate_id=item.candidate_id,
            offset=item.offset,
            size=item.size,
            fusion_margin=item.fusion.margin,
            support_score=item.fusion.support_score,
            conflict_score=item.fusion.conflict_score,
            verification_score=0.0,
        )
        for item in accepted
    )
    selected_ids = set(selection.selected_hypothesis_ids)
    fields = tuple(
        VerifiedField(
            field_id=f"no-verification:{item.candidate_id}",
            offset=item.offset,
            size=item.size,
            semantic_type=item.semantic_type,
            interpretation=item.interpretation,
            verification_score=0.0,
            evidence_ids=item.evidence_ids,
        )
        for item in accepted
        if item.hypothesis_id in selected_ids
    )
    replay_elapsed = perf_counter() - replay_started

    schema = _schema_execution(fields, corpus)
    control_status = {
        str(row["hypothesisId"]): str(row["status"]) for row in control_fusion_audit
    }
    decision_changed_count = sum(
        control_status.get(item.hypothesis_id) != item.status for item in replay_fusions
    )
    wrong_audit = _wrong_hypothesis_effect(
        result.evidence,
        replay_fusions,
        control_verification,
    )
    dependencies = (
        DependencyVersion(name="course-project", version="0.1.0"),
        DependencyVersion(name="python", version=platform.python_version()),
    )
    record = _ablation_record(
        corpus.dataset,
        code_sha=code_sha,
        schema_executable=schema.executable,
        schema_error=schema.error,
        parse_coverage=schema.parse_coverage,
        processing_time_seconds=replay_elapsed,
        dependencies=dependencies,
        semantic=semantic,
        field_count=len(fields),
        decision_changed_count=decision_changed_count,
    )
    audit: dict[str, object] = {
        "datasetId": corpus.dataset.dataset_id,
        "datasetSha256": corpus.dataset.sha256,
        "variant": "ablation_no_verification",
        "resultScope": "mechanism",
        "provider": DETERMINISTIC_MECHANISM_PROVIDER,
        "modelVersion": DETERMINISTIC_MECHANISM_MODEL_VERSION,
        "networkAccess": False,
        "realLLMBenchmark": False,
        "teacherBenchmark": False,
        "controlVerificationExecuted": semantic.get("verificationExecuted"),
        "ablationVerificationExecuted": False,
        "controlFusionPolicy": semantic.get("fusionPolicy"),
        "ablationFusionPolicy": NO_VERIFICATION_POLICY_VERSION,
        "provenanceCollapseEnabled": True,
        "replayedHypothesisCount": len(replay_fusions),
        "decisionChangedCount": decision_changed_count,
        "providerRequestCount": len(provider.requests),
        **wrong_audit,
        "globalConflictGroupCount": selection.conflict_group_count,
        "globalAbstainedHypothesisCount": selection.abstained_hypothesis_count,
        "verifiedFieldCount": len(fields),
        "schemaExecutable": schema.executable,
        "parseCoverage": schema.parse_coverage,
        "constraintSatisfactionRateEvaluable": False,
    }
    return NoVerificationAblationExecution(corpus=corpus, record=record, audit=audit)


def write_no_verification_ablation_execution(
    execution: NoVerificationAblationExecution,
    output_dir: Path,
) -> Path:
    """Write canonical no-verification mechanism evidence."""

    if not isinstance(execution, NoVerificationAblationExecution):
        raise TypeError("execution must be NoVerificationAblationExecution")
    target = output_dir.expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    (target / "ablation_no_verification.json").write_text(
        canonical_record_json(execution.record) + "\n",
        encoding="utf-8",
    )
    (target / "ablation_no_verification.audit.json").write_text(
        json.dumps(execution.audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "datasetId": execution.corpus.dataset.dataset_id,
        "datasetSha256": execution.corpus.dataset.sha256,
        "datasetVersion": execution.corpus.dataset.version,
        "variant": "ablation_no_verification",
        "resultScope": "mechanism",
        "model": {
            "provider": execution.record.model_provider,
            "version": execution.record.model_version,
        },
        "formalBenchmark": False,
        "realLLMBenchmark": False,
        "scientificFingerprint": scientific_record_fingerprint(execution.record),
    }
    (target / "ablation-no-verification-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def _decision_without_verification(
    *,
    support_score: float,
    conflict_score: float,
    effective_component_count: int,
    acceptance_support_threshold: float,
    max_conflict_for_accept: float,
    minimum_effective_components: int,
) -> str:
    if effective_component_count < minimum_effective_components:
        return "uncertain"
    if conflict_score > max_conflict_for_accept:
        return "uncertain"
    if support_score >= acceptance_support_threshold:
        return "accepted"
    return "uncertain"


def _replay_without_verification(
    findings: tuple[Any, ...],
    evidence: tuple[Evidence, ...],
) -> tuple[
    tuple[_ReplayCandidate, ...],
    tuple[ProvenanceFusionResult, ...],
    dict[str, VerificationResult],
]:
    evidence_by_id = {item.evidence_id: item for item in evidence}
    candidates: list[_ReplayCandidate] = []
    fusions: list[ProvenanceFusionResult] = []
    control_verification: dict[str, VerificationResult] = {}

    for finding in findings:
        hypothesis_id = finding.finding_id.removeprefix("finding:")
        relevant_all = tuple(
            evidence_by_id[evidence_id]
            for evidence_id in finding.evidence_ids
            if evidence_id in evidence_by_id
            and evidence_by_id[evidence_id].source_component != "track-c-global-selection"
        )
        verifier_records = tuple(
            item
            for item in relevant_all
            if item.source_component == "track-c-executable-verifier"
        )
        candidate_records = tuple(
            item
            for item in relevant_all
            if item.source_component == "track-d-field-candidate"
        )
        provider_records = tuple(
            item
            for item in relevant_all
            if item.source_component == "track-c-llm-provider"
            and item.observation.get("hypothesisId") == hypothesis_id
        )
        if len(verifier_records) != 1 or len(candidate_records) != 1:
            raise ValueError(
                f"hypothesis {hypothesis_id!r} lacks exact candidate/verifier mapping"
            )
        if len(provider_records) > 1:
            raise ValueError(f"hypothesis {hypothesis_id!r} maps to multiple provider records")

        verifier = _verification_from_evidence(verifier_records[0], hypothesis_id)
        control_verification[hypothesis_id] = verifier
        relevant = tuple(
            item
            for item in relevant_all
            if item.source_component != "track-c-executable-verifier"
        )
        fusion = fuse_hypothesis_evidence_without_verification(hypothesis_id, relevant)
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
            interpretation = f"no-verification replay {finding.semantic_type} hypothesis"
            candidate_id = base_candidate_id

        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ValueError("replay hypothesis has invalid offset")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise ValueError("replay hypothesis has invalid size")
        if not isinstance(interpretation, str) or not interpretation.strip():
            raise ValueError("replay hypothesis has no interpretation")
        if not isinstance(finding.semantic_type, str) or not finding.semantic_type:
            raise ValueError("replay finding has no semantic type")

        candidates.append(
            _ReplayCandidate(
                hypothesis_id=hypothesis_id,
                candidate_id=candidate_id,
                offset=offset,
                size=size,
                semantic_type=finding.semantic_type,
                interpretation=interpretation,
                fusion=fusion,
                evidence_ids=tuple(sorted(item.evidence_id for item in relevant)),
                control_verification_status=verifier.status,
            )
        )
        fusions.append(fusion)

    if not fusions:
        raise ValueError("no production hypotheses were available for no-verification replay")
    return tuple(candidates), tuple(fusions), control_verification


def _wrong_hypothesis_effect(
    evidence: tuple[Evidence, ...],
    replay_fusions: tuple[ProvenanceFusionResult, ...],
    control_verification: dict[str, VerificationResult],
) -> dict[str, int | float]:
    replay_by_id = {item.hypothesis_id: item for item in replay_fusions}
    wrong: list[tuple[str, float]] = []
    correct: list[tuple[str, float]] = []
    for item in evidence:
        if item.source_component != "track-c-llm-provider":
            continue
        hypothesis_id = item.observation.get("hypothesisId")
        interpretation = item.observation.get("interpretation")
        confidence = item.observation.get("modelConfidence")
        if not isinstance(hypothesis_id, str):
            continue
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            continue
        if interpretation == "mechanism provider deliberately wrong endian length":
            wrong.append((hypothesis_id, float(confidence)))
        elif interpretation == "mechanism provider correct endian length":
            correct.append((hypothesis_id, float(confidence)))

    control_rejected_wrong = [
        item
        for item in wrong
        if control_verification.get(item[0]) is not None
        and control_verification[item[0]].status == "rejected"
    ]
    no_verification_not_rejected = [
        item for item in control_rejected_wrong if replay_by_id[item[0]].status != "rejected"
    ]
    no_verification_accepted = [
        item for item in control_rejected_wrong if replay_by_id[item[0]].status == "accepted"
    ]
    if not control_rejected_wrong:
        raise ValueError("paired full-method control rejected no deliberately wrong hypothesis")
    if not no_verification_not_rejected:
        raise ValueError(
            "removing verification did not change any control-rejected wrong hypothesis"
        )
    if not correct or not wrong:
        raise ValueError("deterministic provider did not emit the required competing hypotheses")

    return {
        "controlRejectedWrongHypothesisCount": len(control_rejected_wrong),
        "wrongHypothesisNotRejectedWithoutVerificationCount": len(
            no_verification_not_rejected
        ),
        "wrongHypothesisAcceptedWithoutVerificationCount": len(no_verification_accepted),
        "wrongHypothesisMaxConfidence": max(confidence for _, confidence in wrong),
        "correctHypothesisMaxConfidence": max(confidence for _, confidence in correct),
    }


def _ablation_record(
    dataset: DatasetIdentity,
    *,
    code_sha: str,
    schema_executable: bool,
    schema_error: str | None,
    parse_coverage: float,
    processing_time_seconds: float,
    dependencies: tuple[DependencyVersion, ...],
    semantic: dict[str, Any],
    field_count: int,
    decision_changed_count: int,
) -> ExperimentRecord:
    metrics: list[MetricRecord] = [
        metric_for_dataset(dataset, name, None) for name in _GROUND_TRUTH_METRICS
    ]
    metrics.extend(
        (
            metric_for_dataset(dataset, "parse_coverage", parse_coverage),
            MetricRecord(
                name="constraint_satisfaction_rate",
                evaluable=False,
                value=None,
                unavailable_reason=(
                    "not applicable: executable verification intentionally disabled "
                    "in this ablation"
                ),
            ),
            metric_for_dataset(dataset, "processing_time_seconds", processing_time_seconds),
            metric_for_dataset(dataset, "token_cost_usd", 0.0),
        )
    )
    return ExperimentRecord(
        variant="ablation_no_verification",
        result_scope="mechanism",
        dataset=dataset,
        code_sha=code_sha,
        config={
            "datasetLayout": "SYN1/type/reserved/seq/length-be/payload",
            "externalGroundTruthUsed": False,
            "formalBenchmark": False,
            "realLLMBenchmark": False,
            "providerKind": "deterministic-network-free-mechanism-fixture",
            "providerNetworkAccess": False,
            "llmEnabled": True,
            "verificationEnabled": False,
            "verificationEvidenceUsed": False,
            "verificationSelectionScore": 0.0,
            "provenanceAwareFusionEnabled": True,
            "provenanceCollapseEnabled": True,
            "ablationFusionPolicy": NO_VERIFICATION_POLICY_VERSION,
            "controlFusionPolicy": semantic.get("fusionPolicy"),
            "globalSelectionEnabled": True,
            "decisionChangedCount": decision_changed_count,
            "schemaExecutable": schema_executable,
            "schemaExecutionError": schema_error,
            "fieldCount": field_count,
            "timingScope": (
                "no-verification-replay-after-shared-production-evidence-materialization"
            ),
        },
        random_seed=0,
        model_provider=DETERMINISTIC_MECHANISM_PROVIDER,
        model_version=DETERMINISTIC_MECHANISM_MODEL_VERSION,
        metrics=tuple(metrics),
        dependencies=dependencies,
        notes=(
            "One-factor mechanism ablation: executable verification is disabled.",
            "Provider, provenance collapse, fusion thresholds and global selection "
            "are held constant.",
            "Constraint Satisfaction Rate is not evaluable because the verifier is removed.",
            "Synthetic mechanism evidence is not teacher-data or real-LLM benchmark evidence.",
        ),
    )
