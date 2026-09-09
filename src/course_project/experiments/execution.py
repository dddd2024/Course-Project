"""Executable synthetic mechanism experiments for EvidenceGraph-PRE research.

This module closes the gap between the project-native :mod:`records` contract
and actual project execution.  It deliberately uses a tiny redistributable
synthetic corpus and never labels its results as teacher-data benchmarks.

The currently executable variants are:

* ``heuristic`` - Track D boundary/inference candidates accepted by a fixed
  score threshold, without executable verification in the decision path;
* ``naive_vote`` - equal-source voting over the real candidate/alignment/
  verifier evidence materialized by the production semantic path;
* ``ablation_no_llm`` - the current production provenance-aware executable
  verification/fusion path.  It is intentionally *not* labeled
  ``evidencegraph_pre`` because the current production backend does not invoke
  an LLM hypothesis provider.
"""

from __future__ import annotations

import hashlib
import json
import platform
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable

from course_project.boundary import detect_boundaries, to_message_candidates
from course_project.evidence import DecisionVote, naive_multi_source_vote
from course_project.experiments.records import (
    DatasetIdentity,
    DependencyVersion,
    ExperimentRecord,
    ExperimentValidationError,
    MetricRecord,
    canonical_record,
    canonical_record_json,
    compare_metric,
    metric_for_dataset,
)
from course_project.inference import family_analysis, infer_field_candidates
from course_project.io import load_dat
from course_project.models import Evidence, FieldCandidate, InputMetadata, VerifiedField
from course_project.sidecar import DeterministicTrackCSemanticBackend, TrackDBaselineBackend
from course_project.verification.provisional_parser import ParseSample, execute_provisional_schema

SYNTHETIC_DATASET_ID = "synthetic-mechanism-v1"
SYNTHETIC_DATASET_VERSION = "1"
_SYNTHETIC_MESSAGE_COUNT = 8
_SYNTHETIC_PAYLOAD = b"P" * 8
_HEURISTIC_THRESHOLD = 0.75
_EXECUTED_VARIANTS = ("heuristic", "naive_vote", "ablation_no_llm")
_GROUND_TRUTH_METRICS = (
    "packet_boundary_f1",
    "field_boundary_f1",
    "field_semantic_accuracy",
    "false_hypothesis_rate",
    "restoration_accuracy",
    "accepted_field_coverage",
    "risk_coverage",
)
_STABLE_COMPARISON_METRICS = ("parse_coverage", "constraint_satisfaction_rate")


@dataclass(frozen=True, slots=True)
class SyntheticMechanismCorpus:
    """Exact redistributable corpus bytes and their project experiment identity."""

    capture: bytes
    messages: tuple[bytes, ...]
    dataset: DatasetIdentity


@dataclass(frozen=True, slots=True)
class ExperimentExecutionBundle:
    """Executed records plus a timing-independent comparison artifact."""

    corpus: SyntheticMechanismCorpus
    records: tuple[ExperimentRecord, ...]
    comparison: dict[str, object]


def build_synthetic_mechanism_corpus() -> SyntheticMechanismCorpus:
    """Build the fixed SYN1 corpus used only for mechanism/reproducibility tests."""

    messages = tuple(
        _make_message(msg_type=0x01, seq=index + 1, payload=_SYNTHETIC_PAYLOAD)
        for index in range(_SYNTHETIC_MESSAGE_COUNT)
    )
    capture = b"".join(messages)
    digest = hashlib.sha256(capture).hexdigest()
    dataset = DatasetIdentity(
        dataset_id=SYNTHETIC_DATASET_ID,
        corpus_kind="synthetic",
        sha256=digest,
        version=SYNTHETIC_DATASET_VERSION,
        size_bytes=len(capture),
        ground_truth=frozenset(),
        redistribution_allowed=True,
    )
    return SyntheticMechanismCorpus(capture=capture, messages=messages, dataset=dataset)


def run_synthetic_mechanism_experiments(
    work_dir: Path,
    *,
    code_sha: str,
) -> ExperimentExecutionBundle:
    """Execute the three currently honest mechanism variants on one exact corpus.

    ``processing_time_seconds`` is retained as operational evidence in each exact
    run record.  Scientific identity and the comparison artifact intentionally
    exclude that volatile timing metric via :func:`scientific_record_fingerprint`.
    """

    _validate_code_sha(code_sha)
    root = work_dir.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    corpus = build_synthetic_mechanism_corpus()
    capture_path = root / "capture.dat"
    capture_path.write_bytes(corpus.capture)

    input_metadata = InputMetadata(
        input_id=SYNTHETIC_DATASET_ID,
        kind="dat",
        size_bytes=len(corpus.capture),
        sha256=corpus.dataset.sha256,
        metadata={"experimentScope": "synthetic-mechanism"},
    )

    # Run the production no-LLM path first.  Its evidence is also the evaluator
    # for the two controls: verifier outcomes can assess constraint satisfaction
    # without entering the heuristic decision itself.
    full_start = perf_counter()
    production_result = TrackDBaselineBackend(
        state_dir=root / "production-state",
        semantic_backend=DeterministicTrackCSemanticBackend(),
    ).analyze(
        task_id="synthetic-ablation-no-llm",
        input_metadata=input_metadata,
        input_path=capture_path,
        config=_semantic_config(),
    )
    full_elapsed = perf_counter() - full_start
    _validate_production_result(production_result, expected_messages=len(corpus.messages))
    production_fields = _schema_fields_from_result(
        production_result,
        state_dir=root / "production-state",
    )

    reference_evidence = tuple(production_result.evidence)
    verification_by_candidate = _verification_status_by_candidate(reference_evidence)

    heuristic_start = perf_counter()
    stream = load_dat(capture_path, source_id=input_metadata.input_id)
    packets = detect_boundaries(stream)
    candidates = infer_field_candidates(stream, packets)
    heuristic_fields = _heuristic_fields(candidates)
    heuristic_parse = _parse_coverage(heuristic_fields, corpus)
    heuristic_constraints = _constraint_satisfaction_rate(
        heuristic_fields,
        verification_by_candidate,
    )
    heuristic_elapsed = perf_counter() - heuristic_start

    naive_start = perf_counter()
    naive_fields = _naive_vote_fields(production_result.findings, reference_evidence)
    naive_parse = _parse_coverage(naive_fields, corpus)
    naive_constraints = _constraint_satisfaction_rate(
        naive_fields,
        verification_by_candidate,
    )
    naive_elapsed = perf_counter() - naive_start

    production_parse = _parse_coverage(production_fields, corpus)
    production_constraints = _constraint_satisfaction_rate(
        production_fields,
        verification_by_candidate,
    )

    dependencies = (
        DependencyVersion(name="course-project", version="0.1.0"),
        DependencyVersion(name="python", version=platform.python_version()),
    )
    records = (
        _record(
            "heuristic",
            corpus.dataset,
            code_sha=code_sha,
            parse_coverage=heuristic_parse,
            constraint_satisfaction_rate=heuristic_constraints,
            processing_time_seconds=heuristic_elapsed,
            dependencies=dependencies,
            config={
                "decisionPolicy": "track-d-candidate-score-threshold",
                "heuristicThreshold": _HEURISTIC_THRESHOLD,
                "candidateTypes": ["length", "sequence"],
                "timingScope": "track-d-boundary-inference-decision-and-schema",
                "fieldCount": len(heuristic_fields),
            },
        ),
        _record(
            "naive_vote",
            corpus.dataset,
            code_sha=code_sha,
            parse_coverage=naive_parse,
            constraint_satisfaction_rate=naive_constraints,
            processing_time_seconds=naive_elapsed,
            dependencies=dependencies,
            config={
                "decisionPolicy": "strict-majority-equal-source-vote",
                "evidenceMaterialization": "production-no-llm-semantic-path",
                "timingScope": "naive-decision-and-schema-after-shared-evidence-materialization",
                "fieldCount": len(naive_fields),
            },
        ),
        _record(
            "ablation_no_llm",
            corpus.dataset,
            code_sha=code_sha,
            parse_coverage=production_parse,
            constraint_satisfaction_rate=production_constraints,
            processing_time_seconds=full_elapsed,
            dependencies=dependencies,
            config={
                "decisionPolicy": "production-provenance-aware-fusion",
                "semanticBackend": production_result.metrics.get("semanticBackend"),
                "llmEnabled": False,
                "verificationEnabled": True,
                "timingScope": "track-d-to-track-c-production-end-to-end",
                "fieldCount": len(production_fields),
            },
        ),
    )
    comparison = build_stable_comparison(records)
    return ExperimentExecutionBundle(corpus=corpus, records=records, comparison=comparison)


def scientific_record_fingerprint(record: ExperimentRecord) -> str:
    """Fingerprint scientific content while excluding volatile wall-clock timing."""

    payload = canonical_record(record)
    metrics = payload.get("metrics")
    if not isinstance(metrics, list):
        raise ExperimentValidationError("canonical record metrics must be a list")
    payload["metrics"] = [
        metric
        for metric in metrics
        if isinstance(metric, dict) and metric.get("name") != "processing_time_seconds"
    ]
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_stable_comparison(records: Iterable[ExperimentRecord]) -> dict[str, object]:
    """Build deterministic same-dataset comparison rows for stable mechanism metrics."""

    normalized = tuple(records)
    if set(record.variant for record in normalized) != set(_EXECUTED_VARIANTS):
        raise ExperimentValidationError(
            f"expected exactly executed variants {_EXECUTED_VARIANTS!r}"
        )
    by_variant = {record.variant: record for record in normalized}
    metrics: dict[str, list[dict[str, object]]] = {}
    for metric_name in _STABLE_COMPARISON_METRICS:
        rows = compare_metric(normalized, metric_name)
        metrics[metric_name] = [
            {
                "variant": row.variant,
                "value": row.value,
                "scientificFingerprint": scientific_record_fingerprint(
                    by_variant[row.variant]
                ),
            }
            for row in rows
        ]

    first = normalized[0]
    return {
        "dataset": {
            "datasetId": first.dataset.dataset_id,
            "kind": first.dataset.corpus_kind,
            "sha256": first.dataset.sha256,
            "version": first.dataset.version,
        },
        "resultScope": first.result_scope,
        "variants": list(_EXECUTED_VARIANTS),
        "metrics": metrics,
        "timingExcludedFromScientificFingerprint": True,
    }


def write_experiment_bundle(bundle: ExperimentExecutionBundle, output_dir: Path) -> Path:
    """Write canonical records and the stable comparison artifact."""

    target = output_dir.expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    for record in bundle.records:
        (target / f"{record.variant}.json").write_text(
            canonical_record_json(record) + "\n",
            encoding="utf-8",
        )
    (target / "comparison.json").write_text(
        json.dumps(bundle.comparison, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "datasetId": bundle.corpus.dataset.dataset_id,
        "datasetSha256": bundle.corpus.dataset.sha256,
        "datasetVersion": bundle.corpus.dataset.version,
        "resultScope": "mechanism",
        "variants": [record.variant for record in bundle.records],
        "scientificFingerprints": {
            record.variant: scientific_record_fingerprint(record)
            for record in bundle.records
        },
        "formalBenchmark": False,
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def _make_message(msg_type: int, seq: int, payload: bytes) -> bytes:
    total = 11 + len(payload)
    return (
        b"SYN1"
        + bytes([msg_type])
        + b"\x00\x00\x00"
        + bytes([seq])
        + total.to_bytes(2, "big")
        + payload
    )


def _semantic_config() -> dict[str, object]:
    return {
        "mode": "evidencegraph",
        "stages": ["boundary", "inference", "evidence", "verification", "export"],
        "llmEnabled": False,
        "verificationEnabled": True,
        "behaviorEnabled": False,
        "optionalDependencyPolicy": "degrade",
    }


def _validate_production_result(result: Any, *, expected_messages: int) -> None:
    if result.status != "completed":
        raise ExperimentValidationError(
            f"production no-LLM path did not complete: {result.status!r}"
        )
    if result.metrics.get("messageCount") != expected_messages:
        raise ExperimentValidationError(
            "production boundary detection did not recover the complete synthetic corpus"
        )
    semantic_metrics = result.metrics.get("semanticMetrics")
    if not isinstance(semantic_metrics, dict):
        raise ExperimentValidationError("production semantic metrics are missing")
    if semantic_metrics.get("verificationExecuted") is not True:
        raise ExperimentValidationError("production executable verification did not run")
    if semantic_metrics.get("fusionExecuted") is not True:
        raise ExperimentValidationError("production provenance-aware fusion did not run")
    if result.metrics.get("verifiedFieldCount", 0) <= 0:
        raise ExperimentValidationError("production path emitted no accepted verified fields")


def _schema_fields_from_result(result: Any, *, state_dir: Path) -> tuple[VerifiedField, ...]:
    schema_artifacts = [artifact for artifact in result.artifacts if artifact.type == "schema"]
    if len(schema_artifacts) != 1:
        raise ExperimentValidationError("expected exactly one production schema artifact")
    schema_path = state_dir / schema_artifacts[0].ref
    payload = json.loads(schema_path.read_text(encoding="utf-8"))
    fields_payload = payload.get("fields")
    if not isinstance(fields_payload, list) or not fields_payload:
        raise ExperimentValidationError("production schema artifact contains no fields")
    fields: list[VerifiedField] = []
    for item in fields_payload:
        if not isinstance(item, dict):
            raise ExperimentValidationError("production schema field must be an object")
        fields.append(
            VerifiedField(
                field_id=str(item["fieldId"]),
                offset=int(item["offset"]),
                size=item.get("size") if item.get("size") is None else int(item["size"]),
                semantic_type=str(item["semanticType"]),
                interpretation=str(item["interpretation"]),
                verification_score=float(item["verificationScore"]),
                evidence_ids=tuple(str(value) for value in item.get("evidenceIds", ())),
            )
        )
    return tuple(fields)


def _heuristic_fields(candidates: Iterable[FieldCandidate]) -> tuple[VerifiedField, ...]:
    selected: list[tuple[FieldCandidate, str]] = []
    for candidate in candidates:
        semantic = next(
            (kind for kind in candidate.candidate_types if kind in {"length", "sequence"}),
            None,
        )
        if semantic is None:
            continue
        if candidate.size is None or candidate.size <= 0 or candidate.endian is None:
            continue
        if candidate.score < _HEURISTIC_THRESHOLD:
            continue
        selected.append((candidate, semantic))

    chosen: list[tuple[FieldCandidate, str]] = []
    occupied: list[tuple[int, int]] = []
    for candidate, semantic in sorted(
        selected,
        key=lambda item: (-item[0].score, item[0].offset, item[0].candidate_id),
    ):
        assert candidate.size is not None
        region = (candidate.offset, candidate.offset + candidate.size)
        if any(start < region[1] and region[0] < end for start, end in occupied):
            continue
        occupied.append(region)
        chosen.append((candidate, semantic))

    return tuple(
        VerifiedField(
            field_id=f"heuristic_field_{index}",
            offset=candidate.offset,
            size=candidate.size,
            semantic_type=semantic,
            interpretation=f"heuristic {semantic} candidate above fixed score threshold",
            verification_score=float(candidate.score),
            evidence_ids=(f"candidate:{candidate.candidate_id}",),
        )
        for index, (candidate, semantic) in enumerate(
            sorted(chosen, key=lambda item: (item[0].offset, item[0].candidate_id))
        )
    )


def _naive_vote_fields(findings: Iterable[Any], evidence: tuple[Evidence, ...]) -> tuple[VerifiedField, ...]:
    evidence_by_id = {item.evidence_id: item for item in evidence}
    fields: list[VerifiedField] = []
    for finding in findings:
        relevant = tuple(
            evidence_by_id[evidence_id]
            for evidence_id in finding.evidence_ids
            if evidence_id in evidence_by_id
        )
        candidate_records = tuple(
            item for item in relevant if item.source_component == "track-d-field-candidate"
        )
        if len(candidate_records) != 1:
            raise ExperimentValidationError(
                f"finding {finding.finding_id!r} does not map to exactly one candidate"
            )
        verifier_records = tuple(
            item for item in relevant if item.source_component == "track-c-executable-verifier"
        )
        if len(verifier_records) != 1:
            raise ExperimentValidationError(
                f"finding {finding.finding_id!r} does not map to exactly one verifier result"
            )
        hypothesis_id = verifier_records[0].observation.get("hypothesisId")
        if not isinstance(hypothesis_id, str) or not hypothesis_id:
            raise ExperimentValidationError("verifier evidence has no hypothesis id")

        votes = tuple(
            DecisionVote(
                source_id=source,
                hypothesis_id=hypothesis_id,
                status=_source_status(records),
            )
            for source, records in _group_by_source(relevant)
        )
        vote = naive_multi_source_vote(hypothesis_id, votes)
        if vote.status != "accepted":
            continue
        fields.append(
            _field_from_candidate_evidence(
                candidate_records[0],
                prefix="naive",
                index=len(fields),
                score=vote.accepted_votes / max(vote.total_votes, 1),
                evidence_ids=tuple(sorted(item.evidence_id for item in relevant)),
            )
        )
    return _non_overlapping_fields(fields)


def _group_by_source(evidence: Iterable[Evidence]) -> tuple[tuple[str, tuple[Evidence, ...]], ...]:
    grouped: dict[str, list[Evidence]] = {}
    for item in evidence:
        grouped.setdefault(item.source_component, []).append(item)
    return tuple(
        (source, tuple(grouped[source])) for source in sorted(grouped)
    )


def _source_status(records: tuple[Evidence, ...]) -> str:
    statuses = {_evidence_status(item) for item in records}
    if len(statuses) != 1:
        return "uncertain"
    return statuses.pop()


def _evidence_status(item: Evidence) -> str:
    if item.source_component == "track-c-executable-verifier":
        status = item.observation.get("status")
        if status not in {"accepted", "rejected", "uncertain"}:
            raise ExperimentValidationError("verifier evidence has non-canonical status")
        return str(status)
    stance = item.observation.get("stance", "support")
    if stance == "support":
        return "accepted"
    if stance == "conflict":
        return "rejected"
    if stance == "neutral":
        return "uncertain"
    raise ExperimentValidationError(
        f"evidence {item.evidence_id!r} has unsupported stance {stance!r}"
    )


def _field_from_candidate_evidence(
    item: Evidence,
    *,
    prefix: str,
    index: int,
    score: float,
    evidence_ids: tuple[str, ...],
) -> VerifiedField:
    observation = item.observation
    candidate_types = observation.get("candidateTypes")
    if not isinstance(candidate_types, list):
        raise ExperimentValidationError("candidate evidence has no candidateTypes list")
    semantic = next(
        (kind for kind in candidate_types if kind in {"length", "sequence"}),
        None,
    )
    if semantic is None:
        raise ExperimentValidationError("candidate evidence is not an executable semantic type")
    size = observation.get("size")
    offset = observation.get("offset")
    if not isinstance(offset, int) or isinstance(offset, bool):
        raise ExperimentValidationError("candidate evidence offset is not an integer")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise ExperimentValidationError("candidate evidence size is not a positive integer")
    return VerifiedField(
        field_id=f"{prefix}_field_{index}",
        offset=offset,
        size=size,
        semantic_type=str(semantic),
        interpretation=f"{prefix} baseline accepted {semantic} hypothesis",
        verification_score=max(0.0, min(1.0, float(score))),
        evidence_ids=evidence_ids,
    )


def _non_overlapping_fields(fields: Iterable[VerifiedField]) -> tuple[VerifiedField, ...]:
    selected: list[VerifiedField] = []
    for field in sorted(
        fields,
        key=lambda item: (-item.verification_score, item.offset, item.field_id),
    ):
        if field.size is None:
            continue
        end = field.offset + field.size
        if any(
            existing.size is not None
            and existing.offset < end
            and field.offset < existing.offset + existing.size
            for existing in selected
        ):
            continue
        selected.append(field)
    return tuple(sorted(selected, key=lambda item: (item.offset, item.field_id)))


def _verification_status_by_candidate(evidence: Iterable[Evidence]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for item in evidence:
        if item.source_component != "track-c-executable-verifier":
            continue
        status = item.observation.get("status")
        if status not in {"accepted", "rejected", "uncertain"}:
            raise ExperimentValidationError("verifier evidence has non-canonical status")
        if len(item.parent_evidence_ids) != 1:
            raise ExperimentValidationError(
                "verifier evidence must have exactly one candidate parent for experiment evaluation"
            )
        parent = item.parent_evidence_ids[0]
        previous = statuses.get(parent)
        if previous is not None and previous != status:
            raise ExperimentValidationError(
                f"candidate {parent!r} has conflicting verifier outcomes"
            )
        statuses[parent] = str(status)
    if not statuses:
        raise ExperimentValidationError("production path emitted no executable-verifier evidence")
    return statuses


def _parse_coverage(fields: tuple[VerifiedField, ...], corpus: SyntheticMechanismCorpus) -> float:
    if not fields:
        return 0.0
    report = execute_provisional_schema(
        fields,
        tuple(
            ParseSample(sample_id=f"message-{index}", payload=message)
            for index, message in enumerate(corpus.messages)
        ),
        corpus_id=corpus.dataset.dataset_id,
        corpus_kind="synthetic",
    )
    return report.parse_coverage


def _constraint_satisfaction_rate(
    fields: tuple[VerifiedField, ...],
    verification_by_candidate: dict[str, str],
) -> float:
    if not fields:
        return 0.0
    satisfied = 0
    for field in fields:
        candidate_ids = [
            evidence_id
            for evidence_id in field.evidence_ids
            if evidence_id in verification_by_candidate
        ]
        if len(candidate_ids) != 1:
            raise ExperimentValidationError(
                f"field {field.field_id!r} does not map to exactly one verified candidate"
            )
        if verification_by_candidate[candidate_ids[0]] == "accepted":
            satisfied += 1
    return satisfied / len(fields)


def _record(
    variant: str,
    dataset: DatasetIdentity,
    *,
    code_sha: str,
    parse_coverage: float,
    constraint_satisfaction_rate: float,
    processing_time_seconds: float,
    dependencies: tuple[DependencyVersion, ...],
    config: dict[str, object],
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
            metric_for_dataset(
                dataset,
                "processing_time_seconds",
                processing_time_seconds,
            ),
            metric_for_dataset(dataset, "token_cost_usd", 0.0),
        )
    )
    return ExperimentRecord(
        variant=variant,  # type: ignore[arg-type]
        result_scope="mechanism",
        dataset=dataset,
        code_sha=code_sha,
        config={
            "datasetLayout": "SYN1/type/reserved/seq/length-be/payload",
            "externalGroundTruthUsed": False,
            "formalBenchmark": False,
            **config,
        },
        random_seed=0,
        metrics=tuple(metrics),
        dependencies=dependencies,
    )


def _validate_code_sha(code_sha: str) -> None:
    if len(code_sha) != 40 or any(character not in "0123456789abcdef" for character in code_sha):
        raise ExperimentValidationError("code_sha must be a lowercase 40-character Git SHA")
