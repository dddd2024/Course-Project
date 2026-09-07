from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
FIXTURES = CONTRACTS / "fixtures"

CASES = [
    ("sidecar-message.schema.json", "sidecar-request.json"),
    ("sidecar-message.schema.json", "sidecar-progress.json"),
    ("sidecar-message.schema.json", "sidecar-result.json"),
    ("sidecar-message.schema.json", "sidecar-error.json"),
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
