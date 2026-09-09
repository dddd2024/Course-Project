from __future__ import annotations

import json
import platform
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from course_project.experiments.execution import (
    SchemaExecutionSummary,
    SyntheticMechanismCorpus,
    build_synthetic_mechanism_corpus,
    scientific_record_fingerprint,
)
from course_project.experiments.records import (
    DatasetIdentity,
    DependencyVersion,
    ExperimentRecord,
    MetricRecord,
    canonical_record_json,
    metric_for_dataset,
)
from course_project.llm import (
    HypothesisProposal,
    LLMHypothesisRequest,
    LLMProviderResult,
    materialize_hypotheses,
)
from course_project.models import Evidence, InputMetadata, VerifiedField
from course_project.sidecar import DeterministicTrackCSemanticBackend, TrackDBaselineBackend
from course_project.verification.provisional_parser import ParseSample, execute_provisional_schema

DETERMINISTIC_MECHANISM_PROVIDER = "deterministic-evidencegraph-mechanism"
DETERMINISTIC_MECHANISM_MODEL_VERSION = "1"
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
class FullEvidenceGraphMechanismExecution:
    """One auditable full-method mechanism run on the fixed synthetic corpus."""

    corpus: SyntheticMechanismCorpus
    record: ExperimentRecord
    audit: dict[str, object]


class DeterministicEvidenceGraphMechanismProvider:
    """Network-free provider fixture that exercises the real production LLM seam.

    This fixture is deliberately not presented as an LLM-quality baseline. It returns
    a lower-confidence correct length interpretation and a higher-confidence wrong
    endian interpretation for executable length candidates. The production verifier,
    provenance-aware fusion and global selection must therefore determine the result.
    """

    provider_name = DETERMINISTIC_MECHANISM_PROVIDER
    mode = "mock"

    def __init__(self) -> None:
        self.requests: list[LLMHypothesisRequest] = []

    def propose(self, request: LLMHypothesisRequest) -> LLMProviderResult:
        self.requests.append(request)
        candidate = request.context.get("candidate")
        if not isinstance(candidate, dict):
            return self._empty_result()

        candidate_types = candidate.get("candidateTypes")
        size = candidate.get("size")
        offset = candidate.get("offset")
        endian = candidate.get("declaredEndian")
        match_hint = candidate.get("matchHint")
        if not isinstance(candidate_types, list) or "length" not in candidate_types:
            return self._empty_result()
        if not isinstance(offset, int) or isinstance(offset, bool):
            return self._empty_result()
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            return self._empty_result()
        if endian not in {"big", "little"}:
            return self._empty_result()

        if match_hint == "total":
            parameters: dict[str, Any] = {
                "endian": endian,
                "target": "full_message",
            }
        elif match_hint == "payload_after":
            parameters = {
                "endian": endian,
                "target": "payload",
                "header_size": offset + size,
            }
        else:
            return self._empty_result()

        proposals = [
            HypothesisProposal(
                offset=offset,
                size=size,
                semantic_type="length",
                interpretation="mechanism provider correct endian length",
                parameters=parameters,
                model_confidence=0.61,
                supporting_evidence_ids=request.allowed_evidence_ids,
            )
        ]
        if size > 1:
            wrong_parameters = dict(parameters)
            wrong_parameters["endian"] = "little" if endian == "big" else "big"
            proposals.append(
                HypothesisProposal(
                    offset=offset,
                    size=size,
                    semantic_type="length",
                    interpretation="mechanism provider deliberately wrong endian length",
                    parameters=wrong_parameters,
                    model_confidence=0.97,
                    supporting_evidence_ids=request.allowed_evidence_ids,
                )
            )

        return LLMProviderResult(
            provider=self.provider_name,
            mode=self.mode,
            hypotheses=materialize_hypotheses(
                provider_name=self.provider_name,
                request=request,
                proposals=tuple(proposals),
            ),
            metadata={
                "networkAccess": False,
                "model": DETERMINISTIC_MECHANISM_MODEL_VERSION,
                "structuredOutput": True,
            },
        )

    def _empty_result(self) -> LLMProviderResult:
        return LLMProviderResult(
            provider=self.provider_name,
            mode=self.mode,
            metadata={
                "networkAccess": False,
                "model": DETERMINISTIC_MECHANISM_MODEL_VERSION,
                "structuredOutput": True,
            },
        )


def run_full_evidencegraph_mechanism_experiment(
    work_dir: Path,
    *,
    code_sha: str,
) -> FullEvidenceGraphMechanismExecution:
    """Execute the complete production architecture as mechanism evidence.

    The injected deterministic provider makes the run reproducible and credential-free.
    The resulting `evidencegraph_pre` record proves orchestration and verification/fusion
    execution only; it makes no claim about real-model semantic quality or teacher-data
    performance.
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
        metadata={"experimentScope": "synthetic-full-evidencegraph-mechanism"},
    )
    provider = DeterministicEvidenceGraphMechanismProvider()
    state_dir = root / "full-method-state"
    started = perf_counter()
    result = TrackDBaselineBackend(
        state_dir=state_dir,
        semantic_backend=DeterministicTrackCSemanticBackend(llm_provider=provider),
    ).analyze(
        task_id="synthetic-full-evidencegraph-pre",
        input_metadata=input_metadata,
        input_path=capture_path,
        config=_semantic_config(),
    )
    elapsed = perf_counter() - started

    semantic_metrics = _validate_full_result(
        result,
        expected_messages=len(corpus.messages),
        provider_request_count=len(provider.requests),
    )
    provider_audit = _provider_hypothesis_audit(result.evidence, result.findings)
    fields = _schema_fields_from_result(result, state_dir=state_dir)
    schema = _schema_execution(fields, corpus)
    constraint_rate = _constraint_satisfaction_rate(fields, result.evidence)

    dependencies = (
        DependencyVersion(name="course-project", version="0.1.0"),
        DependencyVersion(name="python", version=platform.python_version()),
    )
    record = _full_method_record(
        corpus.dataset,
        code_sha=code_sha,
        schema=schema,
        constraint_satisfaction_rate=constraint_rate,
        processing_time_seconds=elapsed,
        dependencies=dependencies,
        semantic_metrics=semantic_metrics,
        provider_audit=provider_audit,
        field_count=len(fields),
    )
    audit: dict[str, object] = {
        "datasetId": corpus.dataset.dataset_id,
        "datasetSha256": corpus.dataset.sha256,
        "variant": "evidencegraph_pre",
        "resultScope": "mechanism",
        "provider": DETERMINISTIC_MECHANISM_PROVIDER,
        "modelVersion": DETERMINISTIC_MECHANISM_MODEL_VERSION,
        "networkAccess": False,
        "realLLMBenchmark": False,
        "teacherBenchmark": False,
        "providerRequestCount": len(provider.requests),
        "providerHypothesisCount": provider_audit["providerHypothesisCount"],
        "acceptedProviderHypothesisCount": provider_audit[
            "acceptedProviderHypothesisCount"
        ],
        "rejectedWrongHypothesisCount": provider_audit["rejectedWrongHypothesisCount"],
        "wrongHypothesisMaxConfidence": provider_audit["wrongHypothesisMaxConfidence"],
        "correctHypothesisMaxConfidence": provider_audit["correctHypothesisMaxConfidence"],
        "verifiedFieldCount": len(fields),
        "schemaExecutable": schema.executable,
        "parseCoverage": schema.parse_coverage,
        "constraintSatisfactionRate": constraint_rate,
    }
    return FullEvidenceGraphMechanismExecution(corpus=corpus, record=record, audit=audit)


def write_full_evidencegraph_mechanism_execution(
    execution: FullEvidenceGraphMechanismExecution,
    output_dir: Path,
) -> Path:
    """Write canonical full-method mechanism evidence without rewriting old records."""

    if not isinstance(execution, FullEvidenceGraphMechanismExecution):
        raise TypeError("execution must be FullEvidenceGraphMechanismExecution")
    target = output_dir.expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    (target / "evidencegraph_pre.json").write_text(
        canonical_record_json(execution.record) + "\n",
        encoding="utf-8",
    )
    (target / "evidencegraph_pre.audit.json").write_text(
        json.dumps(execution.audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "datasetId": execution.corpus.dataset.dataset_id,
        "datasetSha256": execution.corpus.dataset.sha256,
        "datasetVersion": execution.corpus.dataset.version,
        "variant": "evidencegraph_pre",
        "resultScope": "mechanism",
        "model": {
            "provider": execution.record.model_provider,
            "version": execution.record.model_version,
        },
        "formalBenchmark": False,
        "realLLMBenchmark": False,
        "scientificFingerprint": scientific_record_fingerprint(execution.record),
    }
    (target / "full-method-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def _semantic_config() -> dict[str, object]:
    return {
        "mode": "evidencegraph",
        "stages": ["boundary", "inference", "evidence", "verification", "export"],
        "llmEnabled": True,
        "verificationEnabled": True,
        "behaviorEnabled": False,
        "optionalDependencyPolicy": "degrade",
    }


def _validate_full_result(
    result: Any,
    *,
    expected_messages: int,
    provider_request_count: int,
) -> dict[str, Any]:
    if result.status != "completed":
        raise ValueError(f"full EvidenceGraph-PRE mechanism path did not complete: {result.status!r}")
    if result.metrics.get("messageCount") != expected_messages:
        raise ValueError("production boundary detection did not recover the complete corpus")
    semantic = result.metrics.get("semanticMetrics")
    if not isinstance(semantic, dict):
        raise TypeError("production semantic metrics are missing")
    required_true = (
        "llmRequested",
        "llmExecuted",
        "verificationExecuted",
        "fusionExecuted",
        "globalSelectionExecuted",
    )
    for name in required_true:
        if semantic.get(name) is not True:
            raise ValueError(f"full method did not execute required semantic stage: {name}")
    if semantic.get("llmRequestCount") != provider_request_count or provider_request_count <= 0:
        raise ValueError("provider request accounting does not match the executed provider")
    hypothesis_count = semantic.get("llmHypothesisCount")
    if not isinstance(hypothesis_count, int) or hypothesis_count < 2:
        raise ValueError("full method emitted fewer than two provider hypotheses")
    if result.metrics.get("verifiedFieldCount", 0) <= 0:
        raise ValueError("full method emitted no accepted verified fields")
    return semantic


def _provider_hypothesis_audit(
    evidence: tuple[Evidence, ...],
    findings: tuple[Any, ...],
) -> dict[str, int | float]:
    provider_evidence = tuple(
        item for item in evidence if item.source_component == "track-c-llm-provider"
    )
    if not provider_evidence:
        raise ValueError("full method emitted no provider evidence")

    verifier_status: dict[str, str] = {}
    for item in evidence:
        if item.source_component != "track-c-executable-verifier":
            continue
        hypothesis_id = item.observation.get("hypothesisId")
        status = item.observation.get("status")
        if isinstance(hypothesis_id, str) and status in {"accepted", "rejected", "uncertain"}:
            verifier_status[hypothesis_id] = str(status)

    finding_status = {
        finding.finding_id.removeprefix("finding:"): finding.status for finding in findings
    }
    correct: list[tuple[str, float]] = []
    wrong: list[tuple[str, float]] = []
    for item in provider_evidence:
        hypothesis_id = item.observation.get("hypothesisId")
        interpretation = item.observation.get("interpretation")
        confidence = item.observation.get("modelConfidence")
        if not isinstance(hypothesis_id, str):
            continue
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            continue
        if interpretation == "mechanism provider correct endian length":
            correct.append((hypothesis_id, float(confidence)))
        elif interpretation == "mechanism provider deliberately wrong endian length":
            wrong.append((hypothesis_id, float(confidence)))

    accepted_correct = [
        item
        for item in correct
        if verifier_status.get(item[0]) == "accepted"
        and finding_status.get(item[0]) == "accepted"
    ]
    rejected_wrong = [item for item in wrong if verifier_status.get(item[0]) == "rejected"]
    if not accepted_correct:
        raise ValueError("no correct provider hypothesis survived verification and fusion")
    if not rejected_wrong:
        raise ValueError("no deliberately wrong provider hypothesis was rejected")

    correct_max = max(confidence for _, confidence in correct)
    wrong_max = max(confidence for _, confidence in wrong)
    if wrong_max <= correct_max:
        raise ValueError("mechanism fixture must rank the wrong hypothesis above the correct one")
    return {
        "providerHypothesisCount": len(provider_evidence),
        "acceptedProviderHypothesisCount": len(accepted_correct),
        "rejectedWrongHypothesisCount": len(rejected_wrong),
        "wrongHypothesisMaxConfidence": wrong_max,
        "correctHypothesisMaxConfidence": correct_max,
    }


def _schema_fields_from_result(result: Any, *, state_dir: Path) -> tuple[VerifiedField, ...]:
    schema_artifacts = [artifact for artifact in result.artifacts if artifact.type == "schema"]
    if len(schema_artifacts) != 1:
        raise ValueError("expected exactly one production schema artifact")
    schema_path = state_dir / schema_artifacts[0].ref
    payload = json.loads(schema_path.read_text(encoding="utf-8"))
    fields_payload = payload.get("fields")
    if not isinstance(fields_payload, list) or not fields_payload:
        raise ValueError("production schema artifact contains no fields")
    return tuple(
        VerifiedField(
            field_id=str(item["fieldId"]),
            offset=int(item["offset"]),
            size=item.get("size") if item.get("size") is None else int(item["size"]),
            semantic_type=str(item["semanticType"]),
            interpretation=str(item["interpretation"]),
            verification_score=float(item["verificationScore"]),
            evidence_ids=tuple(str(value) for value in item.get("evidenceIds", ())),
        )
        for item in fields_payload
        if isinstance(item, dict)
    )


def _schema_execution(
    fields: tuple[VerifiedField, ...],
    corpus: SyntheticMechanismCorpus,
) -> SchemaExecutionSummary:
    if not fields:
        return SchemaExecutionSummary(
            parse_coverage=0.0,
            executable=False,
            error="no emitted fields; no provisional schema can execute",
        )
    try:
        report = execute_provisional_schema(
            fields,
            tuple(
                ParseSample(sample_id=f"message-{index}", payload=message)
                for index, message in enumerate(corpus.messages)
            ),
            corpus_id=corpus.dataset.dataset_id,
            corpus_kind="synthetic",
        )
    except (TypeError, ValueError) as exc:
        return SchemaExecutionSummary(
            parse_coverage=0.0,
            executable=False,
            error=f"{type(exc).__name__}: {exc}",
        )
    return SchemaExecutionSummary(
        parse_coverage=report.parse_coverage,
        executable=True,
        error=None,
    )


def _constraint_satisfaction_rate(
    fields: tuple[VerifiedField, ...],
    evidence: tuple[Evidence, ...],
) -> float:
    if not fields:
        return 0.0
    verifier_status = {
        item.evidence_id: item.observation.get("status")
        for item in evidence
        if item.source_component == "track-c-executable-verifier"
    }
    satisfied = 0
    for field in fields:
        verifier_ids = [
            evidence_id for evidence_id in field.evidence_ids if evidence_id in verifier_status
        ]
        if len(verifier_ids) != 1:
            raise ValueError(
                f"field {field.field_id!r} does not map to exactly one verifier evidence record"
            )
        if verifier_status[verifier_ids[0]] == "accepted":
            satisfied += 1
    return satisfied / len(fields)


def _full_method_record(
    dataset: DatasetIdentity,
    *,
    code_sha: str,
    schema: SchemaExecutionSummary,
    constraint_satisfaction_rate: float,
    processing_time_seconds: float,
    dependencies: tuple[DependencyVersion, ...],
    semantic_metrics: dict[str, Any],
    provider_audit: dict[str, int | float],
    field_count: int,
) -> ExperimentRecord:
    metrics: list[MetricRecord] = [
        metric_for_dataset(dataset, name, None) for name in _GROUND_TRUTH_METRICS
    ]
    metrics.extend(
        (
            metric_for_dataset(dataset, "parse_coverage", schema.parse_coverage),
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
        variant="evidencegraph_pre",
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
            "provenanceAwareFusionEnabled": True,
            "globalSelectionEnabled": True,
            "semanticBackend": "production-llm-aware-track-c",
            "llmContextPolicy": semantic_metrics.get("llmContextPolicy"),
            "llmRequestCount": semantic_metrics.get("llmRequestCount"),
            "llmHypothesisCount": semantic_metrics.get("llmHypothesisCount"),
            "acceptedProviderHypothesisCount": provider_audit[
                "acceptedProviderHypothesisCount"
            ],
            "rejectedWrongHypothesisCount": provider_audit["rejectedWrongHypothesisCount"],
            "schemaExecutable": schema.executable,
            "schemaExecutionError": schema.error,
            "fieldCount": field_count,
            "timingScope": "track-d-to-llm-track-c-verification-fusion-selection-schema",
        },
        random_seed=0,
        model_provider=DETERMINISTIC_MECHANISM_PROVIDER,
        model_version=DETERMINISTIC_MECHANISM_MODEL_VERSION,
        metrics=tuple(metrics),
        dependencies=dependencies,
        notes=(
            "Deterministic provider exercises the full production architecture but is not a real LLM semantic-quality benchmark.",
            "Synthetic mechanism evidence is not teacher-data benchmark evidence.",
            "The deliberately higher-confidence wrong endian hypothesis must be rejected by executable verification.",
        ),
    )


def _validate_code_sha(code_sha: str) -> None:
    if len(code_sha) != 40 or any(
        character not in "0123456789abcdef" for character in code_sha
    ):
        raise ValueError("code_sha must be a lowercase 40-character Git SHA")
