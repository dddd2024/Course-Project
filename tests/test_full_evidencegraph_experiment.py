from __future__ import annotations

import json
from pathlib import Path

from course_project.experiments import (
    MetricRecord,
    run_full_evidencegraph_mechanism_experiment,
    run_synthetic_mechanism_experiments,
    scientific_record_fingerprint,
    write_full_evidencegraph_mechanism_execution,
)

CODE_SHA = "2" * 40


def _metric(record, name: str) -> MetricRecord:
    return next(metric for metric in record.metrics if metric.name == name)


def test_full_method_mechanism_executes_real_production_path(tmp_path: Path) -> None:
    execution = run_full_evidencegraph_mechanism_experiment(
        tmp_path / "run",
        code_sha=CODE_SHA,
    )
    record = execution.record
    audit = execution.audit

    assert record.variant == "evidencegraph_pre"
    assert record.result_scope == "mechanism"
    assert record.model_provider == "deterministic-evidencegraph-mechanism"
    assert record.model_version == "1"
    assert record.config["formalBenchmark"] is False
    assert record.config["realLLMBenchmark"] is False
    assert record.config["providerNetworkAccess"] is False
    assert record.config["llmEnabled"] is True
    assert record.config["verificationEnabled"] is True
    assert record.config["provenanceAwareFusionEnabled"] is True
    assert record.config["globalSelectionEnabled"] is True

    assert audit["providerRequestCount"] > 0
    assert audit["providerHypothesisCount"] >= 2
    assert audit["acceptedProviderHypothesisCount"] >= 1
    assert audit["rejectedWrongHypothesisCount"] >= 1
    assert audit["wrongHypothesisMaxConfidence"] == 0.97
    assert audit["correctHypothesisMaxConfidence"] == 0.61
    assert audit["wrongHypothesisMaxConfidence"] > audit["correctHypothesisMaxConfidence"]
    assert audit["verifiedFieldCount"] > 0
    assert audit["schemaExecutable"] is True

    assert _metric(record, "parse_coverage").value == 1.0
    assert _metric(record, "constraint_satisfaction_rate").value == 1.0
    assert _metric(record, "token_cost_usd").value == 0.0

    semantic_accuracy = _metric(record, "field_semantic_accuracy")
    assert semantic_accuracy.evaluable is False
    assert semantic_accuracy.value is None
    assert semantic_accuracy.unavailable_reason == (
        "not evaluable from declared ground truth; missing: field_semantics"
    )


def test_full_method_scientific_fingerprint_is_reproducible(tmp_path: Path) -> None:
    first = run_full_evidencegraph_mechanism_experiment(
        tmp_path / "first",
        code_sha=CODE_SHA,
    )
    second = run_full_evidencegraph_mechanism_experiment(
        tmp_path / "second",
        code_sha=CODE_SHA,
    )

    assert first.audit == second.audit
    assert scientific_record_fingerprint(first.record) == scientific_record_fingerprint(
        second.record
    )


def test_writer_emits_separate_full_method_mechanism_artifacts(tmp_path: Path) -> None:
    execution = run_full_evidencegraph_mechanism_experiment(
        tmp_path / "run",
        code_sha=CODE_SHA,
    )
    outdir = write_full_evidencegraph_mechanism_execution(execution, tmp_path / "records")

    assert {path.name for path in outdir.iterdir()} == {
        "evidencegraph_pre.json",
        "evidencegraph_pre.audit.json",
        "full-method-manifest.json",
    }
    record = json.loads((outdir / "evidencegraph_pre.json").read_text(encoding="utf-8"))
    manifest = json.loads(
        (outdir / "full-method-manifest.json").read_text(encoding="utf-8")
    )
    assert record["variant"] == "evidencegraph_pre"
    assert record["resultScope"] == "mechanism"
    assert record["model"] == {
        "provider": "deterministic-evidencegraph-mechanism",
        "version": "1",
    }
    assert manifest["formalBenchmark"] is False
    assert manifest["realLLMBenchmark"] is False
    assert manifest["variant"] == "evidencegraph_pre"
    assert len(manifest["scientificFingerprint"]) == 64


def test_existing_three_variant_harness_remains_backward_compatible(tmp_path: Path) -> None:
    bundle = run_synthetic_mechanism_experiments(tmp_path / "legacy", code_sha=CODE_SHA)
    assert [record.variant for record in bundle.records] == [
        "heuristic",
        "naive_vote",
        "ablation_no_llm",
    ]
    assert "evidencegraph_pre" not in {record.variant for record in bundle.records}
