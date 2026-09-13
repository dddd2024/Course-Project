from __future__ import annotations

import hashlib
import json
import platform
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

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
    _schema_execution,
    _schema_fields_from_result,
    _semantic_config,
    _validate_code_sha,
    _validate_full_result,
)
from course_project.experiments.records import (
    DependencyVersion,
    ExperimentRecord,
    MetricRecord,
    canonical_record_json,
    metric_for_dataset,
)
from course_project.models import (
    AlignmentResult,
    BehaviorFeatures,
    FieldCandidate,
    InputMetadata,
    MessageCandidate,
    MessageFamily,
    PacketCandidate,
)
from course_project.sidecar import DeterministicTrackCSemanticBackend, TrackDBaselineBackend
from course_project.sidecar.semantic_bridge import SemanticAnalysis

ALIGNMENT_ABLATION_SCOPE = "alignment_evidence_contribution"
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
class NoAlignmentAblationExecution:
    """Auditable one-factor removal of alignment evidence at the Track C seam."""

    corpus: SyntheticMechanismCorpus
    record: ExperimentRecord
    audit: dict[str, object]


class _NoAlignmentEvidenceSemanticBackend:
    """Experiment-only wrapper that removes only Track C alignment input."""

    def __init__(self, provider: DeterministicEvidenceGraphMechanismProvider) -> None:
        self._inner = DeterministicTrackCSemanticBackend(llm_provider=provider)

    def analyze(
        self,
        *,
        input_metadata: InputMetadata,
        input_path: Path,
        packets: tuple[PacketCandidate, ...],
        messages: tuple[MessageCandidate, ...],
        families: tuple[MessageFamily, ...],
        alignments: tuple[AlignmentResult, ...],
        field_candidates: tuple[FieldCandidate, ...],
        large_raw_profile: Mapping[str, Any] | None,
        behavior: BehaviorFeatures | None,
        config: Mapping[str, Any],
    ) -> SemanticAnalysis:
        del alignments
        return self._inner.analyze(
            input_metadata=input_metadata,
            input_path=input_path,
            packets=packets,
            messages=messages,
            families=families,
            alignments=(),
            field_candidates=field_candidates,
            large_raw_profile=large_raw_profile,
            behavior=behavior,
            config=config,
        )


def run_no_alignment_ablation(
    work_dir: Path,
    *,
    code_sha: str,
) -> NoAlignmentAblationExecution:
    """Execute the alignment-evidence contribution ablation on the fixed fixture.

    Track D still performs its normal deterministic preprocessing.  The paired
    control and ablation therefore receive identical messages, families and field
    candidates.  The experiment changes exactly one Track C input: the ablation
    semantic backend receives ``alignments=()``.
    """

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
        metadata={"experimentScope": "synthetic-no-alignment-evidence-ablation"},
    )

    control_provider = DeterministicEvidenceGraphMechanismProvider()
    ablation_provider = DeterministicEvidenceGraphMechanismProvider()
    control_state = root / "control-state"
    ablation_state = root / "ablation-state"

    control_result = TrackDBaselineBackend(
        state_dir=control_state,
        semantic_backend=DeterministicTrackCSemanticBackend(llm_provider=control_provider),
    ).analyze(
        task_id="synthetic-no-alignment-control",
        input_metadata=input_metadata,
        input_path=capture_path,
        config=_semantic_config(),
    )
    control_semantic = _validate_full_result(
        control_result,
        expected_messages=len(corpus.messages),
        provider_request_count=len(control_provider.requests),
    )

    started = perf_counter()
    ablation_result = TrackDBaselineBackend(
        state_dir=ablation_state,
        semantic_backend=_NoAlignmentEvidenceSemanticBackend(ablation_provider),
    ).analyze(
        task_id="synthetic-ablation-no-alignment",
        input_metadata=input_metadata,
        input_path=capture_path,
        config=_semantic_config(),
    )
    elapsed = perf_counter() - started
    ablation_semantic = _validate_ablation_result(
        ablation_result,
        expected_messages=len(corpus.messages),
        provider_request_count=len(ablation_provider.requests),
    )

    control_structural = _structural_fingerprint(
        control_state, "synthetic-no-alignment-control"
    )
    ablation_structural = _structural_fingerprint(
        ablation_state, "synthetic-ablation-no-alignment"
    )
    if control_structural != ablation_structural:
        raise ValueError("Track D structural intermediates changed in the alignment ablation")

    control_provider_fp = _provider_hypothesis_fingerprint(control_result.evidence)
    ablation_provider_fp = _provider_hypothesis_fingerprint(ablation_result.evidence)
    if control_provider_fp != ablation_provider_fp:
        raise ValueError("provider hypotheses changed when alignment evidence was removed")

    wrong_rejected = _rejected_wrong_hypothesis_count(ablation_result.evidence)
    if wrong_rejected <= 0:
        raise ValueError("alignment ablation failed to preserve executable rejection of wrong hypothesis")

    fields = (
        _schema_fields_from_result(ablation_result, state_dir=ablation_state)
        if ablation_result.metrics.get("verifiedFieldCount", 0) > 0
        else ()
    )
    schema = _schema_execution(fields, corpus)
    constraint_rate = (
        _constraint_satisfaction_rate(fields, ablation_result.evidence) if fields else 0.0
    )
    decision_changed_count = _decision_changed_count(
        control_result.findings, ablation_result.findings
    )

    dependencies = (
        DependencyVersion(name="course-project", version="0.1.0"),
        DependencyVersion(name="python", version=platform.python_version()),
    )
    metrics: list[MetricRecord] = [
        metric_for_dataset(corpus.dataset, name, None) for name in _GROUND_TRUTH_METRICS
    ]
    metrics.extend(
        (
            metric_for_dataset(corpus.dataset, "parse_coverage", schema.parse_coverage),
            metric_for_dataset(
                corpus.dataset, "constraint_satisfaction_rate", constraint_rate
            ),
            metric_for_dataset(corpus.dataset, "processing_time_seconds", elapsed),
            metric_for_dataset(corpus.dataset, "token_cost_usd", 0.0),
        )
    )
    record = ExperimentRecord(
        variant="ablation_no_alignment",
        result_scope="mechanism",
        dataset=corpus.dataset,
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
            "provenanceAwareFusionEnabled": True,
            "globalSelectionEnabled": True,
            "ablationScope": ALIGNMENT_ABLATION_SCOPE,
            "trackCAlignmentInputRemoved": True,
            "alignmentEvidenceUsed": False,
            "preprocessingAlignmentStillUsed": True,
            "structuralIntermediatesMatchControl": True,
            "providerHypothesesMatchControl": True,
            "controlAlignmentEvidenceCount": control_semantic.get("alignmentEvidenceCount"),
            "ablationAlignmentEvidenceCount": ablation_semantic.get("alignmentEvidenceCount"),
            "decisionChangedCount": decision_changed_count,
            "schemaExecutable": schema.executable,
            "schemaExecutionError": schema.error,
            "fieldCount": len(fields),
        },
        random_seed=0,
        model_provider=DETERMINISTIC_MECHANISM_PROVIDER,
        model_version=DETERMINISTIC_MECHANISM_MODEL_VERSION,
        metrics=tuple(metrics),
        dependencies=dependencies,
        notes=(
            "One-factor mechanism ablation of alignment evidence at the Track C semantic seam.",
            "Track D preprocessing alignment remains enabled so messages/families/field candidates stay fixed.",
            "This is not a claim that the entire PRE preprocessing pipeline ran without alignment.",
            "Synthetic mechanism evidence is not teacher-data or real-LLM benchmark evidence.",
        ),
    )
    audit: dict[str, object] = {
        "datasetId": corpus.dataset.dataset_id,
        "datasetSha256": corpus.dataset.sha256,
        "variant": "ablation_no_alignment",
        "resultScope": "mechanism",
        "ablationScope": ALIGNMENT_ABLATION_SCOPE,
        "preprocessingAlignmentStillUsed": True,
        "trackCAlignmentInputRemoved": True,
        "structuralIntermediatesMatchControl": True,
        "providerHypothesesMatchControl": True,
        "controlAlignmentEvidenceCount": control_semantic.get("alignmentEvidenceCount"),
        "ablationAlignmentEvidenceCount": ablation_semantic.get("alignmentEvidenceCount"),
        "ablationFusionEvidenceProducers": ablation_semantic.get("fusionEvidenceProducers"),
        "verificationExecuted": ablation_semantic.get("verificationExecuted"),
        "fusionExecuted": ablation_semantic.get("fusionExecuted"),
        "globalSelectionExecuted": ablation_semantic.get("globalSelectionExecuted"),
        "providerRequestCount": len(ablation_provider.requests),
        "rejectedWrongHypothesisCount": wrong_rejected,
        "decisionChangedCount": decision_changed_count,
        "verifiedFieldCount": len(fields),
        "schemaExecutable": schema.executable,
        "parseCoverage": schema.parse_coverage,
        "constraintSatisfactionRate": constraint_rate,
        "networkAccess": False,
        "teacherBenchmark": False,
        "realLLMBenchmark": False,
    }
    return NoAlignmentAblationExecution(corpus=corpus, record=record, audit=audit)


def write_no_alignment_ablation_execution(
    execution: NoAlignmentAblationExecution,
    output_dir: Path,
) -> Path:
    if not isinstance(execution, NoAlignmentAblationExecution):
        raise TypeError("execution must be NoAlignmentAblationExecution")
    target = output_dir.expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    (target / "ablation_no_alignment.json").write_text(
        canonical_record_json(execution.record) + "\n", encoding="utf-8"
    )
    (target / "ablation_no_alignment.audit.json").write_text(
        json.dumps(execution.audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "datasetId": execution.corpus.dataset.dataset_id,
        "datasetSha256": execution.corpus.dataset.sha256,
        "datasetVersion": execution.corpus.dataset.version,
        "variant": "ablation_no_alignment",
        "resultScope": "mechanism",
        "ablationScope": ALIGNMENT_ABLATION_SCOPE,
        "preprocessingAlignmentStillUsed": True,
        "formalBenchmark": False,
        "realLLMBenchmark": False,
        "scientificFingerprint": scientific_record_fingerprint(execution.record),
    }
    (target / "ablation-no-alignment-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def _validate_ablation_result(
    result: Any,
    *,
    expected_messages: int,
    provider_request_count: int,
) -> dict[str, Any]:
    if result.status not in {"completed", "partial"}:
        raise ValueError(f"alignment ablation did not complete safely: {result.status!r}")
    if result.metrics.get("messageCount") != expected_messages:
        raise ValueError("alignment ablation changed the recovered message corpus")
    semantic = result.metrics.get("semanticMetrics")
    if not isinstance(semantic, dict):
        raise TypeError("alignment ablation semantic metrics are missing")
    for name in (
        "llmRequested",
        "llmExecuted",
        "verificationExecuted",
        "fusionExecuted",
        "globalSelectionExecuted",
    ):
        if semantic.get(name) is not True:
            raise ValueError(f"alignment ablation unexpectedly disabled semantic stage: {name}")
    if semantic.get("alignmentEvidenceCount") != 0:
        raise ValueError("alignment ablation emitted alignment evidence")
    producers = semantic.get("fusionEvidenceProducers")
    if not isinstance(producers, list) or "track-d-alignment" in producers:
        raise ValueError("alignment evidence still participated in ablation fusion")
    if semantic.get("llmRequestCount") != provider_request_count or provider_request_count <= 0:
        raise ValueError("alignment ablation provider request accounting is invalid")
    return semantic


def _structural_fingerprint(state_dir: Path, task_id: str) -> str:
    digest = hashlib.sha256()
    for filename in ("messages.json", "alignment.json"):
        payload = (state_dir / "tasks" / task_id / "artifacts" / filename).read_bytes()
        digest.update(filename.encode("utf-8"))
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")
    return digest.hexdigest()


def _provider_hypothesis_fingerprint(evidence: tuple[Any, ...]) -> str:
    rows = [
        item.observation
        for item in evidence
        if item.source_component == "track-c-llm-provider"
    ]
    if not rows:
        raise ValueError("provider emitted no hypothesis evidence")
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _rejected_wrong_hypothesis_count(evidence: tuple[Any, ...]) -> int:
    wrong_ids = {
        item.observation.get("hypothesisId")
        for item in evidence
        if item.source_component == "track-c-llm-provider"
        and item.observation.get("interpretation")
        == "mechanism provider deliberately wrong endian length"
    }
    rejected = {
        item.observation.get("hypothesisId")
        for item in evidence
        if item.source_component == "track-c-executable-verifier"
        and item.observation.get("status") == "rejected"
    }
    return len({item for item in wrong_ids if isinstance(item, str)} & rejected)


def _decision_changed_count(control_findings: tuple[Any, ...], ablation_findings: tuple[Any, ...]) -> int:
    control = {item.finding_id: item.status for item in control_findings}
    ablation = {item.finding_id: item.status for item in ablation_findings}
    if set(control) != set(ablation):
        raise ValueError("alignment ablation changed the hypothesis set")
    return sum(control[key] != ablation[key] for key in control)
