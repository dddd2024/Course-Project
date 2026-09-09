"""Experiment records and comparison helpers for EvidenceGraph-PRE."""

from course_project.experiments.records import (
    ABLATION_VARIANTS,
    BASELINE_VARIANTS,
    METRIC_GROUND_TRUTH,
    ArtifactReference,
    ComparisonRow,
    DatasetIdentity,
    DependencyVersion,
    ExperimentRecord,
    ExperimentValidationError,
    MetricRecord,
    canonical_record,
    canonical_record_json,
    compare_metric,
    metric_for_dataset,
    record_fingerprint,
)

__all__ = [
    "ABLATION_VARIANTS",
    "BASELINE_VARIANTS",
    "METRIC_GROUND_TRUTH",
    "ArtifactReference",
    "ComparisonRow",
    "DatasetIdentity",
    "DependencyVersion",
    "ExperimentRecord",
    "ExperimentValidationError",
    "MetricRecord",
    "canonical_record",
    "canonical_record_json",
    "compare_metric",
    "metric_for_dataset",
    "record_fingerprint",
]
