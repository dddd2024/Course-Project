"""Fail-closed behavior-evaluation contract for supervised metric claims.

This module does not train a model. It only decides whether behavior metrics are
scientifically evaluable from the supplied labels/split scope and, when they are,
computes deterministic classification metrics for existing ``BehaviorPrediction``
records.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from course_project.models import BehaviorPrediction

BehaviorLabel = Literal[
    "QUERY", "DOWNLOAD", "UPLOAD", "HEARTBEAT", "STREAM", "UNKNOWN"
]
BehaviorSplitUnit = Literal["flow", "session"]

_BEHAVIOR_LABELS = frozenset(
    {"QUERY", "DOWNLOAD", "UPLOAD", "HEARTBEAT", "STREAM", "UNKNOWN"}
)
_ALLOWED_SPLIT_UNITS = frozenset({"flow", "session"})


@dataclass(frozen=True, slots=True)
class BehaviorEvaluation:
    """Auditable result for one behavior-prediction evaluation."""

    metrics_evaluable: bool
    sample_count: int
    labeled_sample_count: int
    accuracy: float | None
    macro_f1: float | None
    split_unit: BehaviorSplitUnit | None
    observed_labels: tuple[str, ...] = ()
    unavailable_reason: str | None = None


def evaluate_behavior_predictions(
    predictions: Sequence[BehaviorPrediction],
    *,
    labels: Mapping[str, str] | None = None,
    split_unit: str | None = None,
) -> BehaviorEvaluation:
    """Evaluate existing behavior predictions without inventing unsupported metrics.

    ``labels=None`` is the explicit unlabeled/descriptive path. Accuracy and F1 are
    unavailable there. Supplying labels switches to supervised evaluation and
    requires exact flow-id coverage plus a leakage-safe ``flow`` or ``session``
    split declaration.
    """

    normalized = tuple(predictions)
    prediction_by_id: dict[str, BehaviorPrediction] = {}
    for prediction in normalized:
        if not isinstance(prediction, BehaviorPrediction):
            raise TypeError("predictions must contain BehaviorPrediction objects")
        flow_id = _text(prediction.flow_id, "prediction flow_id")
        if flow_id in prediction_by_id:
            raise ValueError(f"duplicate prediction flow_id: {flow_id!r}")
        _behavior_label(prediction.label, "predicted behavior label")
        prediction_by_id[flow_id] = prediction

    if labels is None:
        if split_unit is not None:
            raise ValueError("split_unit is only valid when labels are supplied")
        return BehaviorEvaluation(
            metrics_evaluable=False,
            sample_count=len(normalized),
            labeled_sample_count=0,
            accuracy=None,
            macro_f1=None,
            split_unit=None,
            unavailable_reason=(
                "behavior labels are unavailable; Accuracy/F1 must not be reported"
            ),
        )

    if not normalized:
        raise ValueError("supervised behavior evaluation requires at least one prediction")

    normalized_split = _split_unit(split_unit)
    label_by_id: dict[str, str] = {}
    for raw_flow_id, raw_label in labels.items():
        flow_id = _text(raw_flow_id, "label flow_id")
        if flow_id in label_by_id:
            raise ValueError(f"duplicate label flow_id: {flow_id!r}")
        label_by_id[flow_id] = _behavior_label(raw_label, "behavior label")

    prediction_ids = set(prediction_by_id)
    label_ids = set(label_by_id)
    if prediction_ids != label_ids:
        missing = sorted(prediction_ids - label_ids)
        extra = sorted(label_ids - prediction_ids)
        raise ValueError(
            "behavior labels must match predicted flow IDs exactly; "
            f"missing={missing!r}, extra={extra!r}"
        )

    truth = tuple(label_by_id[flow_id] for flow_id in sorted(prediction_by_id))
    predicted = tuple(
        prediction_by_id[flow_id].label for flow_id in sorted(prediction_by_id)
    )
    observed_labels = tuple(sorted(set(truth) | set(predicted)))
    correct = sum(
        1 for expected, actual in zip(truth, predicted, strict=True) if expected == actual
    )
    accuracy = correct / len(truth)
    macro_f1 = sum(
        _f1_for_label(label, truth=truth, predicted=predicted)
        for label in observed_labels
    ) / len(observed_labels)

    return BehaviorEvaluation(
        metrics_evaluable=True,
        sample_count=len(normalized),
        labeled_sample_count=len(label_by_id),
        accuracy=round(accuracy, 12),
        macro_f1=round(macro_f1, 12),
        split_unit=normalized_split,
        observed_labels=observed_labels,
        unavailable_reason=None,
    )


def _f1_for_label(
    label: str,
    *,
    truth: tuple[str, ...],
    predicted: tuple[str, ...],
) -> float:
    true_positive = sum(
        1
        for expected, actual in zip(truth, predicted, strict=True)
        if expected == label and actual == label
    )
    false_positive = sum(
        1
        for expected, actual in zip(truth, predicted, strict=True)
        if expected != label and actual == label
    )
    false_negative = sum(
        1
        for expected, actual in zip(truth, predicted, strict=True)
        if expected == label and actual != label
    )
    denominator = 2 * true_positive + false_positive + false_negative
    if denominator == 0:
        return 0.0
    return (2 * true_positive) / denominator


def _split_unit(value: str | None) -> BehaviorSplitUnit:
    if value is None:
        raise ValueError(
            "supervised behavior evaluation requires split_unit='flow' or 'session'"
        )
    normalized = _text(value, "split_unit").lower()
    if normalized not in _ALLOWED_SPLIT_UNITS:
        raise ValueError(
            "supervised behavior evaluation rejects packet-level/unknown splits; "
            "split_unit must be 'flow' or 'session'"
        )
    return normalized  # type: ignore[return-value]


def _behavior_label(value: str, label: str) -> str:
    normalized = _text(value, label).upper()
    if normalized not in _BEHAVIOR_LABELS:
        raise ValueError(
            f"{label} must use the frozen behavior vocabulary: "
            f"{sorted(_BEHAVIOR_LABELS)!r}"
        )
    return normalized


def _text(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} must be non-empty")
    return normalized
