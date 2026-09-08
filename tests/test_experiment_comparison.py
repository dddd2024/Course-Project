import pytest

from experiments.comparison import (
    CANONICAL_VARIANTS,
    ComparisonExecutionError,
    ExperimentVariant,
    build_comparison_report,
    execute_variants,
)
from experiments.runner import ExperimentManifest, GroundTruth, RunObservation


class RecordingExecutor:
    def __init__(self, *, fail: set[str] | None = None) -> None:
        self.seen: list[ExperimentVariant] = []
        self.fail = fail or set()

    def execute(self, variant: ExperimentVariant) -> RunObservation:
        self.seen.append(variant)
        if variant.name in self.fail:
            raise RuntimeError(f"{variant.name} unavailable")
        return RunObservation(
            run_id=f"run-{variant.name}",
            method=variant.name,
            processing_time_seconds=0.1,
        )


class WrongMethodExecutor:
    def execute(self, variant: ExperimentVariant) -> RunObservation:
        return RunObservation(run_id="wrong", method="different")


def manifest() -> ExperimentManifest:
    return ExperimentManifest(
        experiment_id="comparison-1",
        dataset_id="teacher-data-metadata-only",
        dataset_sha256="b" * 64,
        dataset_version="received-2026-09-08",
        dataset_kind="teacher",
        redistribution_allowed=False,
        git_commit="abcdef1234567890",
        started_at="2026-09-08T10:00:00Z",
        ended_at="2026-09-08T10:10:00Z",
        dependency_versions={"python": "3.11"},
    )


def test_canonical_matrix_contains_all_required_comparisons_and_ablations() -> None:
    by_name = {variant.name: variant for variant in CANONICAL_VARIANTS}

    assert set(by_name) == {
        "heuristic",
        "netzob_binaryinferno",
        "llm_only",
        "llm_verification",
        "naive_vote",
        "evidencegraph_pre",
        "without_verification",
        "without_provenance",
        "without_llm",
        "without_alignment",
    }
    assert by_name["llm_only"].llm_enabled is True
    assert by_name["llm_only"].verification_enabled is False
    assert by_name["without_llm"].llm_enabled is False
    assert by_name["without_provenance"].fusion_mode == "naive"
    assert by_name["evidencegraph_pre"].fusion_mode == "provenance"


def test_executor_receives_only_variant_configuration_before_evaluation() -> None:
    executor = RecordingExecutor()

    report = build_comparison_report(
        manifest(), GroundTruth(notes={"labels": "unavailable"}), executor
    )

    assert tuple(executor.seen) == CANONICAL_VARIANTS
    assert report["coverage"]["comparisons"]["missing"] == []
    assert report["coverage"]["ablations"]["missing"] == []
    assert report["execution_failures"] == []
    assert len(report["runs"]) == 10


def test_variant_failure_is_recorded_and_remaining_runs_continue() -> None:
    executor = RecordingExecutor(fail={"llm_only"})

    report = build_comparison_report(manifest(), GroundTruth(), executor)

    assert report["execution_failures"] == [
        {
            "variant": "llm_only",
            "error_type": "RuntimeError",
            "message": "llm_only unavailable",
        }
    ]
    assert "llm_only" in report["coverage"]["comparisons"]["missing"]
    assert len(report["runs"]) == 9


def test_fail_fast_policy_preserves_original_error() -> None:
    executor = RecordingExecutor(fail={"heuristic"})

    with pytest.raises(ComparisonExecutionError) as error:
        execute_variants(executor, failure_policy="fail")

    assert isinstance(error.value.__cause__, RuntimeError)


def test_invalid_executor_result_is_recorded_as_failure() -> None:
    result = execute_variants(
        WrongMethodExecutor(), variants=(CANONICAL_VARIANTS[0],)
    )

    assert result.runs == ()
    assert result.failures[0].error_type == "ValueError"
    assert "does not match" in result.failures[0].message


def test_all_failed_variants_cannot_create_a_false_empty_report() -> None:
    variant = CANONICAL_VARIANTS[0]
    executor = RecordingExecutor(fail={variant.name})

    with pytest.raises(ComparisonExecutionError, match="all experiment variants failed"):
        build_comparison_report(
            manifest(), GroundTruth(), executor, variants=(variant,)
        )


def test_duplicate_or_invalid_variants_fail_before_execution() -> None:
    executor = RecordingExecutor()
    duplicate = (CANONICAL_VARIANTS[0], CANONICAL_VARIANTS[0])
    invalid = ExperimentVariant(
        name="invalid",
        structure_source="heuristic",
        llm_enabled=True,
        verification_enabled=True,
        alignment_enabled=True,
        fusion_mode="invented",  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="duplicate"):
        execute_variants(executor, duplicate)
    with pytest.raises(ValueError, match="fusion_mode"):
        execute_variants(executor, (invalid,))
    assert executor.seen == []


def test_duplicate_run_ids_are_explicit_execution_failures() -> None:
    class DuplicateRunExecutor:
        def execute(self, variant: ExperimentVariant) -> RunObservation:
            return RunObservation(run_id="same", method=variant.name)

    result = execute_variants(
        DuplicateRunExecutor(), variants=CANONICAL_VARIANTS[:2]
    )

    assert len(result.runs) == 1
    assert len(result.failures) == 1
    assert "duplicate run_id" in result.failures[0].message
