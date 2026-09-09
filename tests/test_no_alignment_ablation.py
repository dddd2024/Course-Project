from __future__ import annotations

import json
from pathlib import Path

from course_project.experiments.execution import scientific_record_fingerprint
from course_project.experiments.no_alignment import (
    ALIGNMENT_ABLATION_SCOPE,
    run_no_alignment_ablation,
    write_no_alignment_ablation_execution,
)

_CODE_SHA = "a" * 40


def test_no_alignment_ablation_is_deterministic_and_scoped(tmp_path: Path) -> None:
    first = run_no_alignment_ablation(tmp_path / "first", code_sha=_CODE_SHA)
    second = run_no_alignment_ablation(tmp_path / "second", code_sha=_CODE_SHA)

    assert scientific_record_fingerprint(first.record) == scientific_record_fingerprint(
        second.record
    )
    assert first.record.variant == "ablation_no_alignment"
    assert first.record.result_scope == "mechanism"
    assert first.record.config["ablationScope"] == ALIGNMENT_ABLATION_SCOPE
    assert first.record.config["preprocessingAlignmentStillUsed"] is True
    assert first.record.config["trackCAlignmentInputRemoved"] is True
    assert first.record.config["alignmentEvidenceUsed"] is False
    assert first.record.config["structuralIntermediatesMatchControl"] is True
    assert first.record.config["providerHypothesesMatchControl"] is True


def test_no_alignment_ablation_removes_only_alignment_evidence(tmp_path: Path) -> None:
    execution = run_no_alignment_ablation(tmp_path / "run", code_sha=_CODE_SHA)
    audit = execution.audit

    assert audit["controlAlignmentEvidenceCount"] > 0
    assert audit["ablationAlignmentEvidenceCount"] == 0
    assert "track-d-alignment" not in audit["ablationFusionEvidenceProducers"]
    assert audit["verificationExecuted"] is True
    assert audit["fusionExecuted"] is True
    assert audit["globalSelectionExecuted"] is True
    assert audit["providerRequestCount"] > 0
    assert audit["rejectedWrongHypothesisCount"] >= 1
    assert audit["structuralIntermediatesMatchControl"] is True
    assert audit["providerHypothesesMatchControl"] is True


def test_no_alignment_writer_preserves_claim_boundary(tmp_path: Path) -> None:
    execution = run_no_alignment_ablation(tmp_path / "run", code_sha=_CODE_SHA)
    output = write_no_alignment_ablation_execution(execution, tmp_path / "records")

    record = json.loads((output / "ablation_no_alignment.json").read_text(encoding="utf-8"))
    audit = json.loads((output / "ablation_no_alignment.audit.json").read_text(encoding="utf-8"))
    manifest = json.loads(
        (output / "ablation-no-alignment-manifest.json").read_text(encoding="utf-8")
    )

    assert record["variant"] == "ablation_no_alignment"
    assert record["resultScope"] == "mechanism"
    assert record["config"]["ablationScope"] == ALIGNMENT_ABLATION_SCOPE
    assert record["config"]["preprocessingAlignmentStillUsed"] is True
    assert record["config"]["formalBenchmark"] is False
    assert record["config"]["realLLMBenchmark"] is False
    semantic = next(
        item for item in record["metrics"] if item["name"] == "field_semantic_accuracy"
    )
    assert semantic["evaluable"] is False
    assert semantic["value"] is None
    assert audit["teacherBenchmark"] is False
    assert audit["realLLMBenchmark"] is False
    assert manifest["ablationScope"] == ALIGNMENT_ABLATION_SCOPE
    assert manifest["preprocessingAlignmentStillUsed"] is True
    assert manifest["formalBenchmark"] is False
    assert manifest["realLLMBenchmark"] is False
