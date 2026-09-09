from __future__ import annotations

import json
from pathlib import Path

from course_project.experiments.threshold_sensitivity import (
    CONFLICT_THRESHOLDS,
    DEFAULT_CONFLICT_THRESHOLD,
    DEFAULT_SUPPORT_THRESHOLD,
    SUPPORT_THRESHOLDS,
    run_threshold_sensitivity_analysis,
    threshold_sensitivity_fingerprint,
    write_threshold_sensitivity_execution,
)

CODE_SHA = "7" * 40


def test_threshold_sensitivity_replays_exact_fixed_grid(tmp_path: Path) -> None:
    execution = run_threshold_sensitivity_analysis(tmp_path / "run", code_sha=CODE_SHA)

    assert execution.default_point_matches_production is True
    assert execution.rejected_wrong_hypothesis_count >= 1
    assert len(execution.points) == 9
    assert {
        (point.acceptance_support_threshold, point.max_conflict_for_accept)
        for point in execution.points
    } == {
        (support, conflict)
        for support in SUPPORT_THRESHOLDS
        for conflict in CONFLICT_THRESHOLDS
    }
    default = next(
        point
        for point in execution.points
        if point.acceptance_support_threshold == DEFAULT_SUPPORT_THRESHOLD
        and point.max_conflict_for_accept == DEFAULT_CONFLICT_THRESHOLD
    )
    assert default.decision_changed_from_default_count == 0
    assert default.selected_ranges_changed_from_default is False
    assert default.selected_field_ranges == execution.production_selected_field_ranges
    assert default.parse_coverage == execution.production_parse_coverage
    assert (
        default.constraint_satisfaction_rate
        == execution.production_constraint_satisfaction_rate
    )
    assert all(point.verifier_rejected_hypothesis_count >= 1 for point in execution.points)
    assert all(point.verifier_rejected_selected_count == 0 for point in execution.points)
    assert execution.summary["pointCount"] == 9
    assert execution.summary["stablePointCount"] + execution.summary["changedPointCount"] == 9


def test_threshold_sensitivity_is_scientifically_reproducible(tmp_path: Path) -> None:
    first = run_threshold_sensitivity_analysis(tmp_path / "first", code_sha=CODE_SHA)
    second = run_threshold_sensitivity_analysis(tmp_path / "second", code_sha=CODE_SHA)

    assert first.points == second.points
    assert first.summary == second.summary
    assert threshold_sensitivity_fingerprint(first) == threshold_sensitivity_fingerprint(second)


def test_threshold_sensitivity_writer_is_mechanism_only_and_not_optimization(
    tmp_path: Path,
) -> None:
    execution = run_threshold_sensitivity_analysis(tmp_path / "run", code_sha=CODE_SHA)
    outdir = write_threshold_sensitivity_execution(execution, tmp_path / "records")

    assert {path.name for path in outdir.iterdir()} == {
        "threshold_sensitivity.json",
        "threshold-sensitivity-manifest.json",
    }
    payload = json.loads((outdir / "threshold_sensitivity.json").read_text(encoding="utf-8"))
    manifest = json.loads(
        (outdir / "threshold-sensitivity-manifest.json").read_text(encoding="utf-8")
    )

    assert payload["analysis"] == "fusion_threshold_sensitivity"
    assert payload["resultScope"] == "mechanism"
    assert payload["formalBenchmark"] is False
    assert payload["realLLMBenchmark"] is False
    assert payload["optimizationPerformed"] is False
    assert payload["bestThresholdSelected"] is False
    assert payload["groundTruthDependentMetricsEvaluated"] is False
    assert payload["defaultPointMatchesProduction"] is True
    assert payload["grid"]["pointCount"] == 9
    assert payload["materialization"]["fullMethodExecutedOnce"] is True
    assert payload["materialization"]["verificationReusedAcrossGrid"] is True
    assert payload["materialization"]["evidenceReusedAcrossGrid"] is True
    assert manifest["formalBenchmark"] is False
    assert manifest["realLLMBenchmark"] is False
    assert manifest["optimizationPerformed"] is False
    assert manifest["gridPointCount"] == 9
    assert len(manifest["scientificFingerprint"]) == 64
