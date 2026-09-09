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
from course_project.models import Evidence, InputMetadata, VerifiedField
from course_project.sidecar import DeterministicTrackCSemanticBackend, TrackDBaselineBackend

LLM_ONLY_SELECTION_POLICY_VERSION = "model-confidence-per-region-v1"
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
class LLMOnlyMechanismExecution:
    """Auditable confidence-only baseline over the deterministic provider fixture."""

    corpus: SyntheticMechanismCorpus
    record: ExperimentRecord
    audit: dict[str, object]


@dataclass(frozen=True, slots=True)
class _ProviderCandidate:
    hypothesis_id: str
    candidate_id: str
    offset: int
    size: int
    semantic_type: str
    interpretation: str
    model_confidence: float
    evidence_id: str

    @property
    def region_key(self) -> tuple[int, int, str]:
        return (self.offset, self.size, self.semantic_type)


def run_llm_only_mechanism_baseline(
    work_dir: Path,
    *,
    code_sha: str,
) -> LLMOnlyMechanismExecution:
    """Execute an LLM-only confidence baseline with no verifier/fusion decisions."""

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
        metadata={"experimentScope": "synthetic-llm-only-mechanism"},
    )
    provider = DeterministicEvidenceGraphMechanismProvider()
    state_dir = root / "paired-full-method-state"
    result = TrackDBaselineBackend(
        state_dir=state_dir,
        semantic_backend=DeterministicTrackCSemanticBackend(llm_provider=provider),
    ).analyze(
        task_id="synthetic-llm-only-baseline",
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
    provider_candidates = _provider_candidates(result.evidence)
    region_winners = _confidence_region_winners(provider_candidates)
    selection = select_globally_consistent_fields(
        FieldSelectionCandidate(
            hypothesis_id=item.hypothesis_id,
            candidate_id=item.candidate_id,
            offset=item.offset,
            size=item.size,
            fusion_margin=item.model_confidence,
            support_score=item.model_confidence,
            conflict_score=0.0,
            verification_score=0.0,
        )
        for item in region_winners
    )
    selected_ids = set(selection.selected_hypothesis_ids)
    selected = tuple(item for item in region_winners if item.hypothesis_id in selected_ids)
    fields = tuple(
        VerifiedField(
            field_id=f"llm-only:{item.hypothesis_id}",
            offset=item.offset,
            size=item.size,
            semantic_type=item.semantic_type,
            interpretation=item.interpretation,
            verification_score=0.0,
            evidence_ids=(item.evidence_id,),
        )
        for item in selected
    )
    replay_elapsed = perf_counter() - replay_started

    wrong_winners = tuple(
        item
        for item in region_winners
        if item.interpretation == "mechanism provider deliberately wrong endian length"
    )
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
    if not wrong_winners:
        raise ValueError("confidence-only ranking produced no wrong-hypothesis region winner")
    if not selected_wrong:
        raise ValueError(
            "LLM-only global selection did not admit the higher-confidence wrong hypothesis"
        )
    if control_audit["rejectedWrongHypothesisCount"] < 1:
        raise ValueError("paired full method rejected no deliberately wrong hypothesis")

    schema = _schema_execution(fields, corpus)
    dependencies = (
        DependencyVersion(name="course-project", version="0.1.0"),
        DependencyVersion(name="python", version=platform.python_version()),
    )
    record = _llm_only_record(
        corpus.dataset,
        code_sha=code_sha,
        schema_executable=schema.executable,
        schema_error=schema.error,
        parse_coverage=schema.parse_coverage,
        processing_time_seconds=replay_elapsed,
        dependencies=dependencies,
        provider_request_count=len(provider.requests),
        provider_hypothesis_count=len(provider_candidates),
        region_winner_count=len(region_winners),
        field_count=len(fields),
    )
    audit: dict[str, object] = {
        "datasetId": corpus.dataset.dataset_id,
        "datasetSha256": corpus.dataset.sha256,
        "variant": "llm_only",
        "resultScope": "mechanism",
        "provider": DETERMINISTIC_MECHANISM_PROVIDER,
        "modelVersion": DETERMINISTIC_MECHANISM_MODEL_VERSION,
        "networkAccess": False,
        "realLLMBenchmark": False,
        "teacherBenchmark": False,
        "selectionPolicy": LLM_ONLY_SELECTION_POLICY_VERSION,
        "providerRequestCount": len(provider.requests),
        "providerHypothesisCount": len(provider_candidates),
        "confidenceRegionWinnerCount": len(region_winners),
        "pairedControlVerificationExecuted": semantic.get("verificationExecuted"),
        "pairedControlRejectedWrongHypothesisCount": control_audit[
            "rejectedWrongHypothesisCount"
        ],
        "wrongHypothesisMaxConfidence": control_audit["wrongHypothesisMaxConfidence"],
        "correctHypothesisMaxConfidence": control_audit["correctHypothesisMaxConfidence"],
        "wrongConfidenceRegionWinnerCount": len(wrong_winners),
        "selectedWrongHypothesisCount": len(selected_wrong),
        "selectedCorrectHypothesisCount": len(selected_correct),
        "selectedHypothesisCount": len(selected),
        "globalConflictGroupCount": selection.conflict_group_count,
        "globalAbstainedHypothesisCount": selection.abstained_hypothesis_count,
        "schemaExecutable": schema.executable,
        "parseCoverage": schema.parse_coverage,
        "constraintSatisfactionRateEvaluable": False,
    }
    return LLMOnlyMechanismExecution(corpus=corpus, record=record, audit=audit)


def write_llm_only_mechanism_execution(
    execution: LLMOnlyMechanismExecution,
    output_dir: Path,
) -> Path:
    """Write canonical LLM-only mechanism evidence."""

    if not isinstance(execution, LLMOnlyMechanismExecution):
        raise TypeError("execution must be LLMOnlyMechanismExecution")
    target = output_dir.expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    (target / "llm_only.json").write_text(
        canonical_record_json(execution.record) + "\n",
        encoding="utf-8",
    )
    (target / "llm_only.audit.json").write_text(
        json.dumps(execution.audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "datasetId": execution.corpus.dataset.dataset_id,
        "datasetSha256": execution.corpus.dataset.sha256,
        "datasetVersion": execution.corpus.dataset.version,
        "variant": "llm_only",
        "resultScope": "mechanism",
        "model": {
            "provider": execution.record.model_provider,
            "version": execution.record.model_version,
        },
        "formalBenchmark": False,
        "realLLMBenchmark": False,
        "scientificFingerprint": scientific_record_fingerprint(execution.record),
    }
    (target / "llm-only-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def _provider_candidates(evidence: tuple[Evidence, ...]) -> tuple[_ProviderCandidate, ...]:
    candidates: list[_ProviderCandidate] = []
    for item in evidence:
        if item.source_component != "track-c-llm-provider":
            continue
        observation = item.observation
        hypothesis_id = observation.get("hypothesisId")
        offset = observation.get("offset")
        size = observation.get("size")
        semantic_type = observation.get("semanticType")
        interpretation = observation.get("interpretation")
        confidence = observation.get("modelConfidence")
        if not isinstance(hypothesis_id, str) or not hypothesis_id.strip():
            raise ValueError("provider evidence has no hypothesisId")
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ValueError("provider evidence has invalid offset")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise ValueError("provider evidence has invalid size")
        if not isinstance(semantic_type, str) or not semantic_type.strip():
            raise ValueError("provider evidence has no semanticType")
        if not isinstance(interpretation, str) or not interpretation.strip():
            raise ValueError("provider evidence has no interpretation")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            raise TypeError("provider modelConfidence must be numeric")
        parsed_confidence = float(confidence)
        if not 0.0 <= parsed_confidence <= 1.0:
            raise ValueError("provider modelConfidence must be within [0, 1]")
        candidates.append(
            _ProviderCandidate(
                hypothesis_id=hypothesis_id,
                candidate_id=f"llm-only:{hypothesis_id}",
                offset=offset,
                size=size,
                semantic_type=semantic_type,
                interpretation=interpretation,
                model_confidence=parsed_confidence,
                evidence_id=item.evidence_id,
            )
        )
    if not candidates:
        raise ValueError("paired full method emitted no provider hypotheses for LLM-only replay")
    return tuple(candidates)


def _confidence_region_winners(
    candidates: tuple[_ProviderCandidate, ...],
) -> tuple[_ProviderCandidate, ...]:
    grouped: dict[tuple[int, int, str], list[_ProviderCandidate]] = {}
    for item in candidates:
        grouped.setdefault(item.region_key, []).append(item)

    winners: list[_ProviderCandidate] = []
    for key, records in grouped.items():
        best_confidence = max(item.model_confidence for item in records)
        best = [item for item in records if item.model_confidence == best_confidence]
        if len(best) != 1:
            raise ValueError(
                f"LLM-only confidence tie for field region {key!r}; baseline must abstain/fail closed"
            )
        winners.append(best[0])
    return tuple(sorted(winners, key=lambda item: (item.offset, item.size, item.hypothesis_id)))


def _llm_only_record(
    dataset: DatasetIdentity,
    *,
    code_sha: str,
    schema_executable: bool,
    schema_error: str | None,
    parse_coverage: float,
    processing_time_seconds: float,
    dependencies: tuple[DependencyVersion, ...],
    provider_request_count: int,
    provider_hypothesis_count: int,
    region_winner_count: int,
    field_count: int,
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
                    "not applicable: LLM-only baseline performs no executable verification"
                ),
            ),
            metric_for_dataset(dataset, "processing_time_seconds", processing_time_seconds),
            metric_for_dataset(dataset, "token_cost_usd", 0.0),
        )
    )
    return ExperimentRecord(
        variant="llm_only",
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
            "llmOnly": True,
            "verificationEnabled": False,
            "verificationEvidenceUsed": False,
            "provenanceAwareFusionEnabled": False,
            "provenanceEvidenceUsedForSelection": False,
            "selectionPolicy": LLM_ONLY_SELECTION_POLICY_VERSION,
            "globalSelectionEnabled": True,
            "providerRequestCount": provider_request_count,
            "providerHypothesisCount": provider_hypothesis_count,
            "confidenceRegionWinnerCount": region_winner_count,
            "schemaExecutable": schema_executable,
            "schemaExecutionError": schema_error,
            "fieldCount": field_count,
            "timingScope": "llm-only-confidence-selection-after-provider-materialization",
        },
        random_seed=0,
        model_provider=DETERMINISTIC_MECHANISM_PROVIDER,
        model_version=DETERMINISTIC_MECHANISM_MODEL_VERSION,
        metrics=tuple(metrics),
        dependencies=dependencies,
        notes=(
            "Mechanism-only LLM baseline: provider confidence ranks hypotheses without executable verification or provenance-aware fusion.",
            "Track D candidate windows are held constant as provider context but do not contribute selection scores.",
            "Constraint Satisfaction Rate is not evaluable because executable verification is absent.",
            "Synthetic deterministic-provider evidence is not a real-LLM or teacher-data benchmark.",
        ),
    )
