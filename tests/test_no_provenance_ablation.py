from __future__ import annotations

import json
from pathlib import Path

from course_project.evidence import fuse_hypothesis_evidence
from course_project.experiments import (
    MetricRecord,
    fuse_hypothesis_evidence_without_provenance,
    run_no_provenance_ablation,
    scientific_record_fingerprint,
    write_no_provenance_ablation_execution,
)
from course_project.models import Evidence, VerificationResult

CODE_SHA = "3" * 40


def _metric(record, name: str) -> MetricRecord:
    return next(metric for metric in record.metrics if metric.name == name)


def _dependent_evidence(status: str = "accepted") -> tuple[tuple[Evidence, ...], VerificationResult]:
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
    verifier_score = 1.0 if status == "accepted" else 0.0
    verifier = Evidence(
        evidence_id="verification:h1",
        source_component="track-c-executable-verifier",
        method="length",
        feature_family="length",
        score=verifier_score,
        observation={"hypothesisId": "h1", "status": status},
        parent_evidence_ids=(candidate.evidence_id, llm.evidence_id),
        independence_group="field:1",
        sample_ids=("m1", "m2"),
    )
    verification = VerificationResult(
        hypothesis_id="h1",
        status=status,
        score=verifier_score,
        support_count=2 if status == "accepted" else 0,
        sample_count=2,
    )
    return (candidate, llm, verifier), verification


def test_no_provenance_policy_treats_each_raw_record_as_independent() -> None:
    evidence, verification = _dependent_evidence()

    control = fuse_hypothesis_evidence("h1", evidence, verification)
    ablation = fuse_hypothesis_evidence_without_provenance("h1", evidence, verification)

    assert control.raw_evidence_count == 3
    assert control.effective_component_count < control.raw_evidence_count
    assert ablation.raw_evidence_count == 3
    assert ablation.effective_component_count == 3
    assert ablation.policy == "raw-record-mean-no-provenance-v1"
    assert all(
        component.dependency_signals == ("provenance-collapse-disabled",)
        for component in ablation.components
    )


def test_no_provenance_policy_preserves_executable_verifier_veto() -> None:
    evidence, verification = _dependent_evidence(status="rejected")

    ablation = fuse_hypothesis_evidence_without_provenance("h1", evidence, verification)

    assert ablation.verification_status == "rejected"
    assert ablation.status == "rejected"


def test_no_provenance_ablation_executes_and_preserves_claim_discipline(
    tmp_path: Path,
) -> None:
    execution = run_no_provenance_ablation(tmp_path / "run", code_sha=CODE_SHA)
    record = execution.record
    audit = execution.audit

    assert record.variant == "ablation_no_provenance"
    assert record.result_scope == "mechanism"
    assert record.model_provider == "deterministic-evidencegraph-mechanism"
    assert record.model_version == "1"
    assert record.config["formalBenchmark"] is False
    assert record.config["realLLMBenchmark"] is False
    assert record.config["llmEnabled"] is True
    assert record.config["verificationEnabled"] is True
    assert record.config["provenanceAwareFusionEnabled"] is False
    assert record.config["provenanceCollapseEnabled"] is False
    assert record.config["rawEvidenceTreatedAsIndependent"] is True
    assert record.config["globalSelectionEnabled"] is True

    assert audit["controlFusionPolicy"] == "transparent-component-mean-v1"
    assert audit["ablationFusionPolicy"] == "raw-record-mean-no-provenance-v1"
    assert audit["controlCollapsedHypothesisCount"] >= 1
    assert audit["controlMaxDependencyReduction"] >= 1
    assert audit["ablationAllEvidenceIndependent"] is True
    assert audit["replayedHypothesisCount"] >= 1
    assert audit["rejectedWrongHypothesisCount"] >= 1
    assert audit["wrongHypothesisMaxConfidence"] == 0.97
    assert audit["correctHypothesisMaxConfidence"] == 0.61
    assert audit["wrongHypothesisMaxConfidence"] > audit["correctHypothesisMaxConfidence"]

    parse_coverage = _metric(record, "parse_coverage")
    constraint_rate = _metric(record, "constraint_satisfaction_rate")
    assert parse_coverage.evaluable is True
    assert parse_coverage.value is not None
    assert 0.0 <= parse_coverage.value <= 1.0
    assert constraint_rate.evaluable is True
    assert constraint_rate.value is not None
    assert 0.0 <= constraint_rate.value <= 1.0
    assert _metric(record, "token_cost_usd").value == 0.0

    semantic_accuracy = _metric(record, "field_semantic_accuracy")
    assert semantic_accuracy.evaluable is False
    assert semantic_accuracy.value is None
    assert semantic_accuracy.unavailable_reason == (
        "not evaluable from declared ground truth; missing: field_semantics"
    )


def test_no_provenance_ablation_is_scientifically_reproducible(tmp_path: Path) -> None:
    first = run_no_provenance_ablation(tmp_path / "first", code_sha=CODE_SHA)
    second = run_no_provenance_ablation(tmp_path / "second", code_sha=CODE_SHA)

    assert first.audit == second.audit
    assert scientific_record_fingerprint(first.record) == scientific_record_fingerprint(
        second.record
    )


def test_no_provenance_writer_emits_separate_canonical_artifacts(tmp_path: Path) -> None:
    execution = run_no_provenance_ablation(tmp_path / "run", code_sha=CODE_SHA)
    outdir = write_no_provenance_ablation_execution(execution, tmp_path / "records")

    assert {path.name for path in outdir.iterdir()} == {
        "ablation_no_provenance.json",
        "ablation_no_provenance.audit.json",
        "ablation-no-provenance-manifest.json",
    }
    record = json.loads((outdir / "ablation_no_provenance.json").read_text(encoding="utf-8"))
    manifest = json.loads(
        (outdir / "ablation-no-provenance-manifest.json").read_text(encoding="utf-8")
    )
    assert record["variant"] == "ablation_no_provenance"
    assert record["resultScope"] == "mechanism"
    assert record["config"]["provenanceCollapseEnabled"] is False
    assert record["model"] == {
        "provider": "deterministic-evidencegraph-mechanism",
        "version": "1",
    }
    assert manifest["formalBenchmark"] is False
    assert manifest["realLLMBenchmark"] is False
    assert manifest["variant"] == "ablation_no_provenance"
    assert len(manifest["scientificFingerprint"]) == 64
