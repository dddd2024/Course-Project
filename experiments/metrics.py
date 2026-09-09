"""Deterministic metrics for Track C baselines and ablations."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import TypeVar

from course_project.models import DecisionStatus

MetricItem = TypeVar("MetricItem")


@dataclass(frozen=True, slots=True)
class PrecisionRecallF1:
    true_positive: int
    false_positive: int
    false_negative: int
    precision: float
    recall: float
    f1: float


@dataclass(frozen=True, slots=True)
class SemanticMetrics:
    correct_count: int
    expected_count: int
    predicted_expected_count: int
    false_positive_count: int
    accuracy: float
    coverage: float


@dataclass(frozen=True, slots=True)
class EvaluatedHypothesis:
    """Evaluation-only outcome; ``correct`` must never enter inference."""

    hypothesis_id: str
    field_id: str
    status: DecisionStatus
    score: float
    correct: bool


@dataclass(frozen=True, slots=True)
class HypothesisMetrics:
    hypothesis_count: int
    false_count: int
    accepted_count: int
    accepted_correct_count: int
    false_hypothesis_rate: float
    accepted_precision: float | None
    accepted_coverage: float


@dataclass(frozen=True, slots=True)
class RiskCoveragePoint:
    threshold: float
    selected_count: int
    coverage: float
    risk: float


def boundary_metrics(
    predicted: Iterable[int],
    expected: Iterable[int],
    *,
    tolerance: int = 0,
) -> PrecisionRecallF1:
    """Compute one-to-one packet-boundary metrics with optional offset tolerance."""

    if isinstance(tolerance, bool) or not isinstance(tolerance, int) or tolerance < 0:
        raise ValueError("tolerance must be a non-negative integer")
    predicted_values = _unique_non_negative_ints(predicted, "predicted boundaries")
    expected_values = _unique_non_negative_ints(expected, "expected boundaries")
    matches = _maximum_matches(
        predicted_values,
        expected_values,
        lambda left, right: abs(left - right) <= tolerance,
    )
    return _precision_recall_f1(
        matches, len(predicted_values), len(expected_values)
    )


def field_boundary_metrics(
    predicted: Iterable[tuple[int, int]],
    expected: Iterable[tuple[int, int]],
    *,
    tolerance: int = 0,
) -> PrecisionRecallF1:
    """Compute one-to-one field-region metrics over ``(offset, size)`` pairs."""

    if isinstance(tolerance, bool) or not isinstance(tolerance, int) or tolerance < 0:
        raise ValueError("tolerance must be a non-negative integer")
    predicted_regions = _unique_regions(predicted, "predicted fields")
    expected_regions = _unique_regions(expected, "expected fields")
    matches = _maximum_matches(
        predicted_regions,
        expected_regions,
        lambda left, right: (
            abs(left[0] - right[0]) <= tolerance
            and abs((left[0] + left[1]) - (right[0] + right[1])) <= tolerance
        ),
    )
    return _precision_recall_f1(
        matches, len(predicted_regions), len(expected_regions)
    )


def semantic_metrics(
    predicted: Mapping[str, str], expected: Mapping[str, str]
) -> SemanticMetrics:
    """Evaluate semantics against all truth fields while reporting abstention coverage."""

    _validate_semantic_mapping(predicted, "predicted")
    _validate_semantic_mapping(expected, "expected")
    if not expected:
        raise ValueError("expected semantics must not be empty")

    predicted_expected = set(predicted) & set(expected)
    correct_count = sum(
        predicted[field_id] == expected[field_id] for field_id in predicted_expected
    )
    return SemanticMetrics(
        correct_count=correct_count,
        expected_count=len(expected),
        predicted_expected_count=len(predicted_expected),
        false_positive_count=len(set(predicted) - set(expected)),
        accuracy=correct_count / len(expected),
        coverage=len(predicted_expected) / len(expected),
    )


def ratio_metric(support_count: int, eligible_count: int, *, name: str) -> float:
    """Validate and compute a bounded count ratio such as ParseCoverage."""

    if not isinstance(name, str) or not name:
        raise ValueError("metric name must not be empty")
    support = _count(support_count, f"{name} support_count")
    eligible = _count(eligible_count, f"{name} eligible_count")
    if eligible == 0:
        raise ValueError(f"{name} requires at least one eligible item")
    if support > eligible:
        raise ValueError(f"{name} support_count cannot exceed eligible_count")
    return support / eligible


def hypothesis_metrics(
    outcomes: Iterable[EvaluatedHypothesis],
) -> HypothesisMetrics:
    """Compute false-hypothesis rate and accepted-hypothesis quality."""

    normalized = _validated_outcomes(outcomes)
    if not normalized:
        raise ValueError("hypothesis metrics require at least one outcome")
    false_count = sum(not outcome.correct for outcome in normalized)
    accepted = tuple(
        outcome for outcome in normalized if outcome.status == "accepted"
    )
    accepted_correct = sum(outcome.correct for outcome in accepted)
    return HypothesisMetrics(
        hypothesis_count=len(normalized),
        false_count=false_count,
        accepted_count=len(accepted),
        accepted_correct_count=accepted_correct,
        false_hypothesis_rate=false_count / len(normalized),
        accepted_precision=(
            accepted_correct / len(accepted) if accepted else None
        ),
        accepted_coverage=len(accepted) / len(normalized),
    )


def risk_coverage_curve(
    outcomes: Iterable[EvaluatedHypothesis],
    *,
    accepted_only: bool = True,
) -> tuple[RiskCoveragePoint, ...]:
    """Compute tied-score threshold points without splitting equal scores."""

    if not isinstance(accepted_only, bool):
        raise TypeError("accepted_only must be a boolean")
    normalized = _validated_outcomes(outcomes)
    if not normalized:
        raise ValueError("risk-coverage requires at least one outcome")
    selectable = tuple(
        outcome
        for outcome in normalized
        if not accepted_only or outcome.status == "accepted"
    )
    if not selectable:
        return ()

    ordered = sorted(selectable, key=lambda item: (-item.score, item.hypothesis_id))
    points: list[RiskCoveragePoint] = []
    selected_count = 0
    error_count = 0
    index = 0
    while index < len(ordered):
        threshold = ordered[index].score
        while index < len(ordered) and ordered[index].score == threshold:
            selected_count += 1
            error_count += not ordered[index].correct
            index += 1
        points.append(
            RiskCoveragePoint(
                threshold=threshold,
                selected_count=selected_count,
                coverage=selected_count / len(normalized),
                risk=error_count / selected_count,
            )
        )
    return tuple(points)


def _precision_recall_f1(
    true_positive: int, predicted_count: int, expected_count: int
) -> PrecisionRecallF1:
    false_positive = predicted_count - true_positive
    false_negative = expected_count - true_positive
    if predicted_count == 0 and expected_count == 0:
        precision = recall = f1 = 1.0
    else:
        precision = true_positive / predicted_count if predicted_count else 0.0
        recall = true_positive / expected_count if expected_count else 0.0
        f1 = (
            2.0 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
    return PrecisionRecallF1(
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        precision=precision,
        recall=recall,
        f1=f1,
    )


def _maximum_matches(
    predicted: tuple[MetricItem, ...],
    expected: tuple[MetricItem, ...],
    compatible: Callable[[MetricItem, MetricItem], bool],
) -> int:
    adjacency = tuple(
        tuple(
            expected_index
            for expected_index, expected_item in enumerate(expected)
            if compatible(predicted_item, expected_item)
        )
        for predicted_item in predicted
    )
    matched_prediction: dict[int, int] = {}

    def augment(predicted_index: int, seen: set[int]) -> bool:
        for expected_index in adjacency[predicted_index]:
            if expected_index in seen:
                continue
            seen.add(expected_index)
            previous = matched_prediction.get(expected_index)
            if previous is None or augment(previous, seen):
                matched_prediction[expected_index] = predicted_index
                return True
        return False

    return sum(augment(index, set()) for index in range(len(predicted)))


def _unique_non_negative_ints(
    values: Iterable[int], name: str
) -> tuple[int, ...]:
    normalized = tuple(values)
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in normalized
    ):
        raise ValueError(f"{name} must contain non-negative integers")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} must not contain duplicates")
    return tuple(sorted(normalized))


def _unique_regions(
    values: Iterable[tuple[int, int]], name: str
) -> tuple[tuple[int, int], ...]:
    normalized = tuple(values)
    for value in normalized:
        if not isinstance(value, tuple) or len(value) != 2:
            raise ValueError(f"{name} must contain (offset, size) tuples")
        offset, size = value
        if (
            isinstance(offset, bool)
            or not isinstance(offset, int)
            or offset < 0
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size <= 0
        ):
            raise ValueError(f"{name} regions require non-negative offsets and sizes")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} must not contain duplicates")
    return tuple(sorted(normalized))


def _validate_semantic_mapping(values: Mapping[str, str], name: str) -> None:
    if not isinstance(values, Mapping):
        raise TypeError(f"{name} semantics must be a mapping")
    if any(
        not isinstance(field_id, str)
        or not field_id
        or not isinstance(semantic, str)
        or not semantic
        for field_id, semantic in values.items()
    ):
        raise ValueError(f"{name} semantics require non-empty string keys and values")


def _count(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _validated_outcomes(
    outcomes: Iterable[EvaluatedHypothesis],
) -> tuple[EvaluatedHypothesis, ...]:
    normalized = tuple(outcomes)
    seen_ids: set[str] = set()
    for outcome in normalized:
        if not isinstance(outcome, EvaluatedHypothesis):
            raise TypeError("outcomes must contain EvaluatedHypothesis records")
        if not outcome.hypothesis_id or not outcome.field_id:
            raise ValueError("hypothesis_id and field_id must not be empty")
        if outcome.hypothesis_id in seen_ids:
            raise ValueError(f"duplicate hypothesis_id: {outcome.hypothesis_id}")
        if outcome.status not in {"accepted", "rejected", "uncertain"}:
            raise ValueError(f"invalid hypothesis status: {outcome.status!r}")
        if (
            isinstance(outcome.score, bool)
            or not isinstance(outcome.score, (int, float))
            or not math.isfinite(float(outcome.score))
            or not 0.0 <= float(outcome.score) <= 1.0
        ):
            raise ValueError("hypothesis score must be a finite number in [0, 1]")
        if not isinstance(outcome.correct, bool):
            raise TypeError("hypothesis correct must be a boolean")
        seen_ids.add(outcome.hypothesis_id)
    return normalized
