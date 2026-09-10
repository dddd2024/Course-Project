from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
FIXTURES = CONTRACTS / "fixtures"

CASES = [
    ("sidecar-message.schema.json", "sidecar-register-input.json"),
    ("sidecar-message.schema.json", "sidecar-request.json"),
    ("sidecar-message.schema.json", "sidecar-read-range.json"),
    ("sidecar-message.schema.json", "sidecar-progress.json"),
    ("sidecar-message.schema.json", "sidecar-result.json"),
    ("sidecar-message.schema.json", "sidecar-error.json"),
    ("sidecar-message.schema.json", "sidecar-register-input-result.json"),
    ("sidecar-message.schema.json", "sidecar-inspect-result.json"),
    ("sidecar-message.schema.json", "sidecar-read-range-result.json"),
    ("sidecar-message.schema.json", "sidecar-task-status.json"),
    ("analysis-result.schema.json", "analysis-result.json"),
    ("agent-response.schema.json", "agent-response.json"),
]


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def test_golden_contract_fixtures_validate() -> None:
    for schema_name, fixture_name in CASES:
        schema = load_json(CONTRACTS / schema_name)
        fixture = load_json(FIXTURES / fixture_name)
        validator = Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(fixture), key=lambda error: list(error.path))
        assert not errors, (
            f"{fixture_name} does not validate against {schema_name}: "
            + "; ".join(error.message for error in errors)
        )


def test_sidecar_fixture_ids_stay_correlated() -> None:
    ids = {
        load_json(FIXTURES / name)["id"]
        for name in (
            "sidecar-request.json",
            "sidecar-progress.json",
            "sidecar-result.json",
            "sidecar-error.json",
        )
    }
    assert ids == {"task-demo-001"}


def test_sidecar_request_uses_canonical_analyze_method() -> None:
    request = load_json(FIXTURES / "sidecar-request.json")
    assert request["method"] == "analyze"
    assert request["params"]["mode"] in {"baseline", "evidencegraph"}


def test_sidecar_rejects_unknown_method_and_config_keys() -> None:
    schema = load_json(CONTRACTS / "sidecar-message.schema.json")
    validator = Draft202012Validator(schema)

    unknown_method = {
        "protocolVersion": 1,
        "id": "task-bad-001",
        "method": "run_analysis",
        "params": {"inputRef": "input-1", "mode": "baseline"},
    }
    drifted_config = {
        "protocolVersion": 1,
        "id": "task-bad-002",
        "method": "analyze",
        "params": {
            "inputRef": "input-1",
            "mode": "baseline",
            "enable_llm": True,
        },
    }

    assert list(validator.iter_errors(unknown_method))
    assert list(validator.iter_errors(drifted_config))


def test_sidecar_status_payloads_are_stage_specific() -> None:
    schema = load_json(CONTRACTS / "sidecar-message.schema.json")
    validator = Draft202012Validator(schema)
    wrong_payload = {
        "protocolVersion": 1,
        "id": "bad-range-001",
        "event": "status",
        "stage": "range",
        "data": {"inputRef": "input-1"},
    }
    assert list(validator.iter_errors(wrong_payload))


def test_analysis_result_evidence_references_resolve() -> None:
    result = load_json(FIXTURES / "analysis-result.json")
    evidence_ids = {item["evidenceId"] for item in result["evidence"]}

    for finding in result["findings"]:
        assert set(finding["evidenceIds"]).issubset(evidence_ids)
        assert finding["status"] in {"ACCEPTED", "REJECTED", "UNCERTAIN"}


def test_analysis_result_artifact_ids_are_unique() -> None:
    result = load_json(FIXTURES / "analysis-result.json")
    artifact_ids = [item["artifactId"] for item in result["artifacts"]]
    assert len(artifact_ids) == len(set(artifact_ids))


def test_evaluation_metadata_contract_accepts_pinned_public_corpus() -> None:
    schema = load_json(CONTRACTS / "teacher-dataset-metadata.schema.json")
    validator = Draft202012Validator(schema)
    public_metadata = {
        "contractVersion": 1,
        "datasetId": "nfstream-public-behavior-v1",
        "corpusKind": "public",
        "version": "nfstream-1426d78597bb",
        "sha256": "a" * 64,
        "sizeBytes": 1,
        "redistributionStatus": "unknown",
        "preprocessing": ["verify exact object hashes", "extract flow observations"],
        "groundTruth": {
            "reference": "pinned upstream expected-result CSV files",
            "sha256": "b" * 64,
            "capabilities": ["behavior_labels"],
        },
    }

    assert not list(validator.iter_errors(public_metadata))
