from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from course_project.experiments import build_synthetic_mechanism_corpus
from course_project.experiments.external_pre import (
    PINNED_NETZOB_VERSION,
    build_netzob_experiment_bundle,
    write_netzob_experiment_bundle,
)
from course_project.experiments.records import ExperimentValidationError
from course_project.inference.netzob_adapter import PREBaselineResult
from course_project.models import FieldCandidate

CODE_SHA = "1" * 40


def _candidate(
    candidate_id: str,
    *,
    offset: int,
    size: int | None,
    candidate_type: str,
) -> FieldCandidate:
    return FieldCandidate(
        candidate_id=candidate_id,
        family_id=None,
        offset=offset,
        size=size,
        candidate_types=(candidate_type,),
        endian=None,
        score=0.9,
        attributes={"backend": "netzob", "support": 8, "sample_count": 8},
    )


def _successful_result() -> PREBaselineResult:
    return PREBaselineResult(
        backend="netzob",
        status="ok",
        field_candidates=(
            _candidate("netzob-f0", offset=0, size=4, candidate_type="magic"),
            _candidate("netzob-f1", offset=4, size=1, candidate_type="enum"),
            _candidate("netzob-f2", offset=5, size=None, candidate_type="unknown"),
        ),
    )


def _bundle(result: PREBaselineResult | None = None):
    return build_netzob_experiment_bundle(
        corpus=build_synthetic_mechanism_corpus(),
        result=result or _successful_result(),
        code_sha=CODE_SHA,
        backend_version=PINNED_NETZOB_VERSION,
        project_version="0.1.0",
        python_version="3.10.21",
        processing_time_seconds=0.25,
    )


def _metric(record, name: str):
    return next(metric for metric in record.metrics if metric.name == name)


def test_netzob_bundle_records_structural_mechanism_without_semantic_overclaim() -> None:
    bundle = _bundle()
    record = bundle.record

    assert record.variant == "netzob_pre"
    assert record.result_scope == "mechanism"
    assert record.dataset.dataset_id == "synthetic-mechanism-v1"
    assert record.dataset.corpus_kind == "synthetic"
    assert record.code_sha == CODE_SHA
    assert record.config["backend"] == "netzob"
    assert record.config["backendVersion"] == PINNED_NETZOB_VERSION
    assert record.config["formalBenchmark"] is False
    assert record.config["externalGroundTruthUsed"] is False
    assert record.config["sourceDto"] == "FieldCandidate"
    assert record.config["productionPromotion"] is False
    assert "not Track C semantic verification" in str(record.config["projectionSemantics"])

    parse_coverage = _metric(record, "parse_coverage")
    assert parse_coverage.evaluable is True
    assert parse_coverage.value == 1.0

    constraint_rate = _metric(record, "constraint_satisfaction_rate")
    assert constraint_rate.evaluable is False
    assert constraint_rate.value is None
    assert "does not execute the project semantic verifier" in str(
        constraint_rate.unavailable_reason
    )

    for metric_name in (
        "packet_boundary_f1",
        "field_boundary_f1",
        "field_semantic_accuracy",
        "false_hypothesis_rate",
        "restoration_accuracy",
        "accepted_field_coverage",
        "risk_coverage",
    ):
        metric = _metric(record, metric_name)
        assert metric.evaluable is False
        assert metric.value is None
        assert "missing" in str(metric.unavailable_reason)

    assert {item.name: item.version for item in record.dependencies} == {
        "course-project": "0.1.0",
        "Netzob": PINNED_NETZOB_VERSION,
        "python": "3.10.21",
    }
    assert len(record.artifacts) == 1
    assert record.artifacts[0].artifact_id == "netzob-field-candidates"
    assert bundle.field_candidates == _successful_result().field_candidates


def test_candidate_artifact_is_canonical_project_native_evidence() -> None:
    bundle = _bundle()
    payload = json.loads(bundle.candidate_artifact_json)

    assert payload["backend"] == "netzob"
    assert payload["projectNativeDto"] == "FieldCandidate"
    assert payload["datasetId"] == bundle.corpus.dataset.dataset_id
    assert payload["datasetSha256"] == bundle.corpus.dataset.sha256
    assert payload["semanticVerificationExecuted"] is False
    assert [item["candidateId"] for item in payload["candidates"]] == [
        "netzob-f0",
        "netzob-f1",
        "netzob-f2",
    ]

    digest = hashlib.sha256(bundle.candidate_artifact_json.encode("utf-8")).hexdigest()
    assert bundle.record.artifacts[0].sha256 == digest
    assert bundle.record.config["candidateArtifactSha256"] == digest


def test_writer_preserves_candidate_hash_and_canonical_record(tmp_path: Path) -> None:
    bundle = _bundle()
    out_dir = write_netzob_experiment_bundle(bundle, tmp_path / "records")

    assert {path.name for path in out_dir.iterdir()} == {
        "netzob-field-candidates.json",
        "netzob_pre.json",
    }
    candidate_path = out_dir / "netzob-field-candidates.json"
    record_path = out_dir / "netzob_pre.json"
    assert hashlib.sha256(candidate_path.read_bytes()).hexdigest() == (
        bundle.record.artifacts[0].sha256
    )

    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["variant"] == "netzob_pre"
    assert record["resultScope"] == "mechanism"
    assert record["config"]["productionPromotion"] is False
    assert record["artifacts"][0]["sha256"] == bundle.record.artifacts[0].sha256


@pytest.mark.parametrize("status", ["unavailable", "failed"])
def test_unsuccessful_upstream_result_fails_closed(status: str) -> None:
    result = PREBaselineResult(
        backend="netzob",
        status=status,
        error_category="dependency_unavailable" if status == "unavailable" else "inference_failed",
        detail="controlled failure",
    )

    with pytest.raises(ExperimentValidationError, match="must succeed before recording"):
        _bundle(result)


def test_empty_success_fails_closed() -> None:
    with pytest.raises(ExperimentValidationError, match="emitted no FieldCandidate"):
        _bundle(PREBaselineResult(backend="netzob", status="ok"))


def test_wrong_backend_provenance_fails_closed() -> None:
    result = PREBaselineResult(
        backend="netzob",
        status="ok",
        field_candidates=(
            FieldCandidate(
                candidate_id="wrong-provenance",
                family_id=None,
                offset=0,
                size=4,
                candidate_types=("magic",),
                score=1.0,
                attributes={"backend": "other"},
            ),
        ),
    )

    with pytest.raises(ExperimentValidationError, match="preserve backend=netzob"):
        _bundle(result)


def test_overlapping_structural_candidates_fail_closed() -> None:
    result = PREBaselineResult(
        backend="netzob",
        status="ok",
        field_candidates=(
            _candidate("a", offset=0, size=4, candidate_type="magic"),
            _candidate("b", offset=3, size=2, candidate_type="enum"),
        ),
    )

    with pytest.raises(ExperimentValidationError, match="structural candidates overlap"):
        _bundle(result)


def test_wrong_pinned_backend_version_fails_closed() -> None:
    with pytest.raises(ExperimentValidationError, match="pinned to 2.0.0"):
        build_netzob_experiment_bundle(
            corpus=build_synthetic_mechanism_corpus(),
            result=_successful_result(),
            code_sha=CODE_SHA,
            backend_version="2.0.1",
            project_version="0.1.0",
            python_version="3.10.21",
            processing_time_seconds=0.25,
        )
