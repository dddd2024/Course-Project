import pytest

from course_project.experiments import (
    ABLATION_VARIANTS,
    BASELINE_VARIANTS,
    ArtifactReference,
    DatasetIdentity,
    DependencyVersion,
    ExperimentRecord,
    ExperimentValidationError,
    MetricRecord,
    canonical_record,
    compare_metric,
    metric_for_dataset,
    record_fingerprint,
)

DATA_SHA = "a" * 64
OTHER_DATA_SHA = "b" * 64
CODE_SHA = "c" * 40
ARTIFACT_SHA = "d" * 64


def dataset(
    *,
    kind: str = "teacher",
    digest: str = DATA_SHA,
    ground_truth: frozenset[str] = frozenset(),
) -> DatasetIdentity:
    return DatasetIdentity(
        dataset_id="course-eval-v1",
        corpus_kind=kind,  # type: ignore[arg-type]
        sha256=digest,
        version="v1",
        size_bytes=4096,
        ground_truth=ground_truth,  # type: ignore[arg-type]
        redistribution_allowed=False,
    )


def record(
    variant: str,
    data: DatasetIdentity,
    metric: MetricRecord,
    *,
    scope: str = "mechanism",
    config: dict[str, object] | None = None,
    dependencies: tuple[DependencyVersion, ...] = (),
    artifacts: tuple[ArtifactReference, ...] = (),
) -> ExperimentRecord:
    llm_kwargs: dict[str, str] = {}
    if variant in {
        "llm_only",
        "llm_verification",
        "evidencegraph_pre",
        "ablation_no_verification",
        "ablation_no_provenance",
        "ablation_no_alignment",
    }:
        llm_kwargs = {"model_provider": "mock", "model_version": "offline-v1"}
    return ExperimentRecord(
        variant=variant,  # type: ignore[arg-type]
        result_scope=scope,  # type: ignore[arg-type]
        dataset=data,
        code_sha=CODE_SHA,
        config=config or {"threshold": 0.75},
        random_seed=7,
        metrics=(metric,),
        dependencies=dependencies,
        artifacts=artifacts,
        **llm_kwargs,
    )


def test_canonical_v2_baseline_and_ablation_vocabulary_is_fixed() -> None:
    assert BASELINE_VARIANTS == (
        "heuristic",
        "netzob_pre",
        "llm_only",
        "llm_verification",
        "naive_vote",
        "evidencegraph_pre",
    )
    assert ABLATION_VARIANTS == (
        "ablation_no_verification",
        "ablation_no_provenance",
        "ablation_no_llm",
        "ablation_no_alignment",
    )


def test_teacher_formal_benchmark_with_declared_ground_truth_is_valid() -> None:
    data = dataset(ground_truth=frozenset({"field_semantics"}))
    metric = metric_for_dataset(data, "field_semantic_accuracy", 0.875)

    run = record("heuristic", data, metric, scope="formal_benchmark")

    assert run.result_scope == "formal_benchmark"
    assert run.dataset.corpus_kind == "teacher"
    assert run.metrics[0].evaluable is True
    assert run.metrics[0].value == 0.875


def test_synthetic_result_cannot_masquerade_as_formal_teacher_benchmark() -> None:
    data = dataset(kind="synthetic")
    metric = metric_for_dataset(data, "parse_coverage", 1.0)

    with pytest.raises(ExperimentValidationError, match="formal benchmark"):
        record("heuristic", data, metric, scope="formal_benchmark")


def test_metric_without_required_ground_truth_is_explicitly_not_evaluable() -> None:
    data = dataset(kind="synthetic")

    metric = metric_for_dataset(data, "field_boundary_f1", None)

    assert metric.evaluable is False
    assert metric.value is None
    assert metric.unavailable_reason is not None
    assert "field_boundaries" in metric.unavailable_reason


def test_missing_ground_truth_rejects_fabricated_metric_value() -> None:
    data = dataset(kind="synthetic")

    with pytest.raises(ExperimentValidationError, match="not evaluable"):
        metric_for_dataset(data, "field_boundary_f1", 0.99)

    fabricated = MetricRecord(
        name="field_semantic_accuracy",
        evaluable=True,
        value=0.99,
    )
    with pytest.raises(ExperimentValidationError, match="lacks ground truth"):
        record("heuristic", data, fabricated)


def test_mechanism_metrics_do_not_require_external_ground_truth() -> None:
    data = dataset(kind="synthetic")

    parse_coverage = metric_for_dataset(data, "parse_coverage", 0.8)
    constraint_rate = metric_for_dataset(data, "constraint_satisfaction_rate", 0.75)

    assert parse_coverage.evaluable is True
    assert constraint_rate.evaluable is True


def test_llm_variants_require_explicit_provider_and_version() -> None:
    data = dataset(kind="synthetic")
    metric = metric_for_dataset(data, "parse_coverage", 1.0)

    with pytest.raises(TypeError, match="model_provider"):
        ExperimentRecord(
            variant="llm_only",
            result_scope="mechanism",
            dataset=data,
            code_sha=CODE_SHA,
            config={},
            metrics=(metric,),
        )


def test_invalid_dataset_hash_code_sha_and_non_json_config_fail_closed() -> None:
    with pytest.raises(ExperimentValidationError, match="dataset sha256"):
        dataset(digest="not-a-hash")

    data = dataset(kind="synthetic")
    metric = metric_for_dataset(data, "parse_coverage", 1.0)
    with pytest.raises(ExperimentValidationError, match="code_sha"):
        ExperimentRecord(
            variant="heuristic",
            result_scope="mechanism",
            dataset=data,
            code_sha="bad",
            config={},
            metrics=(metric,),
        )
    with pytest.raises(TypeError, match="JSON-compatible"):
        ExperimentRecord(
            variant="heuristic",
            result_scope="mechanism",
            dataset=data,
            code_sha=CODE_SHA,
            config={"bad": object()},
            metrics=(metric,),
        )


def test_record_captures_auditable_dependencies_artifacts_and_model_metadata() -> None:
    data = dataset(kind="synthetic")
    metric = metric_for_dataset(data, "processing_time_seconds", 0.42)
    run = record(
        "evidencegraph_pre",
        data,
        metric,
        dependencies=(
            DependencyVersion("netzob", "2.0.0"),
            DependencyVersion("python", "3.11.9"),
        ),
        artifacts=(ArtifactReference("result-json", "artifacts/result.json", ARTIFACT_SHA),),
    )

    payload = canonical_record(run)

    assert payload["codeSha"] == CODE_SHA
    assert payload["randomSeed"] == 7
    assert payload["model"] == {"provider": "mock", "version": "offline-v1"}
    assert payload["dependencies"] == [
        {"name": "netzob", "version": "2.0.0"},
        {"name": "python", "version": "3.11.9"},
    ]
    assert payload["artifacts"] == [
        {
            "artifactId": "result-json",
            "path": "artifacts/result.json",
            "sha256": ARTIFACT_SHA,
        }
    ]


def test_fingerprint_is_deterministic_across_mapping_and_metadata_order() -> None:
    data = dataset(kind="synthetic")
    metric = metric_for_dataset(data, "parse_coverage", 1.0)
    first = record(
        "naive_vote",
        data,
        metric,
        config={"b": 2, "a": 1},
        dependencies=(
            DependencyVersion("python", "3.11"),
            DependencyVersion("netzob", "2.0.0"),
        ),
        artifacts=(
            ArtifactReference("z", "z.json"),
            ArtifactReference("a", "a.json"),
        ),
    )
    second = record(
        "naive_vote",
        data,
        metric,
        config={"a": 1, "b": 2},
        dependencies=(
            DependencyVersion("netzob", "2.0.0"),
            DependencyVersion("python", "3.11"),
        ),
        artifacts=(
            ArtifactReference("a", "a.json"),
            ArtifactReference("z", "z.json"),
        ),
    )

    assert record_fingerprint(first) == record_fingerprint(second)


def test_same_dataset_cross_variant_comparison_is_deterministic() -> None:
    data = dataset(kind="synthetic")
    heuristic = record(
        "heuristic",
        data,
        metric_for_dataset(data, "parse_coverage", 0.5),
    )
    naive = record(
        "naive_vote",
        data,
        metric_for_dataset(data, "parse_coverage", 0.75),
    )
    full = record(
        "evidencegraph_pre",
        data,
        metric_for_dataset(data, "parse_coverage", 1.0),
    )

    rows = compare_metric((full, naive, heuristic), "parse_coverage")

    assert [(row.variant, row.value) for row in rows] == [
        ("heuristic", 0.5),
        ("naive_vote", 0.75),
        ("evidencegraph_pre", 1.0),
    ]
    assert all(len(row.record_fingerprint) == 64 for row in rows)


def test_mixed_dataset_and_not_evaluable_comparisons_fail_closed() -> None:
    first_data = dataset(kind="synthetic")
    second_data = dataset(kind="synthetic", digest=OTHER_DATA_SHA)
    first = record(
        "heuristic",
        first_data,
        metric_for_dataset(first_data, "parse_coverage", 0.5),
    )
    second = record(
        "naive_vote",
        second_data,
        metric_for_dataset(second_data, "parse_coverage", 0.75),
    )

    with pytest.raises(ExperimentValidationError, match="identical dataset"):
        compare_metric((first, second), "parse_coverage")

    unavailable_metric = metric_for_dataset(first_data, "field_semantic_accuracy", None)
    unavailable = record("naive_vote", first_data, unavailable_metric)
    missing_metric = record(
        "heuristic",
        first_data,
        metric_for_dataset(first_data, "field_semantic_accuracy", None),
    )
    with pytest.raises(ExperimentValidationError, match="not evaluable"):
        compare_metric((missing_metric, unavailable), "field_semantic_accuracy")


def test_duplicate_metrics_dependencies_artifacts_and_variants_fail_closed() -> None:
    data = dataset(kind="synthetic")
    metric = metric_for_dataset(data, "parse_coverage", 1.0)

    with pytest.raises(ExperimentValidationError, match="duplicate metric"):
        ExperimentRecord(
            variant="heuristic",
            result_scope="mechanism",
            dataset=data,
            code_sha=CODE_SHA,
            config={},
            metrics=(metric, metric),
        )
    with pytest.raises(ExperimentValidationError, match="duplicate dependency"):
        record(
            "heuristic",
            data,
            metric,
            dependencies=(
                DependencyVersion("python", "3.10"),
                DependencyVersion("python", "3.11"),
            ),
        )
    with pytest.raises(ExperimentValidationError, match="duplicate artifact"):
        record(
            "heuristic",
            data,
            metric,
            artifacts=(
                ArtifactReference("result", "a.json"),
                ArtifactReference("result", "b.json"),
            ),
        )

    first = record("heuristic", data, metric)
    second = record("heuristic", data, metric, config={"different": True})
    with pytest.raises(ExperimentValidationError, match="duplicate experiment variant"):
        compare_metric((first, second), "parse_coverage")
