from __future__ import annotations

import json
import platform
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from course_project.evidence.global_selection import (
    FieldSelectionCandidate,
    select_globally_consistent_fields,
)
from course_project.evidence.provenance_fusion import (
    FusionComponent,
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
    _constraint_satisfaction_rate,
    _provider_hypothesis_audit,
    _schema_execution,
    _semantic_config,
    _validate_code_sha,
    _validate_full_result,
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

NO_PROVENANCE_POLICY_VERSION = "raw-record-mean-no-provenance-v1"
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
class NoProvenanceAblationExecution:
    """Auditable no-provenance replay over exact production evidence."""

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
    verification: VerificationResult
    fusion: ProvenanceFusionResult
    evidence_ids: tuple[str, ...]


def fuse_hypothesis_evidence_without_provenance(
    hypothesis_id: str,
    evidence: Iterable[Evidence],
    verification: VerificationResult,
    *,
    acceptance_support_threshold: float = _ACCEPTANCE_SUPPORT_THRESHOLD,
    max_conflict_for_accept: float = _MAX_CONFLICT_FOR_ACCEPT,
    minimum_effective_components: int = 1,
) -> ProvenanceFusionResult:
    """Replay fusion while intentionally treating every evidence record as independent.

    The production fusion function is called first so the ablation inherits the same
    fail-closed input and threshold validation. The returned production decision is not
    reused: this experiment then classifies the exact raw records with the same stance
    semantics but deliberately skips parent/independence-group collapse.
    """

    records = tuple(evidence)
    fuse_hypothesis_evidence(
        hypothesis_id,
        records,
        verification,
        acceptance_support_threshold=acceptance_support_threshold,
        max_conflict_for_accept=max_conflict_for_accept,
        minimum_effective_components=minimum_effective_components,
    )

    signals = tuple(
        _classify_raw_evidence(item, hypothesis_id, verification) for item in records
    )
    components = tuple(
        _raw_component(item, stance=stance, strength=strength)
        for item, (stance, strength) in zip(records, signals, strict=True)
    )
    component_count = len(components)
    denominator = component_count if component_count else 1
    support_score = sum(max(item.net_strength, 0.0) for item in components) / denominator
    conflict_score = sum(max(-item.net_strength, 0.0) for item in components) / denominator

    status = _decision_without_provenance(
        verification.status,
        support_score=support_score,
        conflict_score=conflict_score,
        effective_component_count=component_count,
        acceptance_support_threshold=acceptance_support_threshold,
        max_conflict_for_accept=max_conflict_for_accept,
        minimum_effective_components=minimum_effective_components,
    )
    direct_support_groups = sum(
        stance == "support" and not item.parent_evidence_ids
        for item, (stance, _strength) in zip(records, signals, strict=True)
    )
    derived_support_records = sum(
        stance == "support" and bool(item.parent_evidence_ids)
        for item, (stance, _strength) in zip(records, signals, strict=True)
    )
    conflict_records = sum(stance == "conflict" for stance, _strength in signals)
    neutral_records = sum(stance == "neutral" for stance, _strength in signals)

    return ProvenanceFusionResult(
        hypothesis_id=hypothesis_id,
        status=status,
        policy=NO_PROVENANCE_POLICY_VERSION,
        support_score=support_score,
        conflict_score=conflict_score,
        margin=support_score - conflict_score,
        verification_status=verification.status,
        raw_evidence_count=len(records),
        effective_component_count=component_count,
        direct_support_groups=direct_support_groups,
        derived_support_records=derived_support_records,
        conflict_records=conflict_records,
        neutral_records=neutral_records,
        acceptance_support_threshold=acceptance_support_threshold,
        max_conflict_for_accept=max_conflict_for_accept,
        minimum_effective_components=minimum_effective_components,
        components=components,
    )


def run_no_provenance_ablation(
    work_dir: Path,
    *,
    code_sha: str,
) -> NoProvenanceAblationExecution:
    """Execute a one-factor no-provenance replay over real production evidence."""

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
        metadata={"experimentScope": "synthetic-no-provenance-ablation"},
    )
    provider = DeterministicEvidenceGraphMechanismProvider()
    state_dir = root / "shared-production-state"
    result = TrackDBaselineBackend(
        state_dir=state_dir,
        semantic_backend=DeterministicTrackCSemanticBackend(llm_provider=provider),
    ).analyze(
        task_id="synthetic-ablation-no-provenance",
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
    collapsed_rows = [
        row
        for row in control_fusion_audit
        if row["rawEvidenceCount"] > row["effectiveComponentCount"]
    ]
    if not collapsed_rows:
        raise ValueError(
            "full method exposed no dependency collapse; no-provenance ablation is not meaningful"
        )

    provider_audit = _provider_hypothesis_audit(result.evidence, result.findings)
    replay_started = perf_counter()
    replay_candidates, replay_fusions = _replay_findings_without_provenance(
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
            verification_score=item.verification.score,
        )
        for item in accepted
    )
    selected_ids = set(selection.selected_hypothesis_ids)
    fields = tuple(
        VerifiedField(
            field_id=f"no-provenance:{item.candidate_id}",
            offset=item.offset,
            size=item.size,
            semantic_type=item.semantic_type,
            interpretation=item.interpretation,
            verification_score=item.verification.score,
            evidence_ids=item.evidence_ids,
        )
        for item in accepted
        if item.hypothesis_id in selected_ids
    )
    replay_elapsed = perf_counter() - replay_started

    schema = _schema_execution(fields, corpus)
    constraint_rate = _constraint_satisfaction_rate(fields, result.evidence)
    control_status = {
        str(row["hypothesisId"]): str(row["status"]) for row in control_fusion_audit
    }
    decision_changed_count = sum(
        control_status.get(item.hypothesis_id) != item.status for item in replay_fusions
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
        constraint_satisfaction_rate=constraint_rate,
        processing_time_seconds=replay_elapsed,
        dependencies=dependencies,
        semantic=semantic,
        field_count=len(fields),
        control_collapsed_count=len(collapsed_rows),
        decision_changed_count=decision_changed_count,
    )
    audit: dict[str, object] = {
        "datasetId": corpus.dataset.dataset_id,
        "datasetSha256": corpus.dataset.sha256,
        "variant": "ablation_no_provenance",
        "resultScope": "mechanism",
        "provider": DETERMINISTIC_MECHANISM_PROVIDER,
        "modelVersion": DETERMINISTIC_MECHANISM_MODEL_VERSION,
        "networkAccess": False,
        "realLLMBenchmark": False,
        "teacherBenchmark": False,
        "controlFusionPolicy": semantic.get("fusionPolicy"),
        "ablationFusionPolicy": NO_PROVENANCE_POLICY_VERSION,
        "controlCollapsedHypothesisCount": len(collapsed_rows),
        "controlMaxDependencyReduction": max(
            row["rawEvidenceCount"] - row["effectiveComponentCount"]
            for row in collapsed_rows
        ),
        "ablationAllEvidenceIndependent": all(
            item.raw_evidence_count == item.effective_component_count
            for item in replay_fusions
        ),
        "replayedHypothesisCount": len(replay_fusions),
        "decisionChangedCount": decision_changed_count,
        "providerRequestCount": len(provider.requests),
        "rejectedWrongHypothesisCount": provider_audit["rejectedWrongHypothesisCount"],
        "wrongHypothesisMaxConfidence": provider_audit["wrongHypothesisMaxConfidence"],
        "correctHypothesisMaxConfidence": provider_audit["correctHypothesisMaxConfidence"],
        "globalConflictGroupCount": selection.conflict_group_count,
        "globalAbstainedHypothesisCount": selection.abstained_hypothesis_count,
        "verifiedFieldCount": len(fields),
        "schemaExecutable": schema.executable,
        "parseCoverage": schema.parse_coverage,
        "constraintSatisfactionRate": constraint_rate,
    }
    return NoProvenanceAblationExecution(corpus=corpus, record=record, audit=audit)


def write_no_provenance_ablation_execution(
    execution: NoProvenanceAblationExecution,
    output_dir: Path,
) -> Path:
    """Write canonical no-provenance mechanism evidence."""

    if not isinstance(execution, NoProvenanceAblationExecution):
        raise TypeError("execution must be NoProvenanceAblationExecution")
    target = output_dir.expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    (target / "ablation_no_provenance.json").write_text(
        canonical_record_json(execution.record) + "\n",
        encoding="utf-8",
    )
    (target / "ablation_no_provenance.audit.json").write_text(
        json.dumps(execution.audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "datasetId": execution.corpus.dataset.dataset_id,
        "datasetSha256": execution.corpus.dataset.sha256,
        "datasetVersion": execution.corpus.dataset.version,
        "variant": "ablation_no_provenance",
        "resultScope": "mechanism",
        "model": {
            "provider": execution.record.model_provider,
            "version": execution.record.model_version,
        },
        "formalBenchmark": False,
        "realLLMBenchmark": False,
        "scientificFingerprint": scientific_record_fingerprint(execution.record),
    }
    (target / "ablation-no-provenance-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def _classify_raw_evidence(
    item: Evidence,
    hypothesis_id: str,
    verification: VerificationResult,
) -> tuple[str, float]:
    if item.source_component == "track-c-executable-verifier":
        if item.observation.get("hypothesisId") != hypothesis_id:
            raise ValueError("verifier evidence targets a different hypothesis")
        if item.observation.get("status") != verification.status:
            raise ValueError("verifier evidence disagrees with verification status")
        if verification.status == "accepted":
            return "support", item.score
        if verification.status == "rejected":
            return "conflict", 1.0 - item.score
        return "neutral", 0.0

    stance = item.observation.get("stance", "support")
    if stance not in {"support", "conflict", "neutral"}:
        raise ValueError(f"unsupported evidence stance: {stance!r}")
    return str(stance), item.score if stance != "neutral" else 0.0


def _raw_component(item: Evidence, *, stance: str, strength: float) -> FusionComponent:
    support_ids = (item.evidence_id,) if stance == "support" else ()
    conflict_ids = (item.evidence_id,) if stance == "conflict" else ()
    support_strength = strength if stance == "support" else 0.0
    conflict_strength = strength if stance == "conflict" else 0.0
    direct_support = support_ids if not item.parent_evidence_ids else ()
    derived_support = support_ids if item.parent_evidence_ids else ()
    return FusionComponent(
        representative_evidence_id=item.evidence_id,
        evidence_ids=(item.evidence_id,),
        source_components=(item.source_component,),
        sample_ids=item.sample_ids,
        dependency_signals=("provenance-collapse-disabled",),
        support_strength=support_strength,
        conflict_strength=conflict_strength,
        net_strength=support_strength - conflict_strength,
        direct_support_evidence_ids=direct_support,
        derived_support_evidence_ids=derived_support,
        conflict_evidence_ids=conflict_ids,
    )


def _decision_without_provenance(
    verification_status: str,
    *,
    support_score: float,
    conflict_score: float,
    effective_component_count: int,
    acceptance_support_threshold: float,
    max_conflict_for_accept: float,
    minimum_effective_components: int,
) -> str:
    if verification_status == "rejected":
        return "rejected"
    if verification_status != "accepted":
        return "uncertain"
    if effective_component_count < minimum_effective_components:
        return "uncertain"
    if conflict_score > max_conflict_for_accept:
        return "uncertain"
    if support_score >= acceptance_support_threshold:
        return "accepted"
    return "uncertain"


def _control_fusion_audit(semantic: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    rows = semantic.get("fusionAudit")
    if not isinstance(rows, list) or not rows:
        raise TypeError("production fusion audit is missing")
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise TypeError("production fusion audit row must be an object")
        required = {
            "hypothesisId",
            "status",
            "rawEvidenceCount",
            "effectiveComponentCount",
        }
        if not required <= row.keys():
            raise ValueError("production fusion audit row is incomplete")
        if not isinstance(row["rawEvidenceCount"], int) or not isinstance(
            row["effectiveComponentCount"], int
        ):
            raise TypeError("production fusion audit counts must be integers")
        normalized.append(dict(row))
    return tuple(normalized)


def _replay_findings_without_provenance(
    findings: tuple[Any, ...],
    evidence: tuple[Evidence, ...],
) -> tuple[tuple[_ReplayCandidate, ...], tuple[ProvenanceFusionResult, ...]]:
    evidence_by_id = {item.evidence_id: item for item in evidence}
    candidates: list[_ReplayCandidate] = []
    fusions: list[ProvenanceFusionResult] = []

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
                f"hypothesis {hypothesis_id!r} lacks an exact candidate/verifier replay mapping"
            )
        if len(provider_records) > 1:
            raise ValueError(f"hypothesis {hypothesis_id!r} maps to multiple provider records")

        verifier = _verification_from_evidence(verifier_records[0], hypothesis_id)
        fusion = fuse_hypothesis_evidence_without_provenance(
            hypothesis_id,
            relevant,
            verifier,
        )
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
            interpretation = f"no-provenance replay {finding.semantic_type} hypothesis"
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
                verification=verifier,
                fusion=fusion,
                evidence_ids=tuple(sorted(item.evidence_id for item in relevant)),
            )
        )
        fusions.append(fusion)

    if not fusions:
        raise ValueError("no production hypotheses were available for no-provenance replay")
    return tuple(candidates), tuple(fusions)


def _verification_from_evidence(item: Evidence, hypothesis_id: str) -> VerificationResult:
    observation = item.observation
    status = observation.get("status")
    support_count = observation.get("supportCount")
    sample_count = observation.get("sampleCount")
    if observation.get("hypothesisId") != hypothesis_id:
        raise ValueError("verifier evidence hypothesis id mismatch")
    if status not in {"accepted", "rejected", "uncertain"}:
        raise ValueError("verifier evidence has non-canonical status")
    if not isinstance(support_count, int) or isinstance(support_count, bool):
        raise TypeError("verifier supportCount must be an integer")
    if not isinstance(sample_count, int) or isinstance(sample_count, bool):
        raise TypeError("verifier sampleCount must be an integer")
    return VerificationResult(
        hypothesis_id=hypothesis_id,
        status=status,
        score=float(item.score),
        support_count=support_count,
        sample_count=sample_count,
        tests={"replayedFromEvidenceId": item.evidence_id},
    )


def _ablation_record(
    dataset: DatasetIdentity,
    *,
    code_sha: str,
    schema_executable: bool,
    schema_error: str | None,
    parse_coverage: float,
    constraint_satisfaction_rate: float,
    processing_time_seconds: float,
    dependencies: tuple[DependencyVersion, ...],
    semantic: dict[str, Any],
    field_count: int,
    control_collapsed_count: int,
    decision_changed_count: int,
) -> ExperimentRecord:
    metrics: list[MetricRecord] = [
        metric_for_dataset(dataset, name, None) for name in _GROUND_TRUTH_METRICS
    ]
    metrics.extend(
        (
            metric_for_dataset(dataset, "parse_coverage", parse_coverage),
            metric_for_dataset(
                dataset,
                "constraint_satisfaction_rate",
                constraint_satisfaction_rate,
            ),
            metric_for_dataset(dataset, "processing_time_seconds", processing_time_seconds),
            metric_for_dataset(dataset, "token_cost_usd", 0.0),
        )
    )
    return ExperimentRecord(
        variant="ablation_no_provenance",
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
            "verificationEnabled": True,
            "provenanceAwareFusionEnabled": False,
            "provenanceCollapseEnabled": False,
            "rawEvidenceTreatedAsIndependent": True,
            "ablationFusionPolicy": NO_PROVENANCE_POLICY_VERSION,
            "controlFusionPolicy": semantic.get("fusionPolicy"),
            "globalSelectionEnabled": True,
            "controlCollapsedHypothesisCount": control_collapsed_count,
            "decisionChangedCount": decision_changed_count,
            "schemaExecutable": schema_executable,
            "schemaExecutionError": schema_error,
            "fieldCount": field_count,
            "timingScope": "no-provenance-replay-after-shared-production-evidence-materialization",
        },
        random_seed=0,
        model_provider=DETERMINISTIC_MECHANISM_PROVIDER,
        model_version=DETERMINISTIC_MECHANISM_MODEL_VERSION,
        metrics=tuple(metrics),
        dependencies=dependencies,
        notes=(
            "One-factor mechanism ablation: only provenance/dependency collapse is disabled.",
            "Provider, verifier, thresholds and global selection are held constant.",
            "Synthetic mechanism evidence is not teacher-data or real-LLM benchmark evidence.",
        ),
    )
