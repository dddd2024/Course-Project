from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from io import StringIO
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from course_project.models import (
    AnalysisFinding,
    AnalysisResult,
    ArtifactRef,
    ByteLocation,
    Evidence,
    InputMetadata,
)
from course_project.sidecar.cli import serve_stream
from course_project.sidecar.runtime import SidecarRuntime

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"


def _schema(name: str) -> dict[str, Any]:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def _assert_sidecar_messages_validate(messages: list[dict[str, Any]]) -> None:
    validator = Draft202012Validator(_schema("sidecar-message.schema.json"))
    for message in messages:
        errors = list(validator.iter_errors(message))
        assert not errors, "; ".join(error.message for error in errors)


class EvidenceBackend:
    def analyze(
        self,
        *,
        task_id: str,
        input_metadata: InputMetadata,
        input_path: Path,
        config: Mapping[str, Any],
    ) -> AnalysisResult:
        assert input_path.is_file()
        assert config["mode"] == "evidencegraph"
        evidence = Evidence(
            evidence_id="ev-test-001",
            source_component="test-backend",
            method="fixture-observation",
            feature_family="integration",
            score=0.9,
            observation={"sizeBytes": input_metadata.size_bytes},
            independence_group="integration-fixture",
            sample_ids=(input_metadata.input_id,),
        )
        finding = AnalysisFinding(
            finding_id="finding-test-001",
            claim="integration fixture is observable",
            status="accepted",
            semantic_type="integration",
            evidence_ids=(evidence.evidence_id,),
            location=ByteLocation(input_metadata.input_id, 0, min(input_metadata.size_bytes, 4)),
            scores={"evidence": 0.9, "verification": 1.0},
        )
        artifact = ArtifactRef(
            artifact_id="artifact-test-001",
            type="statistics",
            format="json",
            ref=f"tasks/{task_id}/statistics.json",
            count=1,
        )
        return AnalysisResult(
            task_id=task_id,
            status="completed",
            input_id=input_metadata.input_id,
            findings=(finding,),
            evidence=(evidence,),
            artifacts=(artifact,),
            metrics={"integration": 1.0},
        )


def test_register_inspect_and_read_range_round_trip(tmp_path: Path) -> None:
    sample = tmp_path / "sample.dat"
    sample.write_bytes(bytes(range(16)))
    runtime = SidecarRuntime(state_dir=tmp_path / "state", allowed_roots=(tmp_path,))

    registered = runtime.handle(
        {
            "protocolVersion": 1,
            "id": "register-001",
            "method": "register_input",
            "params": {"sourceRef": str(sample), "kindHint": "dat"},
        }
    )
    _assert_sidecar_messages_validate(registered)
    input_ref = registered[0]["data"]["inputRef"]
    assert registered[0]["data"]["sourceName"] == "sample.dat"
    assert registered[0]["data"]["sizeBytes"] == 16

    inspected = runtime.handle(
        {
            "protocolVersion": 1,
            "id": "inspect-001",
            "method": "inspect_file",
            "params": {"inputRef": input_ref},
        }
    )
    _assert_sidecar_messages_validate(inspected)
    assert inspected[0]["data"]["sha256"] == registered[0]["data"]["sha256"]

    ranged = runtime.handle(
        {
            "protocolVersion": 1,
            "id": "range-001",
            "method": "read_range",
            "params": {"inputRef": input_ref, "offset": 4, "length": 6},
        }
    )
    _assert_sidecar_messages_validate(ranged)
    assert base64.b64decode(ranged[0]["data"]["bytes"]) == bytes(range(4, 10))
    assert ranged[0]["data"]["actualLength"] == 6
    assert ranged[0]["data"]["eof"] is False


def test_default_backend_is_explicit_partial_not_fake_analysis(tmp_path: Path) -> None:
    sample = tmp_path / "sample.dat"
    sample.write_bytes(b"\x00\x01\x02\x03")
    runtime = SidecarRuntime(state_dir=tmp_path / "state")
    register = runtime.handle(
        {
            "protocolVersion": 1,
            "id": "register-default",
            "method": "register_input",
            "params": {"sourceRef": str(sample)},
        }
    )
    input_ref = register[0]["data"]["inputRef"]

    messages = runtime.handle(
        {
            "protocolVersion": 1,
            "id": "task-default-001",
            "method": "analyze",
            "params": {"inputRef": input_ref, "mode": "baseline"},
        }
    )
    _assert_sidecar_messages_validate(messages)
    assert messages[-2]["data"]["status"] == "PARTIAL"
    result_ref = messages[-1]["resultRef"]
    result_path = tmp_path / "state" / result_ref
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["status"] == "PARTIAL"
    assert payload["findings"] == []
    assert payload["limitations"]
    validator = Draft202012Validator(_schema("analysis-result.schema.json"))
    assert not list(validator.iter_errors(payload))


def test_backend_result_serializes_and_get_result_is_idempotent(tmp_path: Path) -> None:
    sample = tmp_path / "sample.bin"
    sample.write_bytes(b"abcdefgh")
    runtime = SidecarRuntime(state_dir=tmp_path / "state", backend=EvidenceBackend())
    register = runtime.handle(
        {
            "protocolVersion": 1,
            "id": "register-evidence",
            "method": "register_input",
            "params": {"sourceRef": str(sample), "kindHint": "bin"},
        }
    )
    input_ref = register[0]["data"]["inputRef"]
    request = {
        "protocolVersion": 1,
        "id": "task-evidence-001",
        "method": "analyze",
        "params": {
            "inputRef": input_ref,
            "mode": "evidencegraph",
            "llmEnabled": False,
            "verificationEnabled": True,
            "optionalDependencyPolicy": "degrade",
        },
    }

    first = runtime.handle(request)
    _assert_sidecar_messages_validate(first)
    assert first[-2]["data"]["status"] == "COMPLETED"
    result_ref = first[-1]["resultRef"]
    result_path = tmp_path / "state" / result_ref
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(_schema("analysis-result.schema.json"))
    assert not list(validator.iter_errors(payload))
    assert payload["findings"][0]["status"] == "ACCEPTED"
    assert payload["findings"][0]["evidenceIds"] == ["ev-test-001"]
    assert payload["artifacts"][0]["ref"].startswith("tasks/task-evidence-001/")

    duplicate = runtime.handle(request)
    _assert_sidecar_messages_validate(duplicate)
    assert duplicate[-1]["resultRef"] == result_ref

    fetched = runtime.handle(
        {
            "protocolVersion": 1,
            "id": "get-result-001",
            "method": "get_result",
            "params": {"taskId": "task-evidence-001"},
        }
    )
    _assert_sidecar_messages_validate(fetched)
    assert fetched == [{"protocolVersion": 1, "id": "get-result-001", "resultRef": result_ref}]


def test_runtime_rejects_contract_drift_label_leakage_and_version_mismatch(
    tmp_path: Path,
) -> None:
    runtime = SidecarRuntime(state_dir=tmp_path / "state")
    forbidden_params = (
        {"enable_llm": True},
        {"groundTruthRef": "answers.json"},
        {"labels": {"message-1": "header"}},
        {"answerKey": {"protocol": "example"}},
        {"expectedProtocol": "SYN1"},
    )
    for index, forbidden in enumerate(forbidden_params):
        rejected = runtime.handle(
            {
                "protocolVersion": 1,
                "id": f"bad-config-{index}",
                "method": "analyze",
                "params": {"inputRef": "input-1", "mode": "baseline", **forbidden},
            }
        )
        _assert_sidecar_messages_validate(rejected)
        assert rejected[0]["error"]["code"] == "invalid_input"

    mismatch = runtime.handle(
        {
            "protocolVersion": 2,
            "id": "bad-version",
            "method": "inspect_file",
            "params": {"inputRef": "input-1"},
        }
    )
    _assert_sidecar_messages_validate(mismatch)
    assert mismatch[0]["error"]["code"] == "contract_version_mismatch"


def test_jsonl_server_keeps_diagnostics_out_of_stdout(tmp_path: Path) -> None:
    runtime = SidecarRuntime(state_dir=tmp_path / "state")
    instream = StringIO("not-json\n")
    outstream = StringIO()
    errstream = StringIO()

    assert serve_stream(runtime, instream, outstream, errstream) == 0
    response = json.loads(outstream.getvalue())
    assert response["error"]["code"] == "invalid_input"
    assert "input error" in errstream.getvalue()
