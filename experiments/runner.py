"""Reproducible report builder for EvidenceGraph-PRE comparisons."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from course_project.models import DecisionStatus
from experiments.metrics import (
    EvaluatedHypothesis,
    boundary_metrics,
    field_boundary_metrics,
    hypothesis_metrics,
    ratio_metric,
    risk_coverage_curve,
    semantic_metrics,
)

NOT_EVALUABLE = "not evaluable from provided ground truth"

REQUIRED_COMPARISONS = (
    "heuristic",
    "netzob_binaryinferno",
    "llm_only",
    "llm_verification",
    "naive_vote",
    "evidencegraph_pre",
)
REQUIRED_ABLATIONS = (
    "without_verification",
    "without_provenance",
    "without_llm",
    "without_alignment",
)


@dataclass(frozen=True, slots=True)
class ExperimentManifest:
    experiment_id: str
    dataset_id: str
    dataset_sha256: str
    dataset_version: str
    dataset_kind: Literal["teacher", "synthetic", "controlled"]
    redistribution_allowed: bool
    git_commit: str
    started_at: str
    ended_at: str
    config: dict[str, Any] = field(default_factory=dict)
    random_seed: int | None = None
    provider: str | None = None
    model: str | None = None
    dependency_versions: dict[str, str] = field(default_factory=dict)
    artifact_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GroundTruth:
    """Evaluation-only labels kept separate from inference observations."""

    packet_boundaries: tuple[int, ...] | None = None
    field_boundaries: dict[str, tuple[int, int]] | None = None
    field_semantics: dict[str, str] | None = None
    notes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HypothesisPrediction:
    hypothesis_id: str
    field_id: str
    semantic_type: str
    status: DecisionStatus
    score: float


@dataclass(frozen=True, slots=True)
class RunObservation:
    run_id: str
    method: str
    packet_boundaries: tuple[int, ...] = ()
    field_boundaries: dict[str, tuple[int, int]] = field(default_factory=dict)
    field_semantics: dict[str, str] = field(default_factory=dict)
    hypotheses: tuple[HypothesisPrediction, ...] = ()
    parse_counts: tuple[int, int] | None = None
    constraint_counts: tuple[int, int] | None = None
    restoration_counts: tuple[int, int] | None = None
    processing_time_seconds: float = 0.0
    llm_token_count: int | None = None
    llm_cost: float | None = None
    artifact_refs: tuple[str, ...] = ()


def evaluate_experiment(
    manifest: ExperimentManifest,
    ground_truth: GroundTruth,
    runs: Iterable[RunObservation],
) -> dict[str, Any]:
    """Validate and evaluate runs without exposing truth to inference code."""

    _validate_manifest(manifest)
    _validate_ground_truth(ground_truth)
    normalized_runs = tuple(runs)
    if not normalized_runs:
        raise ValueError("an experiment requires at least one run")
    seen_run_ids: set[str] = set()
    for run in normalized_runs:
        _validate_run(run)
        if run.run_id in seen_run_ids:
            raise ValueError(f"duplicate run_id: {run.run_id}")
        seen_run_ids.add(run.run_id)

    ordered_runs = tuple(sorted(normalized_runs, key=lambda item: item.run_id))
    methods = {run.method for run in ordered_runs}
    return {
        "report_version": 1,
        "manifest": _manifest_payload(manifest),
        "ground_truth": {
            "availability": {
                "packet_boundaries": ground_truth.packet_boundaries is not None,
                "field_boundaries": ground_truth.field_boundaries is not None,
                "field_semantics": ground_truth.field_semantics is not None,
            },
            "notes": dict(sorted(ground_truth.notes.items())),
        },
        "coverage": {
            "comparisons": _requirement_coverage(REQUIRED_COMPARISONS, methods),
            "ablations": _requirement_coverage(REQUIRED_ABLATIONS, methods),
        },
        "runs": [_evaluate_run(run, ground_truth) for run in ordered_runs],
    }


def write_report(report: Mapping[str, Any], destination: str | Path) -> Path:
    """Atomically write one deterministic UTF-8 JSON experiment report."""

    if not isinstance(report, Mapping):
        raise TypeError("report must be a mapping")
    path = Path(destination)
    if path.exists() and path.is_dir():
        raise ValueError("report destination must be a file")
    try:
        serialized = json.dumps(
            report,
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("report must contain only finite JSON values") from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(f"{serialized}\n", encoding="utf-8", newline="\n")
    temporary.replace(path)
    return path


def _evaluate_run(run: RunObservation, truth: GroundTruth) -> dict[str, Any]:
    unavailable = NOT_EVALUABLE
    metrics: dict[str, Any] = {
        "packet_boundary_precision": unavailable,
        "packet_boundary_recall": unavailable,
        "packet_boundary_f1": unavailable,
        "field_boundary_precision": unavailable,
        "field_boundary_recall": unavailable,
        "field_boundary_f1": unavailable,
        "field_semantic_accuracy": unavailable,
        "field_semantic_coverage": unavailable,
        "false_hypothesis_rate": unavailable,
        "accepted_hypothesis_precision": unavailable,
        "accepted_hypothesis_coverage": unavailable,
        "accepted_field_coverage": unavailable,
        "risk_coverage": unavailable,
        "parse_coverage": _optional_ratio(run.parse_counts, "parse_coverage"),
        "constraint_satisfaction_rate": _optional_ratio(
            run.constraint_counts, "constraint_satisfaction_rate"
        ),
        "restoration_accuracy": _optional_ratio(
            run.restoration_counts, "restoration_accuracy"
        ),
        "processing_time_seconds": run.processing_time_seconds,
        "llm_token_count": run.llm_token_count,
        "llm_cost": run.llm_cost,
    }

    if truth.packet_boundaries is not None:
        packet_result = boundary_metrics(
            run.packet_boundaries, truth.packet_boundaries
        )
        metrics.update(
            packet_boundary_precision=packet_result.precision,
            packet_boundary_recall=packet_result.recall,
            packet_boundary_f1=packet_result.f1,
        )
    if truth.field_boundaries is not None:
        field_result = field_boundary_metrics(
            run.field_boundaries.values(), truth.field_boundaries.values()
        )
        metrics.update(
            field_boundary_precision=field_result.precision,
            field_boundary_recall=field_result.recall,
            field_boundary_f1=field_result.f1,
        )
    if truth.field_semantics is not None and truth.field_semantics:
        semantic_result = semantic_metrics(
            run.field_semantics, truth.field_semantics
        )
        metrics.update(
            field_semantic_accuracy=semantic_result.accuracy,
            field_semantic_coverage=semantic_result.coverage,
        )
        if run.hypotheses:
            outcomes = tuple(
                EvaluatedHypothesis(
                    hypothesis_id=item.hypothesis_id,
                    field_id=item.field_id,
                    status=item.status,
                    score=item.score,
                    correct=(
                        truth.field_semantics.get(item.field_id)
                        == item.semantic_type
                    ),
                )
                for item in run.hypotheses
            )
            hypothesis_result = hypothesis_metrics(outcomes)
            accepted_correct_fields = {
                outcome.field_id
                for outcome in outcomes
                if outcome.status == "accepted" and outcome.correct
            }
            metrics.update(
                false_hypothesis_rate=hypothesis_result.false_hypothesis_rate,
                accepted_hypothesis_precision=(
                    hypothesis_result.accepted_precision
                    if hypothesis_result.accepted_precision is not None
                    else unavailable
                ),
                accepted_hypothesis_coverage=hypothesis_result.accepted_coverage,
                accepted_field_coverage=(
                    len(accepted_correct_fields) / len(truth.field_semantics)
                ),
                risk_coverage=[
                    asdict(point) for point in risk_coverage_curve(outcomes)
                ],
            )

    return {
        "run_id": run.run_id,
        "method": run.method,
        "metrics": metrics,
        "artifact_refs": list(run.artifact_refs),
    }


def _manifest_payload(manifest: ExperimentManifest) -> dict[str, Any]:
    return {
        "experiment_id": manifest.experiment_id,
        "dataset": {
            "id": manifest.dataset_id,
            "sha256": manifest.dataset_sha256,
            "version": manifest.dataset_version,
            "kind": manifest.dataset_kind,
            "redistribution_allowed": manifest.redistribution_allowed,
        },
        "git_commit": manifest.git_commit,
        "started_at": manifest.started_at,
        "ended_at": manifest.ended_at,
        "config": manifest.config,
        "random_seed": manifest.random_seed,
        "provider": manifest.provider,
        "model": manifest.model,
        "dependency_versions": dict(sorted(manifest.dependency_versions.items())),
        "artifact_refs": list(manifest.artifact_refs),
    }


def _requirement_coverage(
    required: tuple[str, ...], present: set[str]
) -> dict[str, list[str]]:
    return {
        "required": list(required),
        "present": sorted(set(required) & present),
        "missing": sorted(set(required) - present),
    }


def _optional_ratio(counts: tuple[int, int] | None, name: str) -> float | str:
    if counts is None:
        return NOT_EVALUABLE
    if not isinstance(counts, tuple) or len(counts) != 2:
        raise ValueError(f"{name} counts must be a (support, eligible) tuple")
    return ratio_metric(counts[0], counts[1], name=name)


def _validate_manifest(manifest: ExperimentManifest) -> None:
    if not isinstance(manifest, ExperimentManifest):
        raise TypeError("manifest must be an ExperimentManifest")
    for name, value in (
        ("experiment_id", manifest.experiment_id),
        ("dataset_id", manifest.dataset_id),
        ("dataset_version", manifest.dataset_version),
    ):
        if not isinstance(value, str) or not value:
            raise ValueError(f"{name} must not be empty")
    if not re.fullmatch(r"[0-9a-f]{64}", manifest.dataset_sha256):
        raise ValueError("dataset_sha256 must be 64 lowercase hexadecimal characters")
    if manifest.dataset_kind not in {"teacher", "synthetic", "controlled"}:
        raise ValueError(f"invalid dataset_kind: {manifest.dataset_kind!r}")
    if not isinstance(manifest.redistribution_allowed, bool):
        raise TypeError("redistribution_allowed must be a boolean")
    if not re.fullmatch(r"[0-9a-f]{7,64}", manifest.git_commit):
        raise ValueError("git_commit must be a lowercase hexadecimal revision")
    started = _timestamp(manifest.started_at, "started_at")
    ended = _timestamp(manifest.ended_at, "ended_at")
    if ended < started:
        raise ValueError("ended_at must not precede started_at")
    if manifest.random_seed is not None and (
        isinstance(manifest.random_seed, bool)
        or not isinstance(manifest.random_seed, int)
    ):
        raise TypeError("random_seed must be an integer or None")
    if (manifest.provider is None) != (manifest.model is None):
        raise ValueError("provider and model must either both be set or both be None")
    for name, optional_value in (
        ("provider", manifest.provider),
        ("model", manifest.model),
    ):
        if optional_value is not None and (
            not isinstance(optional_value, str) or not optional_value
        ):
            raise ValueError(f"{name} must be a non-empty string or None")
    _json_mapping(manifest.config, "config")
    _string_mapping(manifest.dependency_versions, "dependency_versions")
    _artifact_refs(manifest.artifact_refs)


def _validate_ground_truth(truth: GroundTruth) -> None:
    if not isinstance(truth, GroundTruth):
        raise TypeError("ground_truth must be GroundTruth")
    if truth.packet_boundaries is not None:
        boundary_metrics(truth.packet_boundaries, truth.packet_boundaries)
    if truth.field_boundaries is not None:
        _field_mapping(truth.field_boundaries, "ground-truth field_boundaries")
    if truth.field_semantics is not None:
        _string_mapping(truth.field_semantics, "ground-truth field_semantics")
    if truth.field_boundaries is not None and truth.field_semantics is not None:
        unknown = set(truth.field_semantics) - set(truth.field_boundaries)
        if unknown:
            raise ValueError(
                f"field semantics reference unknown boundary ids: {sorted(unknown)}"
            )
    _string_mapping(truth.notes, "ground-truth notes")


def _validate_run(run: RunObservation) -> None:
    if not isinstance(run, RunObservation):
        raise TypeError("runs must contain RunObservation records")
    if not run.run_id or not run.method:
        raise ValueError("run_id and method must not be empty")
    boundary_metrics(run.packet_boundaries, run.packet_boundaries)
    _field_mapping(run.field_boundaries, "run field_boundaries")
    _string_mapping(run.field_semantics, "run field_semantics")
    if not set(run.field_semantics) <= set(run.field_boundaries):
        raise ValueError("run field_semantics must reference predicted field boundaries")
    _validate_predictions(run.hypotheses)
    for counts, name in (
        (run.parse_counts, "parse_coverage"),
        (run.constraint_counts, "constraint_satisfaction_rate"),
        (run.restoration_counts, "restoration_accuracy"),
    ):
        _optional_ratio(counts, name)
    if (
        isinstance(run.processing_time_seconds, bool)
        or not isinstance(run.processing_time_seconds, (int, float))
        or not math.isfinite(float(run.processing_time_seconds))
        or run.processing_time_seconds < 0
    ):
        raise ValueError("processing_time_seconds must be finite and non-negative")
    if run.llm_token_count is not None and (
        isinstance(run.llm_token_count, bool)
        or not isinstance(run.llm_token_count, int)
        or run.llm_token_count < 0
    ):
        raise ValueError("llm_token_count must be a non-negative integer or None")
    if run.llm_cost is not None and (
        isinstance(run.llm_cost, bool)
        or not isinstance(run.llm_cost, (int, float))
        or not math.isfinite(float(run.llm_cost))
        or run.llm_cost < 0
    ):
        raise ValueError("llm_cost must be finite and non-negative or None")
    _artifact_refs(run.artifact_refs)


def _validate_predictions(predictions: tuple[HypothesisPrediction, ...]) -> None:
    seen: set[str] = set()
    for prediction in predictions:
        if not isinstance(prediction, HypothesisPrediction):
            raise TypeError("hypotheses must contain HypothesisPrediction records")
        if not prediction.hypothesis_id or not prediction.field_id:
            raise ValueError("hypothesis_id and field_id must not be empty")
        if not prediction.semantic_type:
            raise ValueError("hypothesis semantic_type must not be empty")
        if prediction.hypothesis_id in seen:
            raise ValueError(f"duplicate hypothesis_id: {prediction.hypothesis_id}")
        if prediction.status not in {"accepted", "rejected", "uncertain"}:
            raise ValueError(f"invalid hypothesis status: {prediction.status!r}")
        if (
            isinstance(prediction.score, bool)
            or not isinstance(prediction.score, (int, float))
            or not math.isfinite(float(prediction.score))
            or not 0.0 <= float(prediction.score) <= 1.0
        ):
            raise ValueError("hypothesis score must be finite and in [0, 1]")
        seen.add(prediction.hypothesis_id)


def _field_mapping(values: Mapping[str, tuple[int, int]], name: str) -> None:
    if not isinstance(values, Mapping):
        raise TypeError(f"{name} must be a mapping")
    _string_keys(values, name)
    field_boundary_metrics(values.values(), values.values())


def _string_mapping(values: Mapping[str, str], name: str) -> None:
    if not isinstance(values, Mapping):
        raise TypeError(f"{name} must be a mapping")
    if any(
        not isinstance(key, str)
        or not key
        or not isinstance(value, str)
        or not value
        for key, value in values.items()
    ):
        raise ValueError(f"{name} requires non-empty string keys and values")


def _string_keys(values: Mapping[Any, Any], name: str) -> None:
    if any(not isinstance(key, str) or not key for key in values):
        raise ValueError(f"{name} requires non-empty string keys")


def _json_mapping(values: Mapping[str, Any], name: str) -> None:
    if not isinstance(values, Mapping):
        raise TypeError(f"{name} must be a mapping")
    _string_keys(values, name)
    try:
        json.dumps(values, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain only finite JSON values") from exc


def _artifact_refs(refs: tuple[str, ...]) -> None:
    if not isinstance(refs, tuple):
        raise TypeError("artifact_refs must be a tuple")
    if len(set(refs)) != len(refs):
        raise ValueError("artifact_refs must not contain duplicates")
    for ref in refs:
        if not isinstance(ref, str) or not ref or "\\" in ref:
            raise ValueError("artifact refs must be non-empty POSIX relative paths")
        parsed = PurePosixPath(ref)
        if parsed.is_absolute() or ".." in parsed.parts:
            raise ValueError("artifact refs must stay within the experiment output")


def _timestamp(value: str, name: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed
