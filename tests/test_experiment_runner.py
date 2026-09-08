import json
from pathlib import Path

import pytest

from experiments.runner import (
    NOT_EVALUABLE,
    ExperimentManifest,
    GroundTruth,
    HypothesisPrediction,
    RunObservation,
    evaluate_experiment,
    write_report,
)


def manifest(**overrides: object) -> ExperimentManifest:
    values: dict[str, object] = {
        "experiment_id": "experiment-controlled-1",
        "dataset_id": "controlled-fixture-a",
        "dataset_sha256": "a" * 64,
        "dataset_version": "1",
        "dataset_kind": "controlled",
        "redistribution_allowed": True,
        "git_commit": "abcdef1234567890",
        "started_at": "2026-09-08T10:00:00+08:00",
        "ended_at": "2026-09-08T10:01:00+08:00",
        "config": {"verification": True, "threshold": 0.9},
        "random_seed": 7,
        "provider": "mock",
        "model": "deterministic-v1",
        "dependency_versions": {"python": "3.11"},
        "artifact_refs": ("artifacts/messages.json",),
    }
    values.update(overrides)
    return ExperimentManifest(**values)  # type: ignore[arg-type]


def truth() -> GroundTruth:
    return GroundTruth(
        packet_boundaries=(0, 10, 20),
        field_boundaries={"f1": (0, 2), "f2": (2, 1)},
        field_semantics={"f1": "length", "f2": "enum"},
        notes={"source": "controlled fixture; not teacher benchmark"},
    )


def prediction(
    hypothesis_id: str,
    field_id: str,
    semantic_type: str,
    status: str,
    score: float,
) -> HypothesisPrediction:
    return HypothesisPrediction(
        hypothesis_id=hypothesis_id,
        field_id=field_id,
        semantic_type=semantic_type,
        status=status,  # type: ignore[arg-type]
        score=score,
    )


def run(**overrides: object) -> RunObservation:
    values: dict[str, object] = {
        "run_id": "full-1",
        "method": "evidencegraph_pre",
        "packet_boundaries": (0, 10, 21),
        "field_boundaries": {"f1": (0, 2), "f2": (2, 1)},
        "field_semantics": {"f1": "length", "f2": "sequence"},
        "hypotheses": (
            prediction("h1", "f1", "length", "accepted", 0.98),
            prediction("h2", "f2", "sequence", "accepted", 0.9),
            prediction("h3", "f2", "enum", "uncertain", 0.6),
        ),
        "parse_counts": (9, 10),
        "constraint_counts": (18, 20),
        "restoration_counts": (95, 100),
        "processing_time_seconds": 1.25,
        "llm_token_count": 120,
        "llm_cost": 0.01,
        "artifact_refs": ("runs/full/findings.json",),
    }
    values.update(overrides)
    return RunObservation(**values)  # type: ignore[arg-type]


def test_report_evaluates_required_metrics_without_truth_leakage() -> None:
    report = evaluate_experiment(manifest(), truth(), (run(),))
    metrics = report["runs"][0]["metrics"]

    assert metrics["packet_boundary_precision"] == pytest.approx(2 / 3)
    assert metrics["packet_boundary_recall"] == pytest.approx(2 / 3)
    assert metrics["packet_boundary_f1"] == pytest.approx(2 / 3)
    assert metrics["field_boundary_f1"] == 1.0
    assert metrics["field_semantic_accuracy"] == 0.5
    assert metrics["field_semantic_coverage"] == 1.0
    assert metrics["false_hypothesis_rate"] == pytest.approx(1 / 3)
    assert metrics["accepted_hypothesis_precision"] == 0.5
    assert metrics["accepted_hypothesis_coverage"] == pytest.approx(2 / 3)
    assert metrics["accepted_field_coverage"] == 0.5
    assert metrics["parse_coverage"] == 0.9
    assert metrics["constraint_satisfaction_rate"] == 0.9
    assert metrics["restoration_accuracy"] == 0.95
    assert metrics["processing_time_seconds"] == 1.25
    assert metrics["risk_coverage"][0]["risk"] == 0.0
    assert "packet_boundaries" not in report["ground_truth"]
    assert "field_semantics" not in report["ground_truth"]


def test_missing_ground_truth_is_explicit_instead_of_fabricated() -> None:
    report = evaluate_experiment(
        manifest(provider=None, model=None),
        GroundTruth(notes={"reason": "teacher supplied no labels"}),
        (run(hypotheses=(), parse_counts=None, llm_token_count=None, llm_cost=None),),
    )
    metrics = report["runs"][0]["metrics"]

    assert metrics["packet_boundary_f1"] == NOT_EVALUABLE
    assert metrics["field_boundary_f1"] == NOT_EVALUABLE
    assert metrics["field_semantic_accuracy"] == NOT_EVALUABLE
    assert metrics["false_hypothesis_rate"] == NOT_EVALUABLE
    assert metrics["parse_coverage"] == NOT_EVALUABLE
    assert report["ground_truth"]["notes"] == {
        "reason": "teacher supplied no labels"
    }


def test_required_comparison_and_ablation_gaps_are_reported() -> None:
    runs = (
        run(run_id="heuristic", method="heuristic"),
        run(run_id="full", method="evidencegraph_pre"),
        run(run_id="no-llm", method="without_llm"),
    )

    report = evaluate_experiment(manifest(), truth(), runs)

    assert report["coverage"]["comparisons"]["present"] == [
        "evidencegraph_pre",
        "heuristic",
    ]
    assert "llm_only" in report["coverage"]["comparisons"]["missing"]
    assert report["coverage"]["ablations"]["present"] == ["without_llm"]
    assert "without_provenance" in report["coverage"]["ablations"]["missing"]


def test_report_order_and_json_output_are_deterministic(tmp_path: Path) -> None:
    report = evaluate_experiment(
        manifest(),
        truth(),
        (
            run(run_id="z-run", method="heuristic"),
            run(run_id="a-run", method="llm_only"),
        ),
    )
    destination = tmp_path / "nested" / "report.json"

    written = write_report(report, destination)
    first = written.read_bytes()
    write_report(report, destination)

    assert written == destination
    assert written.read_bytes() == first
    assert first.endswith(b"\n")
    loaded = json.loads(first)
    assert [item["run_id"] for item in loaded["runs"]] == ["a-run", "z-run"]
    assert not (destination.parent / ".report.json.tmp").exists()


@pytest.mark.parametrize(
    "invalid_manifest",
    [
        manifest(dataset_sha256="abc"),
        manifest(git_commit="not-a-sha"),
        manifest(started_at="2026-09-08T10:00:00"),
        manifest(
            started_at="2026-09-08T10:01:00+08:00",
            ended_at="2026-09-08T10:00:00+08:00",
        ),
        manifest(provider="mock", model=None),
        manifest(config={"bad": float("nan")}),
        manifest(artifact_refs=("../secret.dat",)),
    ],
)
def test_invalid_reproducibility_manifest_fails_closed(
    invalid_manifest: ExperimentManifest,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        evaluate_experiment(invalid_manifest, truth(), (run(),))


def test_ground_truth_references_must_be_consistent() -> None:
    invalid = GroundTruth(
        field_boundaries={"known": (0, 1)},
        field_semantics={"unknown": "length"},
    )

    with pytest.raises(ValueError, match="unknown boundary ids"):
        evaluate_experiment(manifest(), invalid, (run(),))


@pytest.mark.parametrize(
    "invalid_run",
    [
        run(run_id=""),
        run(field_semantics={"missing": "length"}),
        run(parse_counts=(2, 1)),
        run(processing_time_seconds=float("inf")),
        run(llm_token_count=-1),
        run(artifact_refs=("C:\\private.dat",)),
        run(
            hypotheses=(
                prediction("same", "f1", "length", "accepted", 0.9),
                prediction("same", "f2", "enum", "accepted", 0.8),
            )
        ),
    ],
)
def test_invalid_run_observations_fail_closed(invalid_run: RunObservation) -> None:
    with pytest.raises((TypeError, ValueError)):
        evaluate_experiment(manifest(), truth(), (invalid_run,))


def test_duplicate_run_ids_fail_closed() -> None:
    with pytest.raises(ValueError, match="duplicate run_id"):
        evaluate_experiment(manifest(), truth(), (run(), run()))


def test_report_writer_rejects_non_finite_or_non_mapping_content(
    tmp_path: Path,
) -> None:
    with pytest.raises(TypeError, match="mapping"):
        write_report([], tmp_path / "report.json")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="finite JSON"):
        write_report({"bad": float("nan")}, tmp_path / "report.json")
