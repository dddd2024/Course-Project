from __future__ import annotations

import hashlib
import json
from importlib.metadata import version
from pathlib import Path

import pytest

from course_project.experiments.external_pre import (
    PINNED_NETZOB_VERSION,
    run_live_netzob_mechanism_experiment,
    write_netzob_experiment_bundle,
)
from course_project.inference.netzob_adapter import is_netzob_available
from course_project.models import FieldCandidate

pytestmark = pytest.mark.skipif(
    not is_netzob_available(),
    reason="live Netzob experiment runs only in the isolated Netzob workflow",
)

CODE_SHA = "1" * 40


def _metric(record, name: str):
    return next(metric for metric in record.metrics if metric.name == name)


def test_live_netzob_2_0_0_materializes_canonical_mechanism_record(
    tmp_path: Path,
) -> None:
    assert version("Netzob") == PINNED_NETZOB_VERSION

    bundle = run_live_netzob_mechanism_experiment(code_sha=CODE_SHA)
    record = bundle.record

    assert record.variant == "netzob_pre"
    assert record.result_scope == "mechanism"
    assert record.dataset.dataset_id == "synthetic-mechanism-v1"
    assert record.dataset.corpus_kind == "synthetic"
    assert record.config["backend"] == "netzob"
    assert record.config["backendVersion"] == PINNED_NETZOB_VERSION
    assert record.config["formalBenchmark"] is False
    assert record.config["externalGroundTruthUsed"] is False
    assert record.config["productionPromotion"] is False
    assert record.config["sourceDto"] == "FieldCandidate"
    assert "not Track C semantic verification" in str(record.config["projectionSemantics"])
    assert bundle.field_candidates
    assert all(isinstance(item, FieldCandidate) for item in bundle.field_candidates)
    assert all(
        item.attributes.get("backend") == "netzob" for item in bundle.field_candidates
    )

    parse_coverage = _metric(record, "parse_coverage")
    assert parse_coverage.evaluable is True
    assert parse_coverage.value is not None
    assert 0.0 <= parse_coverage.value <= 1.0

    constraint_rate = _metric(record, "constraint_satisfaction_rate")
    assert constraint_rate.evaluable is False
    assert constraint_rate.value is None
    assert "semantic verifier" in str(constraint_rate.unavailable_reason)

    out_dir = write_netzob_experiment_bundle(bundle, tmp_path / "records")
    candidate_path = out_dir / "netzob-field-candidates.json"
    record_path = out_dir / "netzob_pre.json"
    assert candidate_path.is_file()
    assert record_path.is_file()
    assert hashlib.sha256(candidate_path.read_bytes()).hexdigest() == (
        record.artifacts[0].sha256
    )

    candidate_payload = json.loads(candidate_path.read_text(encoding="utf-8"))
    record_payload = json.loads(record_path.read_text(encoding="utf-8"))
    assert candidate_payload["semanticVerificationExecuted"] is False
    assert candidate_payload["projectNativeDto"] == "FieldCandidate"
    assert record_payload["variant"] == "netzob_pre"
    assert record_payload["config"]["productionPromotion"] is False
