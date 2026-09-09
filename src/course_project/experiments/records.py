"""Fail-closed experiment records for EvidenceGraph-PRE evaluation.

This module intentionally provides only the project-specific scientific contract.
Generic experiment dashboards/storage can be layered on top later without changing
teacher/synthetic claim discipline or metric evaluability semantics.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any, Literal, Mapping, Sequence

CorpusKind = Literal["teacher", "synthetic", "other"]
ResultScope = Literal["formal_benchmark", "mechanism"]
ExperimentVariant = Literal[
    "heuristic",
    "netzob_pre",
    "llm_only",
    "llm_verification",
    "naive_vote",
    "evidencegraph_pre",
    "ablation_no_verification",
    "ablation_no_provenance",
    "ablation_no_llm",
    "ablation_no_alignment",
]
GroundTruthCapability = Literal[
    "packet_boundaries",
    "field_boundaries",
    "field_semantics",
    "restoration_reference",
    "behavior_labels",
]
MetricName = Literal[
    "packet_boundary_f1",
    "field_boundary_f1",
    "field_semantic_accuracy",
    "false_hypothesis_rate",
    "parse_coverage",
    "constraint_satisfaction_rate",
    "restoration_accuracy",
    "accepted_field_coverage",
    "risk_coverage",
    "processing_time_seconds",
    "token_cost_usd",
]

BASELINE_VARIANTS: tuple[ExperimentVariant, ...] = (
    "heuristic",
    "netzob_pre",
    "llm_only",
    "llm_verification",
    "naive_vote",
    "evidencegraph_pre",
)
ABLATION_VARIANTS: tuple[ExperimentVariant, ...] = (
    "ablation_no_verification",
    "ablation_no_provenance",
    "ablation_no_llm",
    "ablation_no_alignment",
)
ALL_VARIANTS = frozenset((*BASELINE_VARIANTS, *ABLATION_VARIANTS))
GROUND_TRUTH_CAPABILITIES = frozenset(
    {
        "packet_boundaries",
        "field_boundaries",
        "field_semantics",
        "restoration_reference",
        "behavior_labels",
    }
)

METRIC_GROUND_TRUTH: dict[MetricName, frozenset[GroundTruthCapability]] = {
    "packet_boundary_f1": frozenset({"packet_boundaries"}),
    "field_boundary_f1": frozenset({"field_boundaries"}),
    "field_semantic_accuracy": frozenset({"field_semantics"}),
    "false_hypothesis_rate": frozenset({"field_semantics"}),
    "parse_coverage": frozenset(),
    "constraint_satisfaction_rate": frozenset(),
    "restoration_accuracy": frozenset({"restoration_reference"}),
    "accepted_field_coverage": frozenset({"field_semantics"}),
    "risk_coverage": frozenset({"field_semantics"}),
    "processing_time_seconds": frozenset(),
    "token_cost_usd": frozenset(),
}

_RATE_METRICS = frozenset(
    {
        "packet_boundary_f1",
        "field_boundary_f1",
        "field_semantic_accuracy",
        "false_hypothesis_rate",
        "parse_coverage",
        "constraint_satisfaction_rate",
        "restoration_accuracy",
        "accepted_field_coverage",
        "risk_coverage",
    }
)
_LLM_VARIANTS = frozenset(
    {
        "llm_only",
        "llm_verification",
        "evidencegraph_pre",
        "ablation_no_verification",
        "ablation_no_provenance",
        "ablation_no_alignment",
    }
)
_HEX_40 = re.compile(r"^[0-9a-f]{40}$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


class ExperimentValidationError(ValueError):
    """Raised when an experiment record would violate the scientific contract."""


@dataclass(frozen=True, slots=True)
class DatasetIdentity:
    """Auditable identity for one evaluation corpus without storing raw data."""

    dataset_id: str
    corpus_kind: CorpusKind
    sha256: str
    version: str
    size_bytes: int
    ground_truth: frozenset[GroundTruthCapability] = frozenset()
    redistribution_allowed: bool | None = None

    def __post_init__(self) -> None:
        dataset_id = _text(self.dataset_id, "dataset_id")
        version = _text(self.version, "version")
        digest = self.sha256.strip().lower()
        if self.corpus_kind not in {"teacher", "synthetic", "other"}:
            raise ExperimentValidationError(f"unsupported corpus_kind: {self.corpus_kind!r}")
        if not _HEX_64.fullmatch(digest):
            raise ExperimentValidationError("dataset sha256 must be exactly 64 lowercase hex digits")
        if not isinstance(self.size_bytes, int) or isinstance(self.size_bytes, bool):
            raise TypeError("size_bytes must be an integer")
        if self.size_bytes < 0:
            raise ExperimentValidationError("size_bytes must be non-negative")
        unknown = set(self.ground_truth) - GROUND_TRUTH_CAPABILITIES
        if unknown:
            raise ExperimentValidationError(
                f"unknown ground-truth capabilities: {sorted(unknown)!r}"
            )
        if self.redistribution_allowed is not None and not isinstance(
            self.redistribution_allowed, bool
        ):
            raise TypeError("redistribution_allowed must be bool or None")
        object.__setattr__(self, "dataset_id", dataset_id)
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "sha256", digest)
        object.__setattr__(self, "ground_truth", frozenset(self.ground_truth))


@dataclass(frozen=True, slots=True)
class DependencyVersion:
    name: str
    version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _text(self.name, "dependency name"))
        object.__setattr__(self, "version", _text(self.version, "dependency version"))


@dataclass(frozen=True, slots=True)
class ArtifactReference:
    artifact_id: str
    path: str
    sha256: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_id", _text(self.artifact_id, "artifact_id"))
        object.__setattr__(self, "path", _text(self.path, "artifact path"))
        if self.sha256 is not None:
            digest = self.sha256.strip().lower()
            if not _HEX_64.fullmatch(digest):
                raise ExperimentValidationError(
                    "artifact sha256 must be exactly 64 lowercase hex digits"
                )
            object.__setattr__(self, "sha256", digest)


@dataclass(frozen=True, slots=True)
class MetricRecord:
    """One metric value or an explicit not-evaluable result."""

    name: MetricName
    evaluable: bool
    value: float | None
    unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        if self.name not in METRIC_GROUND_TRUTH:
            raise ExperimentValidationError(f"unsupported metric: {self.name!r}")
        if not isinstance(self.evaluable, bool):
            raise TypeError("evaluable must be a boolean")
        if self.evaluable:
            if self.value is None:
                raise ExperimentValidationError("evaluable metric requires a value")
            value = _metric_value(self.name, self.value)
            if self.unavailable_reason is not None:
                raise ExperimentValidationError(
                    "evaluable metric must not carry unavailable_reason"
                )
            object.__setattr__(self, "value", value)
        else:
            if self.value is not None:
                raise ExperimentValidationError(
                    "not-evaluable metric must not fabricate a numeric value"
                )
            object.__setattr__(
                self,
                "unavailable_reason",
                _text(self.unavailable_reason, "unavailable_reason"),
            )


@dataclass(frozen=True, slots=True)
class ExperimentRecord:
    """Deterministic run record for one V2 baseline or ablation."""

    variant: ExperimentVariant
    result_scope: ResultScope
    dataset: DatasetIdentity
    code_sha: str
    config: Mapping[str, Any]
    metrics: tuple[MetricRecord, ...]
    random_seed: int | None = None
    model_provider: str | None = None
    model_version: str | None = None
    dependencies: tuple[DependencyVersion, ...] = ()
    artifacts: tuple[ArtifactReference, ...] = ()
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.variant not in ALL_VARIANTS:
            raise ExperimentValidationError(f"unsupported experiment variant: {self.variant!r}")
        if self.result_scope not in {"formal_benchmark", "mechanism"}:
            raise ExperimentValidationError(f"unsupported result_scope: {self.result_scope!r}")
        if not isinstance(self.dataset, DatasetIdentity):
            raise TypeError("dataset must be DatasetIdentity")
        if self.result_scope == "formal_benchmark" and self.dataset.corpus_kind != "teacher":
            raise ExperimentValidationError(
                "formal benchmark claims require a teacher corpus; synthetic/other results are mechanism evidence"
            )

        code_sha = self.code_sha.strip().lower()
        if not _HEX_40.fullmatch(code_sha):
            raise ExperimentValidationError("code_sha must be exactly 40 lowercase hex digits")
        object.__setattr__(self, "code_sha", code_sha)

        if self.random_seed is not None:
            if not isinstance(self.random_seed, int) or isinstance(self.random_seed, bool):
                raise TypeError("random_seed must be an integer or None")
            if self.random_seed < 0:
                raise ExperimentValidationError("random_seed must be non-negative")

        config = _json_object(self.config, "config")
        object.__setattr__(self, "config", config)

        if self.variant in _LLM_VARIANTS:
            object.__setattr__(
                self, "model_provider", _text(self.model_provider, "model_provider")
            )
            object.__setattr__(
                self, "model_version", _text(self.model_version, "model_version")
            )
        else:
            if self.model_provider is not None:
                object.__setattr__(
                    self, "model_provider", _text(self.model_provider, "model_provider")
                )
            if self.model_version is not None:
                object.__setattr__(
                    self, "model_version", _text(self.model_version, "model_version")
                )

        metrics = tuple(self.metrics)
        if not metrics:
            raise ExperimentValidationError("experiment record requires at least one metric")
        if any(not isinstance(metric, MetricRecord) for metric in metrics):
            raise TypeError("metrics must contain MetricRecord objects")
        _require_unique((metric.name for metric in metrics), "metric")
        for metric in metrics:
            _validate_metric_against_dataset(self.dataset, metric)
        object.__setattr__(self, "metrics", metrics)

        dependencies = tuple(self.dependencies)
        if any(not isinstance(item, DependencyVersion) for item in dependencies):
            raise TypeError("dependencies must contain DependencyVersion objects")
        _require_unique((item.name for item in dependencies), "dependency")
        object.__setattr__(self, "dependencies", dependencies)

        artifacts = tuple(self.artifacts)
        if any(not isinstance(item, ArtifactReference) for item in artifacts):
            raise TypeError("artifacts must contain ArtifactReference objects")
        _require_unique((item.artifact_id for item in artifacts), "artifact")
        object.__setattr__(self, "artifacts", artifacts)

        notes = tuple(_text(note, "note") for note in self.notes)
        object.__setattr__(self, "notes", notes)


@dataclass(frozen=True, slots=True)
class ComparisonRow:
    variant: ExperimentVariant
    value: float
    record_fingerprint: str


def metric_for_dataset(
    dataset: DatasetIdentity,
    name: MetricName,
    value: float | None,
) -> MetricRecord:
    """Create a metric while enforcing ground-truth evaluability.

    If required ground truth is missing, callers must pass ``None``. The function
    returns an explicit not-evaluable record. Supplying a number in that case is
    rejected rather than silently treating it as a benchmark result.
    """

    if not isinstance(dataset, DatasetIdentity):
        raise TypeError("dataset must be DatasetIdentity")
    if name not in METRIC_GROUND_TRUTH:
        raise ExperimentValidationError(f"unsupported metric: {name!r}")
    required = METRIC_GROUND_TRUTH[name]
    missing = sorted(required - dataset.ground_truth)
    if missing:
        if value is not None:
            raise ExperimentValidationError(
                f"metric {name} is not evaluable: dataset lacks ground truth {missing!r}"
            )
        return MetricRecord(
            name=name,
            evaluable=False,
            value=None,
            unavailable_reason=(
                "not evaluable from declared ground truth; missing: " + ", ".join(missing)
            ),
        )
    if value is None:
        raise ExperimentValidationError(
            f"metric {name} is evaluable from declared ground truth and requires a value"
        )
    return MetricRecord(name=name, evaluable=True, value=value)


def canonical_record(record: ExperimentRecord) -> dict[str, Any]:
    """Return the stable JSON-compatible scientific record."""

    if not isinstance(record, ExperimentRecord):
        raise TypeError("record must be ExperimentRecord")
    return {
        "variant": record.variant,
        "resultScope": record.result_scope,
        "dataset": {
            "datasetId": record.dataset.dataset_id,
            "corpusKind": record.dataset.corpus_kind,
            "sha256": record.dataset.sha256,
            "version": record.dataset.version,
            "sizeBytes": record.dataset.size_bytes,
            "groundTruth": sorted(record.dataset.ground_truth),
            "redistributionAllowed": record.dataset.redistribution_allowed,
        },
        "codeSha": record.code_sha,
        "config": dict(record.config),
        "randomSeed": record.random_seed,
        "model": (
            None
            if record.model_provider is None and record.model_version is None
            else {
                "provider": record.model_provider,
                "version": record.model_version,
            }
        ),
        "dependencies": [
            {"name": item.name, "version": item.version}
            for item in sorted(record.dependencies, key=lambda item: (item.name, item.version))
        ],
        "metrics": [
            {
                "name": metric.name,
                "evaluable": metric.evaluable,
                "value": metric.value,
                "unavailableReason": metric.unavailable_reason,
            }
            for metric in sorted(record.metrics, key=lambda item: item.name)
        ],
        "artifacts": [
            {
                "artifactId": item.artifact_id,
                "path": item.path,
                "sha256": item.sha256,
            }
            for item in sorted(record.artifacts, key=lambda item: item.artifact_id)
        ],
        "notes": list(record.notes),
    }


def canonical_record_json(record: ExperimentRecord) -> str:
    """Serialize an experiment record deterministically."""

    return json.dumps(
        canonical_record(record),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def record_fingerprint(record: ExperimentRecord) -> str:
    """Content-derived identity for exact experiment evidence."""

    return hashlib.sha256(canonical_record_json(record).encode("utf-8")).hexdigest()


def compare_metric(
    records: Sequence[ExperimentRecord],
    metric_name: MetricName,
) -> tuple[ComparisonRow, ...]:
    """Compare one metric across variants on exactly the same dataset identity.

    Mixed corpora, duplicate variants, absent metrics and not-evaluable metrics
    all fail closed. This prevents visually convenient but scientifically invalid
    tables from combining incomparable runs.
    """

    normalized = tuple(records)
    if len(normalized) < 2:
        raise ExperimentValidationError("comparison requires at least two experiment records")
    if any(not isinstance(record, ExperimentRecord) for record in normalized):
        raise TypeError("records must contain ExperimentRecord objects")
    if metric_name not in METRIC_GROUND_TRUTH:
        raise ExperimentValidationError(f"unsupported metric: {metric_name!r}")

    first = normalized[0]
    for record in normalized[1:]:
        if record.dataset != first.dataset:
            raise ExperimentValidationError("comparison records must use identical dataset identity")
        if record.result_scope != first.result_scope:
            raise ExperimentValidationError("comparison records must use the same result_scope")
    _require_unique((record.variant for record in normalized), "experiment variant")

    rows: list[ComparisonRow] = []
    for record in normalized:
        matching = [metric for metric in record.metrics if metric.name == metric_name]
        if not matching:
            raise ExperimentValidationError(
                f"variant {record.variant} does not record metric {metric_name}"
            )
        metric = matching[0]
        if not metric.evaluable or metric.value is None:
            raise ExperimentValidationError(
                f"variant {record.variant} metric {metric_name} is not evaluable"
            )
        rows.append(
            ComparisonRow(
                variant=record.variant,
                value=metric.value,
                record_fingerprint=record_fingerprint(record),
            )
        )

    order = {variant: index for index, variant in enumerate((*BASELINE_VARIANTS, *ABLATION_VARIANTS))}
    return tuple(sorted(rows, key=lambda row: order[row.variant]))


def _validate_metric_against_dataset(dataset: DatasetIdentity, metric: MetricRecord) -> None:
    required = METRIC_GROUND_TRUTH[metric.name]
    missing = sorted(required - dataset.ground_truth)
    if missing and metric.evaluable:
        raise ExperimentValidationError(
            f"metric {metric.name} cannot be evaluable; dataset lacks ground truth {missing!r}"
        )
    if not missing and not metric.evaluable:
        reason = metric.unavailable_reason or ""
        if "missing" in reason.lower() and "ground truth" in reason.lower():
            raise ExperimentValidationError(
                f"metric {metric.name} declares missing ground truth that the dataset provides"
            )


def _metric_value(name: MetricName, value: float) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError("metric value must be numeric")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ExperimentValidationError("metric value must be finite")
    if name in _RATE_METRICS and not 0.0 <= parsed <= 1.0:
        raise ExperimentValidationError(f"rate metric {name} must be within [0, 1]")
    if name in {"processing_time_seconds", "token_cost_usd"} and parsed < 0.0:
        raise ExperimentValidationError(f"metric {name} must be non-negative")
    return parsed


def _json_object(value: Mapping[str, Any], name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    try:
        encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)
        decoded = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{name} must be JSON-compatible") from exc
    if not isinstance(decoded, dict):
        raise TypeError(f"{name} must encode to a JSON object")
    return decoded


def _text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ExperimentValidationError(f"{name} must be non-empty")
    return normalized


def _require_unique(values: Sequence[str] | Any, name: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise ExperimentValidationError(f"duplicate {name}: {value}")
        seen.add(value)
