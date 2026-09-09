from __future__ import annotations

import json
import platform
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from course_project.evidence.global_selection import (
    FieldSelectionCandidate,
    select_globally_consistent_fields,
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
from course_project.experiments.llm_only import _provider_candidates
from course_project.experiments.no_provenance import _verification_from_evidence
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

LLM_VERIFICATION_SELECTION_POLICY_VERSION = "verification-gate-model-confidence-v1"
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
class LLMVerificationMechanismExecution:
    """Provider-hypothesis baseline gated by executable verification only."""

    corpus: SyntheticMechanismCorpus
    record: ExperimentRecord
    audit: dict[str, object]


@dataclass(frozen=True, slots=True)
class _VerifiedProviderCandidate:
    hypothesis_id: str
    candidate_id: str
    offset: int
    size: int
    semantic_type: str
    interpretation: str
    model_confidence: float
    provider_evidence_id: str
    verifier_evidence_id: str
    verification: VerificationResult

    @property
    def region_key(self) -> tuple[int, int, str]:
        return (self.offset, self.size, self.semantic_type)


def run_llm_verification_mechanism_baseline(
    work_dir: Path,
    *,
    code_sha: str,
) -> LLMVerificationMechanismExecution:
    """Execute provider hypotheses with verifier gating and no provenance fusion."""

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
        metadata={"experimentScope": "synthetic-llm-verification-mechanism"},
    )
    provider = DeterministicEvidenceGraphMechanismProvider()
    state_dir = root / "paired-full-method-state"
    result = TrackDBaselineBackend(
        state_dir=state_dir,
        semantic_backend=DeterministicTrackCSemanticBackend(llm_provider=provider),
    ).analyze(
        task_id="synthetic-llm-verification-baseline",
        input_metadata=input_metadata,
        input_path=capture_path,
        config=_semantic_config(),
    )
    semantic = _validate_full_result(
        result,
        expected_messages=len(corpus.messages),
        provider_request_count=len(provider.requests),
    )
    control_audit = _provider_hypothesis_audit(result.evidence, result.findings)

    replay_started = perf_counter()
    candidates = _verified_provider_candidates(result.evidence)
    accepted = tuple(item for item in candidates if item.verification.status == "accepted")
    rejected = tuple(item for item in candidates if item.verification.status == "rejected")
    uncertain = tuple(item for item in candidates if item.verification.status == "uncertain")
    region_winners = _accepted_region_winners(accepted)
    selection = select_globally_consistent_fields(
        FieldSelectionCandidate(
            hypothesis_id=item.hypothesis_id,
            candidate_id=item.candidate_id,
            offset=item.offset,
            size=item.size,
            fusion_margin=item.verification.score,
            support_score=item.model_confidence,
            conflict_score=0.0,
            verification_score=item.verification.score,
        )
        for item in region_winners
    )
    selected_ids = set(selection.selected_hypothesis_ids)
    selected = tuple(item for item in region_winners if item.hypothesis_id in selected_ids)
    fields = tuple(
        VerifiedField(
            field_id=f"llm-verification:{item.hypothesis_id}",
            offset=item.offset,
            size=item.size,
            semantic_type=item.semantic_type,
            interpretation=item.interpretation,
            verification_score=item.verification.score,
            evidence_ids=(item.provider_evidence_id, item.verifier_evidence_id),
        )
        for item in selected
    )
    replay_elapsed = perf_counter() - replay_started

    wrong = tuple(
        item
        for item in candidates
        if item.interpretation == "mechanism provider deliberately wrong endian length"
    )
    correct = tuple(
        item
        for item in candidates
        if item.interpretation == "mechanism provider correct endian length"
    )
    rejected_wrong = tuple(item for item in wrong if item.verification.status == "rejected")
    accepted_correct = tuple(item for item in correct if item.verification.status == "accepted")
    selected_wrong = tuple(
        item
        for item in selected
        if item.interpretation == "mechanism provider deliberately wrong endian length"
    )
    selected_correct = tuple(
        item
        for item in selected
        if item.interpretation == "mechanism provider correct endian length"
    )
    if not rejected_wrong:
        raise ValueError("LLM+verification baseline rejected no deliberately wrong hypothesis")
    if not accepted_correct:
        raise ValueError("LLM+verification baseline accepted no correct provider hypothesis")
    if selected_wrong:
        raise ValueError("LLM+verification baseline selected a verifier-rejected wrong hypothesis")
    if not selected_correct:
        raise ValueError("LLM+verification baseline selected no correct provider hypothesis")

    schema = _schema_execution(fields, corpus)
    constraint_rate = _constraint_satisfaction_rate(fields, result.evidence)
    dependencies = (
        DependencyVersion(name="course-project", version="0.1.0"),
        DependencyVersion(name="python", version=platform.python_version()),
    )
    record = _llm_verification_record(
        corpus.dataset,
        code_sha=code_sha,
        schema_executable=schema.executable,
        schema_error=schema.error,
        parse_coverage=schema.parse_coverage,
        constraint_satisfaction_rate=constraint_rate,
        processing_time_seconds=replay_elapsed,
        dependencies=dependencies,
        provider_request_count=len(provider.requests),
        provider_hypothesis_count=len(candidates),
        accepted_hypothesis_count=len(accepted),
        rejected_hypothesis_count=len(rejected),
        uncertain_hypothesis_count=len(uncertain),
        region_winner_count=len(region_winners),
        field_count=len(fields),
    )
    audit: dict[str, object] = {
        "datasetId": corpus.dataset.dataset_id,
        "datasetSha256": corpus.dataset.sha256,
        "variant": "llm_verification",
        "resultScope": "mechanism",
        "provider": DETERMINISTIC_MECHANISM_PROVIDER,
        "modelVersion": DETERMINISTIC_MECHANISM_MODEL_VERSION,
        "networkAccess": False,
        "realLLMBenchmark": False,
        "teacherBenchmark": False,
        "selectionPolicy": LLM_VERIFICATION_SELECTION_POLICY_VERSION,
        "providerRequestCount": len(provider.requests),
        "providerHypothesisCount": len(candidates),
        "verificationMatchedProviderHypothesisCount": len(candidates),
        "acceptedProviderHypothesisCount": len(accepted),
        "rejectedProviderHypothesisCount": len(rejected),
        "uncertainProviderHypothesisCount": len(uncertain),
        "pairedControlVerificationExecuted": semantic.get("verificationExecuted"),
        "pairedControlFusionExecuted": semantic.get("fusionExecuted"),
        "baselineVerificationExecuted": True,
        "baselineFusionExecuted": False,
        "rejectedWrongHypothesisCount": len(rejected_wrong),
        "acceptedCorrectHypothesisCount": len(accepted_correct),
        "wrongHypothesisMaxConfidence": control_audit["wrongHypothesisMaxConfidence"],
        "correctHypothesisMaxConfidence": control_audit["correctHypothesisMaxConfidence"],
        "selectedWrongHypothesisCount": len(selected_wrong),
        "selectedCorrectHypothesisCount": len(selected_correct),
        "selectedHypothesisCount": len(selected),
        "globalConflictGroupCount": selection.conflict_group_count,
        "globalAbstainedHypothesisCount": selection.abstained_hypothesis_count,
        "schemaExecutable": schema.executable,
        "parseCoverage": schema.parse_coverage,
        "constraintSatisfactionRate": constraint_rate,
    }
    return LLMVerificationMechanismExecution(corpus=corpus, record=record, audit=audit)


def write_llm_verification_mechanism_execution(
    execution: LLMVerificationMechanismExecution,
    output_dir: Path,
) -> Path:
    """Write canonical LLM+verification mechanism evidence."""

    if not isinstance(execution, LLMVerificationMechanismExecution):
        raise TypeError("execution must be LLMVerificationMechanismExecution")
    target = output_dir.expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    (target / "llm_verification.json").write_text(
        canonical_record_json(execution.record) + "\n",
        encoding="utf-8",
    )
    (target / "llm_verification.audit.json").write_text(
        json.dumps(execution.audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "datasetId": execution.corpus.dataset.dataset_id,
        "datasetSha256": execution.corpus.dataset.sha256,
        "datasetVersion": execution.corpus.dataset.version,
        "variant": "llm_verification",
        "resultScope": "mechanism",
        "model": {
            "provider": execution.record.model_provider,
            "version": execution.record.model_version,
        },
        "formalBenchmark": False,
        "realLLMBenchmark": False,
        "scientificFingerprint": scientific_record_fingerprint(execution.record),
    }
    (target / "llm-verification-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def _verified_provider_candidates(
    evidence: tuple[Evidence, ...],
) -> tuple[_VerifiedProviderCandidate, ...]:
    provider_candidates = _provider_candidates(evidence)
    provider_evidence: dict[str, Evidence] = {}
    verifier_evidence: dict[str, Evidence] = {}

    for item in evidence:
        hypothesis_id = item.observation.get("hypothesisId")
        if not isinstance(hypothesis_id, str):
            continue
        if item.source_component == "track-c-llm-provider":
            if hypothesis_id in provider_evidence:
                raise ValueError(f"duplicate provider evidence for hypothesis {hypothesis_id!r}")
            provider_evidence[hypothesis_id] = item
        elif item.source_component == "track-c-executable-verifier":
            if hypothesis_id in verifier_evidence:
                raise ValueError(f"duplicate verifier evidence for hypothesis {hypothesis_id!r}")
            verifier_evidence[hypothesis_id] = item

    verified: list[_VerifiedProviderCandidate] = []
    for candidate in provider_candidates:
        provider_record = provider_evidence.get(candidate.hypothesis_id)
        verifier_record = verifier_evidence.get(candidate.hypothesis_id)
        if provider_record is None:
            raise ValueError(
                f"provider hypothesis {candidate.hypothesis_id!r} has no provider evidence record"
            )
        if verifier_record is None:
            raise ValueError(
                f"provider hypothesis {candidate.hypothesis_id!r} has no executable verifier record"
            )
        verification = _verification_from_evidence(
            verifier_record,
            candidate.hypothesis_id,
        )
        verified.append(
            _VerifiedProviderCandidate(
                hypothesis_id=candidate.hypothesis_id,
                candidate_id=f"llm-verification:{candidate.hypothesis_id}",
                offset=candidate.offset,
                size=candidate.size,
                semantic_type=candidate.semantic_type,
                interpretation=candidate.interpretation,
                model_confidence=candidate.model_confidence,
                provider_evidence_id=provider_record.evidence_id,
                verifier_evidence_id=verifier_record.evidence_id,
                verification=verification,
            )
        )
    if not verified:
        raise ValueError("paired full method emitted no verified provider hypotheses")
    return tuple(verified)


def _accepted_region_winners(
    candidates: tuple[_VerifiedProviderCandidate, ...],
) -> tuple[_VerifiedProviderCandidate, ...]:
    grouped: dict[tuple[int, int, str], list[_VerifiedProviderCandidate]] = {}
    for item in candidates:
        if item.verification.status != "accepted":
            raise ValueError("region ranking may only receive verifier-accepted hypotheses")
        grouped.setdefault(item.region_key, []).append(item)

    winners: list[_VerifiedProviderCandidate] = []
    for key, records in grouped.items():
        best_confidence = max(item.model_confidence for item in records)
        best = [item for item in records if item.model_confidence == best_confidence]
        if len(best) != 1:
            raise ValueError(
                f"LLM+verification confidence tie for accepted field region {key!r}; baseline must fail closed"
            )
        winners.append(best[0])
    return tuple(sorted(winners, key=lambda item: (item.offset, item.size, item.hypothesis_id)))


def _llm_verification_record(
    dataset: DatasetIdentity,
    *,
    code_sha: str,
    schema_executable: bool,
    schema_error: str | None,
    parse_coverage: float,
    constraint_satisfaction_rate: float,
    processing_time_seconds: float,
    dependencies: tuple[DependencyVersion, ...],
    provider_request_count: int,
    provider_hypothesis_count: int,
    accepted_hypothesis_count: int,
    rejected_hypothesis_count: int,
    uncertain_hypothesis_count: int,
    region_winner_count: int,
    field_count: int,
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
        variant="llm_verification",
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
            "llmVerificationBaseline": True,
            "verificationEnabled": True,
            "verificationEvidenceUsed": True,
            "provenanceAwareFusionEnabled": False,
            "provenanceEvidenceUsedForSelection": False,
            "selectionPolicy": LLM_VERIFICATION_SELECTION_POLICY_VERSION,
            "globalSelectionEnabled": True,
            "providerRequestCount": provider_request_count,
            "providerHypothesisCount": provider_hypothesis_count,
            "acceptedProviderHypothesisCount": accepted_hypothesis_count,
            "rejectedProviderHypothesisCount": rejected_hypothesis_count,
            "uncertainProviderHypothesisCount": uncertain_hypothesis_count,
            "acceptedRegionWinnerCount": region_winner_count,
            "schemaExecutable": schema_executable,
            "schemaExecutionError": schema_error,
            "fieldCount": field_count,
            "timingScope": "llm-provider-plus-verifier-selection-after-paired-production-materialization",
        },
        random_seed=0,
        model_provider=DETERMINISTIC_MECHANISM_PROVIDER,
        model_version=DETERMINISTIC_MECHANISM_MODEL_VERSION,
        metrics=tuple(metrics),
        dependencies=dependencies,
        notes=(
            "Mechanism-only LLM+verification baseline: provider hypotheses are gated by executable verification without provenance-aware fusion.",
            "Model confidence is only a secondary ranking signal among verifier-accepted competing hypotheses and is never relabeled as verification confidence.",
            "Constraint Satisfaction Rate is derived from actual verifier evidence linked to the selected fields.",
            "Synthetic deterministic-provider evidence is not a real-LLM or teacher-data benchmark.",
        ),
    )
