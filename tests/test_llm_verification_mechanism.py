from __future__ import annotations

import json
from pathlib import Path

from course_project.experiments import (
    MetricRecord,
    run_llm_verification_mechanism_baseline,
    scientific_record_fingerprint,
    write_llm_verification_mechanism_execution,
)

CODE_SHA = "6" * 40


def _metric(record, name: str) -> MetricRecord:
    return next(metric for metric in record.metrics if metric.name == name)


def test_llm_verification_rejects_high_confidence_wrong_hypothesis(tmp_path: Path) -> None:
    execution = run_llm_verification_mechanism_baseline(
        tmp_path / "run",
        code_sha=CODE_SHA,
    )
    record = execution.record
    audit = execution.audit

    assert record.variant == "llm_verification"
    assert record.result_scope == "mechanism"
    assert record.model_provider == "deterministic-evidencegraph-mechanism"
    assert record.model_version == "1"
    assert record.config["formalBenchmark"] is False
    assert record.config["realLLMBenchmark"] is False
    assert record.config["llmVerificationBaseline"] is True
    assert record.config["verificationEnabled"] is True
    assert record.config["verificationEvidenceUsed"] is True
    assert record.config["provenanceAwareFusionEnabled"] is False
    assert record.config["provenanceEvidenceUsedForSelection"] is False
    assert record.config["globalSelectionEnabled"] is True
    assert record.config["globalSelectionMayAbstainWithoutFusion"] is True
    assert record.config["selectionPolicy"] == "verification-gate-model-confidence-v1"

    assert audit["pairedControlVerificationExecuted"] is True
    assert audit["pairedControlFusionExecuted"] is True
    assert audit["baselineVerificationExecuted"] is True
    assert audit["baselineFusionExecuted"] is False
    assert audit["verificationMatchedProviderHypothesisCount"] == audit[
        "providerHypothesisCount"
    ]
    assert audit["rejectedWrongHypothesisCount"] >= 1
    assert audit["acceptedCorrectHypothesisCount"] >= 1
    assert audit["selectedWrongHypothesisCount"] == 0
    # The deterministic fixture exposes a second-stage limitation: after the verifier
    # removes the wrong high-confidence endian proposal, accepted overlapping provider
    # hypotheses can remain scientifically tied without provenance-fusion signals.
    # Global selection must preserve that abstention instead of force-picking a field.
    assert audit["globalAbstainedHypothesisCount"] >= 1
    assert audit["wrongHypothesisMaxConfidence"] == 0.97
    assert audit["correctHypothesisMaxConfidence"] == 0.61
    assert audit["wrongHypothesisMaxConfidence"] > audit["correctHypothesisMaxConfidence"]

    parse_coverage = _metric(record, "parse_coverage")
    assert parse_coverage.evaluable is True
    assert parse_coverage.value is not None
    assert 0.0 <= parse_coverage.value <= 1.0
    assert parse_coverage.value == audit["parseCoverage"]

    constraint_rate = _metric(record, "constraint_satisfaction_rate")
    assert constraint_rate.evaluable is True
    assert constraint_rate.value is not None
    assert 0.0 <= constraint_rate.value <= 1.0
    assert constraint_rate.value == audit["constraintSatisfactionRate"]

    semantic_accuracy = _metric(record, "field_semantic_accuracy")
    assert semantic_accuracy.evaluable is False
    assert semantic_accuracy.value is None
    assert semantic_accuracy.unavailable_reason == (
        "not evaluable from declared ground truth; missing: field_semantics"
    )
    assert _metric(record, "token_cost_usd").value == 0.0


def test_llm_verification_mechanism_is_scientifically_reproducible(
    tmp_path: Path,
) -> None:
    first = run_llm_verification_mechanism_baseline(
        tmp_path / "first",
        code_sha=CODE_SHA,
    )
    second = run_llm_verification_mechanism_baseline(
        tmp_path / "second",
        code_sha=CODE_SHA,
    )

    assert first.audit == second.audit
    assert scientific_record_fingerprint(first.record) == scientific_record_fingerprint(
        second.record
    )


def test_llm_verification_writer_emits_separate_canonical_artifacts(
    tmp_path: Path,
) -> None:
    execution = run_llm_verification_mechanism_baseline(
        tmp_path / "run",
        code_sha=CODE_SHA,
    )
    outdir = write_llm_verification_mechanism_execution(
        execution,
        tmp_path / "records",
    )

    assert {path.name for path in outdir.iterdir()} == {
        "llm_verification.json",
        "llm_verification.audit.json",
        "llm-verification-manifest.json",
    }
    record = json.loads((outdir / "llm_verification.json").read_text(encoding="utf-8"))
    manifest = json.loads(
        (outdir / "llm-verification-manifest.json").read_text(encoding="utf-8")
    )
    audit = json.loads(
        (outdir / "llm_verification.audit.json").read_text(encoding="utf-8")
    )

    assert record["variant"] == "llm_verification"
    assert record["resultScope"] == "mechanism"
    assert record["config"]["verificationEnabled"] is True
    assert record["config"]["verificationEvidenceUsed"] is True
    assert record["config"]["provenanceAwareFusionEnabled"] is False
    assert record["config"]["globalSelectionMayAbstainWithoutFusion"] is True
    assert record["model"] == {
        "provider": "deterministic-evidencegraph-mechanism",
        "version": "1",
    }
    assert manifest["formalBenchmark"] is False
    assert manifest["realLLMBenchmark"] is False
    assert manifest["variant"] == "llm_verification"
    assert len(manifest["scientificFingerprint"]) == 64
    assert audit["rejectedWrongHypothesisCount"] >= 1
    assert audit["acceptedCorrectHypothesisCount"] >= 1
    assert audit["selectedWrongHypothesisCount"] == 0
    assert audit["globalAbstainedHypothesisCount"] >= 1
