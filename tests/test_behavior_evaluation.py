from __future__ import annotations

import pytest

from course_project.behavior import BehaviorEvaluation, evaluate_behavior_predictions
from course_project.models import BehaviorPrediction


def _prediction(flow_id: str, label: str) -> BehaviorPrediction:
    return BehaviorPrediction(
        flow_id=flow_id,
        label=label,  # type: ignore[arg-type]
        confidence=0.9,
        features={"packet_count": 4},
    )


def test_unlabeled_behavior_evaluation_never_fabricates_accuracy_or_f1() -> None:
    result = evaluate_behavior_predictions(
        [_prediction("flow-a", "QUERY"), _prediction("flow-b", "DOWNLOAD")]
    )

    assert isinstance(result, BehaviorEvaluation)
    assert result.metrics_evaluable is False
    assert result.sample_count == 2
    assert result.labeled_sample_count == 0
    assert result.accuracy is None
    assert result.macro_f1 is None
    assert result.split_unit is None
    assert "must not be reported" in (result.unavailable_reason or "")


def test_labeled_behavior_evaluation_computes_deterministic_metrics() -> None:
    result = evaluate_behavior_predictions(
        [
            _prediction("flow-a", "QUERY"),
            _prediction("flow-b", "UPLOAD"),
            _prediction("flow-c", "DOWNLOAD"),
        ],
        labels={
            "flow-a": "QUERY",
            "flow-b": "DOWNLOAD",
            "flow-c": "DOWNLOAD",
        },
        split_unit="flow",
    )

    assert result.metrics_evaluable is True
    assert result.sample_count == 3
    assert result.labeled_sample_count == 3
    assert result.accuracy == 0.666666666667
    assert result.macro_f1 == 0.555555555556
    assert result.split_unit == "flow"
    assert result.observed_labels == ("DOWNLOAD", "QUERY", "UPLOAD")
    assert result.unavailable_reason is None


def test_supervised_behavior_evaluation_requires_exact_flow_identity() -> None:
    with pytest.raises(ValueError, match="match predicted flow IDs exactly"):
        evaluate_behavior_predictions(
            [_prediction("flow-a", "QUERY"), _prediction("flow-b", "DOWNLOAD")],
            labels={"flow-a": "QUERY", "flow-extra": "DOWNLOAD"},
            split_unit="flow",
        )


def test_behavior_evaluation_rejects_duplicate_prediction_ids() -> None:
    with pytest.raises(ValueError, match="duplicate prediction flow_id"):
        evaluate_behavior_predictions(
            [_prediction("flow-a", "QUERY"), _prediction("flow-a", "DOWNLOAD")]
        )


def test_behavior_evaluation_rejects_invalid_labels() -> None:
    with pytest.raises(ValueError, match="frozen behavior vocabulary"):
        evaluate_behavior_predictions([_prediction("flow-a", "NOT_A_LABEL")])


def test_behavior_evaluation_rejects_noncanonical_label_case() -> None:
    with pytest.raises(ValueError, match="frozen behavior vocabulary"):
        evaluate_behavior_predictions(
            [_prediction("flow-a", "QUERY")],
            labels={"flow-a": "query"},
            split_unit="flow",
        )


def test_behavior_evaluation_rejects_packet_level_supervised_split() -> None:
    with pytest.raises(ValueError, match="rejects packet-level"):
        evaluate_behavior_predictions(
            [_prediction("flow-a", "QUERY")],
            labels={"flow-a": "QUERY"},
            split_unit="packet",
        )


def test_behavior_evaluation_requires_split_for_supervised_metrics() -> None:
    with pytest.raises(ValueError, match="requires split_unit"):
        evaluate_behavior_predictions(
            [_prediction("flow-a", "QUERY")],
            labels={"flow-a": "QUERY"},
        )


def test_unlabeled_behavior_evaluation_rejects_fake_split_metadata() -> None:
    with pytest.raises(ValueError, match="only valid when labels are supplied"):
        evaluate_behavior_predictions(
            [_prediction("flow-a", "QUERY")],
            split_unit="flow",
        )
