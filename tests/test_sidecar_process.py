from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


def _make_message(msg_type: int, seq: int, payload: bytes) -> bytes:
    return (
        b"SYN1"
        + bytes([msg_type])
        + b"\x00\x00\x00"
        + bytes([seq])
        + (11 + len(payload)).to_bytes(2, "big")
        + payload
    )


def test_synthetic_placeholder_uses_final_teacher_data_ingress_without_labels(
    tmp_path: Path,
) -> None:
    sample = tmp_path / "teacher-placeholder.dat"
    sample_bytes = b"".join(_make_message(0x01, i + 1, b"P" * 8) for i in range(4))
    sample.write_bytes(sample_bytes)
    input_ref = f"input-{hashlib.sha256(sample_bytes).hexdigest()[:16]}"
    state_dir = tmp_path / "state"

    requests = [
        {
            "protocolVersion": 1,
            "id": "register-1",
            "method": "register_input",
            "params": {"sourceRef": str(sample)},
        },
        {
            "protocolVersion": 1,
            "id": "inspect-1",
            "method": "inspect_file",
            "params": {"inputRef": input_ref},
        },
        {
            "protocolVersion": 1,
            "id": "task-1",
            "method": "analyze",
            "params": {
                "inputRef": input_ref,
                "mode": "baseline",
                "llmEnabled": False,
                "verificationEnabled": True,
                "behaviorEnabled": True,
                "optionalDependencyPolicy": "degrade",
            },
        },
        {
            "protocolVersion": 1,
            "id": "result-1",
            "method": "get_result",
            "params": {"taskId": "task-1"},
        },
    ]
    stdin_payload = "".join(json.dumps(item) + "\n" for item in requests)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "course_project.sidecar",
            "--state-dir",
            str(state_dir),
            "--allow-root",
            str(tmp_path),
        ],
        input=stdin_payload,
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    responses = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    assert responses
    assert all(item["protocolVersion"] == 1 for item in responses)

    registered = next(item for item in responses if item.get("id") == "register-1")
    assert registered["event"] == "status"
    assert registered["stage"] == "registered"
    assert registered["data"]["inputRef"] == input_ref
    assert registered["data"]["sourceName"] == "teacher-placeholder.dat"
    assert registered["data"]["sha256"] == hashlib.sha256(sample_bytes).hexdigest()

    inspected = next(item for item in responses if item.get("id") == "inspect-1")
    assert inspected["stage"] == "inspected"
    assert inspected["data"]["sha256"] == hashlib.sha256(sample_bytes).hexdigest()

    task_messages = [item for item in responses if item.get("id") == "task-1"]
    assert any(
        item.get("event") == "status"
        and item.get("stage") == "task_status"
        and item.get("data", {}).get("status") == "COMPLETED"
        for item in task_messages
    )
    result_message = next(
        item for item in task_messages if "resultRef" in item and "event" not in item
    )
    assert result_message["resultRef"] == "tasks/task-1/analysis-result.json"

    fetched = next(item for item in responses if item.get("id") == "result-1")
    assert fetched["resultRef"] == "tasks/task-1/analysis-result.json"

    result_path = state_dir / "tasks" / "task-1" / "analysis-result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["taskId"] == "task-1"
    assert result["status"] == "COMPLETED"
    assert result["inputId"] == input_ref
    assert result["resultRef"] == "tasks/task-1/analysis-result.json"
    assert result["findings"]
    assert {finding["status"] for finding in result["findings"]} <= {
        "ACCEPTED",
        "REJECTED",
        "UNCERTAIN",
    }
    assert result["metrics"]["analysisBackend"] == "track-d-baseline-v1"
    assert result["metrics"]["trackDExecuted"] is True
    assert result["metrics"]["semanticExecuted"] is True
    assert result["metrics"]["semanticBackend"] == "track-a-delegated-track-c-semantic-v1"
    assert result["metrics"]["verifiedFieldCount"] > 0
    assert result["metrics"]["messageCount"] > 0
    assert result["metrics"]["fieldCandidateCount"] > 0
    assert result["limitations"] == []

    artifact_types = {artifact["type"] for artifact in result["artifacts"]}
    assert {"messages", "alignment", "statistics", "behavior", "evidence", "schema"} <= artifact_types
    for artifact in result["artifacts"]:
        artifact_path = state_dir / artifact["ref"]
        assert artifact_path.is_file()
        json.loads(artifact_path.read_text(encoding="utf-8"))
