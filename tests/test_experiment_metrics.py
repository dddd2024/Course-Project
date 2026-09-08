import pytest

from experiments.metrics import (
    EvaluatedHypothesis,
    boundary_metrics,
    field_boundary_metrics,
    hypothesis_metrics,
    ratio_metric,
    risk_coverage_curve,
    semantic_metrics,
)


def outcome(
    hypothesis_id: str,
    *,
    status: str,
    score: float,
    correct: bool,
    field_id: str | None = None,
) -> EvaluatedHypothesis:
    return EvaluatedHypothesis(
        hypothesis_id=hypothesis_id,
        field_id=field_id or hypothesis_id,
        status=status,  # type: ignore[arg-type]
        score=score,
        correct=correct,
    )


def test_packet_boundary_metrics_are_one_to_one_with_tolerance() -> None:
    exact = boundary_metrics((10, 20, 30, 50), (10, 21, 30, 40))
    tolerant = boundary_metrics((10, 20, 22), (10, 21), tolerance=1)

    assert exact.true_positive == 2
    assert exact.false_positive == 2
    assert exact.false_negative == 2
    assert exact.precision == exact.recall == exact.f1 == 0.5
    assert tolerant.true_positive == 2
    assert tolerant.false_positive == 1
    assert tolerant.false_negative == 0


def test_empty_boundary_sets_are_perfect_and_one_sided_sets_are_not() -> None:
    assert boundary_metrics((), ()).f1 == 1.0
    assert boundary_metrics((1,), ()).f1 == 0.0
    assert boundary_metrics((), (1,)).f1 == 0.0


def test_field_boundary_metrics_match_both_region_edges() -> None:
    metrics = field_boundary_metrics(
        ((0, 4), (5, 2), (10, 2)),
        ((0, 4), (4, 3), (20, 2)),
        tolerance=1,
    )

    assert metrics.true_positive == 2
    assert metrics.false_positive == 1
    assert metrics.false_negative == 1
    assert metrics.f1 == pytest.approx(2 / 3)


@pytest.mark.parametrize(
    "function,predicted,expected",
    [
        (boundary_metrics, (1, 1), (1,)),
        (boundary_metrics, (-1,), (1,)),
        (field_boundary_metrics, ((0, 0),), ((0, 1),)),
        (field_boundary_metrics, ((0, 1), (0, 1)), ((0, 1),)),
    ],
)
def test_invalid_or_duplicate_boundaries_fail_closed(
    function: object, predicted: object, expected: object
) -> None:
    with pytest.raises(ValueError):
        function(predicted, expected)  # type: ignore[operator]


def test_semantic_accuracy_penalizes_abstention_and_reports_false_positives() -> None:
    metrics = semantic_metrics(
        {"field-1": "length", "field-2": "enum", "extra": "timestamp"},
        {"field-1": "length", "field-2": "sequence", "field-3": "checksum"},
    )

    assert metrics.correct_count == 1
    assert metrics.expected_count == 3
    assert metrics.predicted_expected_count == 2
    assert metrics.false_positive_count == 1
    assert metrics.accuracy == pytest.approx(1 / 3)
    assert metrics.coverage == pytest.approx(2 / 3)


def test_ratio_metrics_cover_parse_constraint_and_restoration_counts() -> None:
    assert ratio_metric(9, 10, name="parse_coverage") == 0.9
    assert ratio_metric(18, 20, name="constraint_satisfaction") == 0.9
    assert ratio_metric(99, 100, name="restoration_accuracy") == 0.99


@pytest.mark.parametrize(
    "support,eligible",
    [(-1, 1), (2, 1), (0, 0), (True, 1)],
)
def test_invalid_ratio_counts_fail_closed(support: int, eligible: int) -> None:
    with pytest.raises(ValueError):
        ratio_metric(support, eligible, name="parse_coverage")


def test_hypothesis_metrics_keep_false_rate_separate_from_acceptance() -> None:
    metrics = hypothesis_metrics(
        (
            outcome("h1", status="accepted", score=0.95, correct=True),
            outcome("h2", status="accepted", score=0.90, correct=False),
            outcome("h3", status="rejected", score=0.20, correct=False),
            outcome("h4", status="uncertain", score=0.55, correct=True),
        )
    )

    assert metrics.hypothesis_count == 4
    assert metrics.false_hypothesis_rate == 0.5
    assert metrics.accepted_precision == 0.5
    assert metrics.accepted_coverage == 0.5


def test_no_accepted_hypotheses_has_zero_coverage_and_undefined_precision() -> None:
    metrics = hypothesis_metrics(
        (outcome("h1", status="uncertain", score=0.5, correct=True),)
    )

    assert metrics.accepted_count == 0
    assert metrics.accepted_coverage == 0.0
    assert metrics.accepted_precision is None


def test_risk_coverage_curve_groups_equal_thresholds() -> None:
    outcomes = (
        outcome("h1", status="accepted", score=0.9, correct=True),
        outcome("h2", status="accepted", score=0.8, correct=False),
        outcome("h3", status="accepted", score=0.8, correct=True),
        outcome("h4", status="uncertain", score=0.7, correct=False),
    )

    points = risk_coverage_curve(outcomes)

    assert len(points) == 2
    assert points[0].threshold == 0.9
    assert points[0].coverage == 0.25
    assert points[0].risk == 0.0
    assert points[1].threshold == 0.8
    assert points[1].selected_count == 3
    assert points[1].coverage == 0.75
    assert points[1].risk == pytest.approx(1 / 3)


def test_risk_coverage_can_measure_all_predictions() -> None:
    outcomes = (
        outcome("h1", status="accepted", score=0.8, correct=True),
        outcome("h2", status="uncertain", score=0.7, correct=False),
    )

    points = risk_coverage_curve(outcomes, accepted_only=False)

    assert points[-1].coverage == 1.0
    assert points[-1].risk == 0.5


def test_invalid_hypothesis_outcomes_fail_closed() -> None:
    duplicate = (
        outcome("same", status="accepted", score=0.9, correct=True),
        outcome("same", status="rejected", score=0.1, correct=False),
    )
    invalid_score = outcome("nan", status="accepted", score=float("nan"), correct=True)

    with pytest.raises(ValueError, match="duplicate"):
        hypothesis_metrics(duplicate)
    with pytest.raises(ValueError, match="finite"):
        risk_coverage_curve((invalid_score,))
