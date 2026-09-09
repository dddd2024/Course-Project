from __future__ import annotations

import json
from pathlib import Path

from course_project.evidence import fuse_hypothesis_evidence
from course_project.experiments import (
    MetricRecord,
    fuse_hypothesis_evidence_without_verification,
    run_no_verification_ablation,
    scientific_record_fingerprint,
    write_no_verification_ablation_execution,
)
from course_project.models import Evidence, VerificationResult

CODE_SHA = "4" * 40


def _metric(record, name: str) -> MetricRecord:
    return next(metric for metric in record.metrics if metric.name == name)


def _dependent_evidence() -> tuple[tuple[Evidence, ...], VerificationResult]:
    candidate = Evidence(
        evidence_id="candidate:c1",
        source_component="track-d-field-candidate",
        method="candidate",
        feature_family="length",
        score=0.8,
        observation={"stance": "support"},
        independence_group="field:1",
        sample_ids=("m1", "m2"),
    )
    llm = Evidence(
        evidence_id="llm:h1",
        source_component="track-c-llm-provider",
        method="deterministic-test",
        feature_family="length",
        score=0.9,
        observation={"hypothesisId": "h1", "stance": "support"},
        parent_evidence_ids=(candidate.evidence_id,),
        independence_group="field:1",
        sample_ids=("m1", "m2"),
    )
    verifier = Evidence(
        evidence_id="verification:h1",
        source_component="track-c-executable-verifier",
        method="length",
        feature_family="length",
        score=0.0,
        observation={"hypothesisId": "h1", "status": "rejected"},
        parent_evidence_ids=(candidate.evidence_id, llm.evidence_id),
        independence_group="field:1",
        sample_ids=("m1", "m2"),
    )
    verification = VerificationResult(
        hypothesis_id="h1",
        status="rejected",
        score=0.0,
        support_count=0,
        sample_count=2,
    )
    return (candidate, llm, verifier), verification


def test_no_verification_policy_removes_verifier_gate_but_keeps_provenance_collapse() -> None:
    evidence, verification = _dependent_evidence()

    control = fuse_hypothesis_evidence("h1", evidence, verification)
    ablation = fuse_hypothesis_evidence_without_verification("h1", evidence)

    assert control.status == "rejected"
    assert control.verification_status == "rejected"
    assert ablation.status == "accepted"
    assert ablation.verification_status == "uncertain"
    assert ablation.policy == "transparent-component-mean-no-verifier-v1"
    assert ablation.raw_evidence_count == 2
    assert ablation.effective_component_count == 1
    assert all(
        "track-c-executable-verifier" not in component.source_components
        for component in ablation.components
    )


def test_no_verification_ablation_executes_and_preserves_claim_discipline(
    tmp_path: Path,
) -> None:
    execution = run_no_verification_ablation(tmp_path / "run", code_sha=CODE_SHA)
    record = execution.record
    audit = execution.audit

    assert record.variant == "ablation_no_verification"
    assert record.result_scope == "mechanism"
    assert record.model_provider == "deterministic-evidencegraph-mechanism"
    assert record.model_version == "1"
    assert record.config["formalBenchmark"] is False
    assert record.config["realLLMBenchmark"] is False
    assert record.config["llmEnabled"] is True
    assert record.config["verificationEnabled"] is False
    assert record.config["verificationEvidenceUsed"] is False
    assert record.config["verificationSelectionScore"] == 0.0
    assert record.config["provenanceAwareFusionEnabled"] is True
    assert record.config["provenanceCollapseEnabled"] is True
    assert record.config["globalSelectionEnabled"] is True

    assert audit["controlVerificationExecuted"] is True
    assert audit["ablationVerificationExecuted"] is False
    assert audit["controlFusionPolicy"] == "transparent-component-mean-v1"
    assert audit["ablationFusionPolicy"] == "transparent-component-mean-no-verifier-v1"
    assert audit["provenanceCollapseEnabled"] is True
    assert audit["replayedHypothesisCount"] >= 1
    assert audit["controlRejectedWrongHypothesisCount"] >= 1
    assert audit["wrongHypothesisNotRejectedWithoutVerificationCount"] >= 1
    assert audit["wrongHypothesisMaxConfidence"] == 0.97
    assert audit["correctHypothesisMaxConfidence"] == 0.61
    assert audit["wrongHypothesisMaxConfidence"] > audit["correctHypothesisMaxConfidence"]

    parse_coverage = _metric(record, "parse_coverage")
    assert parse_coverage.evaluable is True
    assert parse_coverage.value is not None
    assert 0.0 <= parse_coverage.value <= 1.0

    constraint_rate = _metric(record, "constraint_satisfaction_rate")
    assert constraint_rate.evaluable is False
    assert constraint_rate.value is None
    assert constraint_rate.unavailable_reason == (
        "not applicable: executable verification intentionally disabled in this ablation"
    )

    semantic_accuracy = _metric(record, "field_semantic_accuracy")
    assert semantic_accuracy.evaluable is False
    assert semantic_accuracy.value is None
    assert semantic_accuracy.unavailable_reason == (
        "not evaluable from declared ground truth; missing: field_semantics"
    )
    assert _metric(record, "token_cost_usd").value == 0.0


def test_no_verification_ablation_is_scientifically_reproducible(tmp_path: Path) -> None:
    first = run_no_verification_ablation(tmp_path / "first", code_sha=CODE_SHA)
    second = run_no_verification_ablation(tmp_path / "second", code_sha=CODE_SHA)

    assert first.audit == second.audit
    assert scientific_record_fingerprint(first.record) == scientific_record_fingerprint(
        second.record
    )


def test_no_verification_writer_emits_separate_canonical_artifacts(tmp_path: Path) -> None:
    execution = run_no_verification_ablation(tmp_path / "run", code_sha=CODE_SHA)
    outdir = write_no_verification_ablation_execution(execution, tmp_path / "records")

    assert {path.name for path in outdir.iterdir()} == {
        "ablation_no_verification.json",
        "ablation_no_verification.audit.json",
        "ablation-no-verification-manifest.json",
    }
    record = json.loads(
        (outdir / "ablation_no_verification.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (outdir / "ablation-no-verification-manifest.json").read_text(encoding="utf-8")
    )
    assert record["variant"] == "ablation_no_verification"
    assert record["resultScope"] == "mechanism"
    assert record["config"]["verificationEnabled"] is False
    assert record["config"]["provenanceCollapseEnabled"] is True
    assert record["model"] == {
        "provider": "deterministic-evidencegraph-mechanism",
        "version": "1",
    }
    constraint_rate = next(
        metric
        for metric in record["metrics"]
        if metric["name"] == "constraint_satisfaction_rate"
    )
    assert constraint_rate["evaluable"] is False
    assert constraint_rate["value"] is None
    assert manifest["formalBenchmark"] is False
    assert manifest["realLLMBenchmark"] is False
    assert manifest["variant"] == "ablation_no_verification"
    assert len(manifest["scientificFingerprint"]) == 64
