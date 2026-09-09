"""External PRE baseline execution through the project scientific record contract.

This module keeps the third-party PRE boundary and the scientific-evaluation
boundary separate. Netzob produces project-native ``FieldCandidate`` objects;
this experiment layer preserves those exact candidates as evidence and performs
an experiment-only structural projection solely to execute ParseCoverage.

The structural projection is not Track C semantic verification and must never be
published as a production ``VerifiedField`` result.
"""

from __future__ import annotations

import hashlib
import json
import platform
from dataclasses import dataclass
from importlib.metadata import version
from time import perf_counter

from course_project.experiments.execution import (
    SyntheticMechanismCorpus,
    build_synthetic_mechanism_corpus,
)
from course_project.experiments.records import (
    ArtifactReference,
    DependencyVersion,
    ExperimentRecord,
    ExperimentValidationError,
    MetricRecord,
    canonical_record_json,
    metric_for_dataset,
)
from course_project.inference.netzob_adapter import PREBaselineResult, run_netzob_baseline
from course_project.io import load_raw
from course_project.models import FieldCandidate, PacketCandidate, VerifiedField
from course_project.verification.provisional_parser import ParseSample, execute_provisional_schema

PINNED_NETZOB_VERSION = "2.0.0"
_CANDIDATE_ARTIFACT_NAME = "netzob-field-candidates.json"
_RECORD_NAME = "netzob_pre.json"
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
class ExternalPREExperimentBundle:
    """Canonical evidence produced by one external PRE mechanism run."""

    corpus: SyntheticMechanismCorpus
    record: ExperimentRecord
    field_candidates: tuple[FieldCandidate, ...]
    candidate_artifact_json: str


def run_live_netzob_mechanism_experiment(*, code_sha: str) -> ExternalPREExperimentBundle:
    """Execute pinned upstream Netzob on the exact redistributable SYN1 corpus."""

    observed_version = version("Netzob")
    if observed_version != PINNED_NETZOB_VERSION:
        raise ExperimentValidationError(
            f"expected Netzob {PINNED_NETZOB_VERSION}, observed {observed_version}"
        )

    corpus = build_synthetic_mechanism_corpus()
    stream = load_raw(corpus.capture, source_id=corpus.dataset.dataset_id)
    packets = _packets_for_messages(corpus.messages)

    started = perf_counter()
    result = run_netzob_baseline(stream, list(packets), min_support=2)
    elapsed = perf_counter() - started

    return build_netzob_experiment_bundle(
        corpus=corpus,
        result=result,
        code_sha=code_sha,
        backend_version=observed_version,
        project_version=version("course-project"),
        python_version=platform.python_version(),
        processing_time_seconds=elapsed,
    )


def build_netzob_experiment_bundle(
    *,
    corpus: SyntheticMechanismCorpus,
    result: PREBaselineResult,
    code_sha: str,
    backend_version: str,
    project_version: str,
    python_version: str,
    processing_time_seconds: float,
) -> ExternalPREExperimentBundle:
    """Build a fail-closed ``netzob_pre`` record from project-native output.

    This function is dependency-free: unit tests inject a project-native
    ``PREBaselineResult`` without importing or installing Netzob.
    """

    if not isinstance(corpus, SyntheticMechanismCorpus):
        raise TypeError("corpus must be SyntheticMechanismCorpus")
    if not isinstance(result, PREBaselineResult):
        raise TypeError("result must be PREBaselineResult")
    if result.backend != "netzob":
        raise ExperimentValidationError("external PRE result backend must be netzob")
    if result.status != "ok":
        detail = result.detail or result.error_category or "unknown failure"
        raise ExperimentValidationError(
            f"Netzob baseline must succeed before recording: {result.status}: {detail}"
        )
    if result.error_category is not None:
        raise ExperimentValidationError("successful Netzob result cannot carry error_category")
    if backend_version != PINNED_NETZOB_VERSION:
        raise ExperimentValidationError(
            f"Netzob experiment is pinned to {PINNED_NETZOB_VERSION}, got {backend_version}"
        )
    if processing_time_seconds < 0:
        raise ExperimentValidationError("processing_time_seconds must be non-negative")

    candidates = tuple(result.field_candidates)
    if not candidates:
        raise ExperimentValidationError("successful Netzob baseline emitted no FieldCandidate")
    if any(not isinstance(candidate, FieldCandidate) for candidate in candidates):
        raise TypeError("Netzob output must contain only project-native FieldCandidate objects")
    if any(candidate.attributes.get("backend") != "netzob" for candidate in candidates):
        raise ExperimentValidationError(
            "every external PRE FieldCandidate must preserve backend=netzob provenance"
        )

    candidate_artifact_json = _canonical_candidate_artifact(corpus, candidates)
    candidate_sha = hashlib.sha256(candidate_artifact_json.encode("utf-8")).hexdigest()

    projected_fields = _structural_projection(candidates)
    try:
        parse_report = execute_provisional_schema(
            projected_fields,
            tuple(
                ParseSample(sample_id=f"message-{index}", payload=message)
                for index, message in enumerate(corpus.messages)
            ),
            corpus_id=corpus.dataset.dataset_id,
            corpus_kind=corpus.dataset.corpus_kind,
        )
    except (TypeError, ValueError) as exc:
        raise ExperimentValidationError(
            f"Netzob structural output is not executable: {type(exc).__name__}: {exc}"
        ) from exc

    metrics = [
        metric_for_dataset(corpus.dataset, metric_name, None)
        for metric_name in _GROUND_TRUTH_METRICS
    ]
    metrics.extend(
        (
            metric_for_dataset(corpus.dataset, "parse_coverage", parse_report.parse_coverage),
            MetricRecord(
                name="constraint_satisfaction_rate",
                evaluable=False,
                value=None,
                unavailable_reason=(
                    "not evaluable for raw Netzob PRE output: structural segmentation "
                    "does not execute the project semantic verifier"
                ),
            ),
            metric_for_dataset(
                corpus.dataset,
                "processing_time_seconds",
                processing_time_seconds,
            ),
            metric_for_dataset(corpus.dataset, "token_cost_usd", 0.0),
        )
    )

    record = ExperimentRecord(
        variant="netzob_pre",
        result_scope="mechanism",
        dataset=corpus.dataset,
        code_sha=code_sha,
        config={
            "backend": "netzob",
            "backendVersion": backend_version,
            "formalBenchmark": False,
            "externalGroundTruthUsed": False,
            "fieldCandidateCount": len(candidates),
            "schemaExecutable": True,
            "projectionSemantics": (
                "experiment-only structural projection from FieldCandidate; "
                "not Track C semantic verification or production VerifiedField acceptance"
            ),
            "sourceDto": "FieldCandidate",
            "productionPromotion": False,
            "candidateArtifactSha256": candidate_sha,
        },
        random_seed=0,
        metrics=tuple(metrics),
        dependencies=(
            DependencyVersion(name="course-project", version=project_version),
            DependencyVersion(name="Netzob", version=backend_version),
            DependencyVersion(name="python", version=python_version),
        ),
        artifacts=(
            ArtifactReference(
                artifact_id="netzob-field-candidates",
                path=_CANDIDATE_ARTIFACT_NAME,
                sha256=candidate_sha,
            ),
        ),
        notes=(
            "Synthetic mechanism evidence only; this is not a teacher-data benchmark.",
            "FieldCandidate candidate_types remain PRE heuristics and are not promoted as verified semantic facts.",
            "The parser projection exists only to measure structural ParseCoverage on exact PRE output.",
        ),
    )
    return ExternalPREExperimentBundle(
        corpus=corpus,
        record=record,
        field_candidates=candidates,
        candidate_artifact_json=candidate_artifact_json,
    )


def write_netzob_experiment_bundle(
    bundle: ExternalPREExperimentBundle, out_dir: "PathLike"
) -> str:
    """Write canonical candidate evidence and ``netzob_pre`` record.

    The return value is the normalized output directory path as a string so the
    helper remains simple for both CLI use and integration tests.
    """

    from pathlib import Path

    if not isinstance(bundle, ExternalPREExperimentBundle):
        raise TypeError("bundle must be ExternalPREExperimentBundle")
    root = Path(out_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)

    candidate_path = root / _CANDIDATE_ARTIFACT_NAME
    candidate_path.write_text(bundle.candidate_artifact_json, encoding="utf-8")
    actual_sha = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
    expected_sha = bundle.record.artifacts[0].sha256
    if actual_sha != expected_sha:
        raise ExperimentValidationError("candidate artifact hash changed during write")

    record_path = root / _RECORD_NAME
    record_path.write_text(canonical_record_json(bundle.record) + "\n", encoding="utf-8")
    return str(root)


PathLike = str | "Path"


def _packets_for_messages(messages: tuple[bytes, ...]) -> tuple[PacketCandidate, ...]:
    packets: list[PacketCandidate] = []
    offset = 0
    for message in messages:
        packets.append(PacketCandidate(offset, offset + len(message), 1.0))
        offset += len(message)
    return tuple(packets)


def _canonical_candidate_artifact(
    corpus: SyntheticMechanismCorpus,
    candidates: tuple[FieldCandidate, ...],
) -> str:
    payload = {
        "backend": "netzob",
        "projectNativeDto": "FieldCandidate",
        "datasetId": corpus.dataset.dataset_id,
        "datasetSha256": corpus.dataset.sha256,
        "semanticVerificationExecuted": False,
        "candidates": [
            {
                "candidateId": candidate.candidate_id,
                "familyId": candidate.family_id,
                "offset": candidate.offset,
                "size": candidate.size,
                "candidateTypes": list(candidate.candidate_types),
                "endian": candidate.endian,
                "score": candidate.score,
                "attributes": dict(candidate.attributes),
            }
            for candidate in sorted(
                candidates,
                key=lambda item: (
                    item.offset,
                    item.size is None,
                    item.size if item.size is not None else 0,
                    item.candidate_id,
                ),
            )
        ],
    }
    try:
        return (
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        )
    except (TypeError, ValueError) as exc:
        raise ExperimentValidationError(
            "Netzob FieldCandidate artifact must be canonical JSON"
        ) from exc


def _structural_projection(
    candidates: tuple[FieldCandidate, ...],
) -> tuple[VerifiedField, ...]:
    """Project PRE ranges for parser execution without semantic promotion."""

    ordered = tuple(
        sorted(
            candidates,
            key=lambda item: (
                item.offset,
                item.size is None,
                item.size if item.size is not None else 0,
                item.candidate_id,
            ),
        )
    )
    projected: list[VerifiedField] = []
    previous_end = 0
    variable_seen = False
    for index, candidate in enumerate(ordered):
        if candidate.offset < 0:
            raise ExperimentValidationError("Netzob candidate offset must be non-negative")
        if candidate.size is not None and candidate.size <= 0:
            raise ExperimentValidationError("Netzob fixed candidate size must be positive")
        if variable_seen:
            raise ExperimentValidationError(
                "Netzob variable-size candidate must be the final structural field"
            )
        if candidate.offset < previous_end:
            raise ExperimentValidationError("Netzob structural candidates overlap")

        projected.append(
            VerifiedField(
                field_id=f"netzob_projection_{index:03d}",
                offset=candidate.offset,
                size=candidate.size,
                semantic_type="unknown",
                interpretation=(
                    "Experiment-only structural projection of a Netzob FieldCandidate; "
                    "not semantically verified"
                ),
                verification_score=0.0,
                evidence_ids=(),
            )
        )
        if candidate.size is None:
            variable_seen = True
        else:
            previous_end = candidate.offset + candidate.size

    if not projected:
        raise ExperimentValidationError("Netzob structural projection is empty")
    return tuple(projected)
