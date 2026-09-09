from __future__ import annotations

import json
from pathlib import Path

from course_project.experiments import (
    MetricRecord,
    run_llm_only_mechanism_baseline,
    scientific_record_fingerprint,
    write_llm_only_mechanism_execution,
)

CODE_SHA = "5" * 40


def _metric(record, name: str) -> MetricRecord:
    return next(metric for metric in record.metrics if metric.name == name)


def test_llm_only_mechanism_exposes_confidence_only_failure_mode(tmp_path: Path) -> None:
    execution = run_llm_only_mechanism_baseline(tmp_path / "run", code_sha=CODE_SHA)
    record = execution.record
    audit = execution.audit

    assert record.variant == "llm_only"
    assert record.result_scope == "mechanism"
    assert record.model_provider == "deterministic-evidencegraph-mechanism"
    assert record.model_version == "1"
    assert record.config["formalBenchmark"] is False
    assert record.config["realLLMBenchmark"] is False
    assert record.config["llmOnly"] is True
    assert record.config["verificationEnabled"] is False
    assert record.config["verificationEvidenceUsed"] is False
    assert record.config["provenanceAwareFusionEnabled"] is False
    assert record.config["provenanceEvidenceUsedForSelection"] is False
    assert record.config["globalSelectionEnabled"] is True
    assert record.config["selectionPolicy"] == "model-confidence-per-region-v1"

    assert audit["pairedControlVerificationExecuted"] is True
    assert audit["pairedControlRejectedWrongHypothesisCount"] >= 1
    assert audit["wrongHypothesisMaxConfidence"] == 0.97
    assert audit["correctHypothesisMaxConfidence"] == 0.61
    assert audit["wrongHypothesisMaxConfidence"] > audit["correctHypothesisMaxConfidence"]
    assert audit["wrongConfidenceRegionWinnerCount"] >= 1
    assert audit["selectedWrongHypothesisCount"] >= 1

    parse_coverage = _metric(record, "parse_coverage")
    assert parse_coverage.evaluable is True
    assert parse_coverage.value is not None
    assert 0.0 <= parse_coverage.value <= 1.0

    constraint_rate = _metric(record, "constraint_satisfaction_rate")
    assert constraint_rate.evaluable is False
    assert constraint_rate.value is None
    assert constraint_rate.unavailable_reason == (
        "not applicable: LLM-only baseline performs no executable verification"
    )

    semantic_accuracy = _metric(record, "field_semantic_accuracy")
    assert semantic_accuracy.evaluable is False
    assert semantic_accuracy.value is None
    assert semantic_accuracy.unavailable_reason == (
        "not evaluable from declared ground truth; missing: field_semantics"
    )
    assert _metric(record, "token_cost_usd").value == 0.0


def test_llm_only_mechanism_is_scientifically_reproducible(tmp_path: Path) -> None:
    first = run_llm_only_mechanism_baseline(tmp_path / "first", code_sha=CODE_SHA)
    second = run_llm_only_mechanism_baseline(tmp_path / "second", code_sha=CODE_SHA)

    assert first.audit == second.audit
    assert scientific_record_fingerprint(first.record) == scientific_record_fingerprint(
        second.record
    )


def test_llm_only_writer_emits_separate_canonical_artifacts(tmp_path: Path) -> None:
    execution = run_llm_only_mechanism_baseline(tmp_path / "run", code_sha=CODE_SHA)
    outdir = write_llm_only_mechanism_execution(execution, tmp_path / "records")

    assert {path.name for path in outdir.iterdir()} == {
        "llm_only.json",
        "llm_only.audit.json",
        "llm-only-manifest.json",
    }
    record = json.loads((outdir / "llm_only.json").read_text(encoding="utf-8"))
    manifest = json.loads((outdir / "llm-only-manifest.json").read_text(encoding="utf-8"))
    audit = json.loads((outdir / "llm_only.audit.json").read_text(encoding="utf-8"))

    assert record["variant"] == "llm_only"
    assert record["resultScope"] == "mechanism"
    assert record["config"]["verificationEnabled"] is False
    assert record["config"]["provenanceAwareFusionEnabled"] is False
    assert record["model"] == {
        "provider": "deterministic-evidencegraph-mechanism",
        "version": "1",
    }
    assert manifest["formalBenchmark"] is False
    assert manifest["realLLMBenchmark"] is False
    assert manifest["variant"] == "llm_only"
    assert len(manifest["scientificFingerprint"]) == 64
    assert audit["selectedWrongHypothesisCount"] >= 1
