from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from course_project.experiments import (
    MetricRecord,
    build_synthetic_mechanism_corpus,
    run_synthetic_mechanism_experiments,
    scientific_record_fingerprint,
    write_experiment_bundle,
)

CODE_SHA = "1" * 40


def _metric(record, name: str) -> MetricRecord:
    return next(metric for metric in record.metrics if metric.name == name)


def test_synthetic_mechanism_corpus_identity_is_deterministic() -> None:
    first = build_synthetic_mechanism_corpus()
    second = build_synthetic_mechanism_corpus()

    assert first.capture == second.capture
    assert first.messages == second.messages
    assert first.dataset == second.dataset
    assert first.dataset.corpus_kind == "synthetic"
    assert first.dataset.redistribution_allowed is True
    assert first.dataset.ground_truth == frozenset()
    assert len(first.dataset.sha256) == 64


def test_harness_executes_honest_variants_and_metric_claims(tmp_path: Path) -> None:
    bundle = run_synthetic_mechanism_experiments(tmp_path / "run", code_sha=CODE_SHA)
    by_variant = {record.variant: record for record in bundle.records}

    assert set(by_variant) == {"heuristic", "naive_vote", "ablation_no_llm"}
    assert "evidencegraph_pre" not in by_variant

    for record in bundle.records:
        assert record.result_scope == "mechanism"
        assert record.formal_benchmark is False
        assert record.dataset.corpus_kind == "synthetic"
        assert record.dataset.ground_truth == frozenset()
        assert record.code_sha == CODE_SHA

        parse_coverage = _metric(record, "parse_coverage")
        constraint_rate = _metric(record, "constraint_satisfaction_rate")
        processing_time = _metric(record, "processing_time_seconds")
        boundary_f1 = _metric(record, "field_boundary_f1")

        assert parse_coverage.evaluable is True
        assert parse_coverage.value is not None
        assert 0.0 <= parse_coverage.value <= 1.0
        assert constraint_rate.evaluable is True
        assert constraint_rate.value is not None
        assert 0.0 <= constraint_rate.value <= 1.0
        assert processing_time.evaluable is True
        assert processing_time.value is not None
        assert processing_time.value >= 0.0
        assert boundary_f1.evaluable is False
        assert boundary_f1.value is None
        assert boundary_f1.reason == "not evaluable from declared ground truth"

    assert by_variant["ablation_no_llm"].config["llmEnabled"] is False
    assert by_variant["ablation_no_llm"].config["verificationEnabled"] is True


def test_scientific_fingerprint_excludes_only_wall_clock_timing(tmp_path: Path) -> None:
    bundle = run_synthetic_mechanism_experiments(tmp_path / "run", code_sha=CODE_SHA)
    record = bundle.records[0]
    changed_metrics = tuple(
        replace(metric, value=(metric.value or 0.0) + 123.0)
        if metric.name == "processing_time_seconds"
        else metric
        for metric in record.metrics
    )
    timing_changed = replace(record, metrics=changed_metrics)

    assert scientific_record_fingerprint(record) == scientific_record_fingerprint(timing_changed)

    parse_changed_metrics = tuple(
        replace(metric, value=0.0)
        if metric.name == "parse_coverage" and metric.value != 0.0
        else replace(metric, value=1.0)
        if metric.name == "parse_coverage"
        else metric
        for metric in record.metrics
    )
    parse_changed = replace(record, metrics=parse_changed_metrics)
    assert scientific_record_fingerprint(record) != scientific_record_fingerprint(parse_changed)


def test_rerun_has_stable_scientific_comparison(tmp_path: Path) -> None:
    first = run_synthetic_mechanism_experiments(tmp_path / "first", code_sha=CODE_SHA)
    second = run_synthetic_mechanism_experiments(tmp_path / "second", code_sha=CODE_SHA)

    assert first.comparison == second.comparison
    assert [scientific_record_fingerprint(record) for record in first.records] == [
        scientific_record_fingerprint(record) for record in second.records
    ]


def test_bundle_writer_emits_canonical_records_and_stable_manifest(tmp_path: Path) -> None:
    bundle = run_synthetic_mechanism_experiments(tmp_path / "run", code_sha=CODE_SHA)
    outdir = write_experiment_bundle(bundle, tmp_path / "out")

    assert {path.name for path in outdir.iterdir()} == {
        "heuristic.json",
        "naive_vote.json",
        "ablation_no_llm.json",
        "comparison.json",
        "manifest.json",
    }
    manifest = json.loads((outdir / "manifest.json").read_text(encoding="utf-8"))
    comparison = json.loads((outdir / "comparison.json").read_text(encoding="utf-8"))
    assert manifest["formalBenchmark"] is False
    assert manifest["variants"] == ["heuristic", "naive_vote", "ablation_no_llm"]
    assert comparison == bundle.comparison
