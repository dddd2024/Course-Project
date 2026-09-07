from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


def test_sidecar_module_entrypoint_runtime_smoke(tmp_path: Path) -> None:
    sample = tmp_path / "sample.dat"
    sample_bytes = b"\x01\x02course-project\x03\x04"
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
                "verificationEnabled": False,
                "behaviorEnabled": False,
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
    assert registered["data"]["sourceName"] == "sample.dat"

    inspected = next(item for item in responses if item.get("id") == "inspect-1")
    assert inspected["stage"] == "inspected"
    assert inspected["data"]["sha256"] == hashlib.sha256(sample_bytes).hexdigest()

    task_messages = [item for item in responses if item.get("id") == "task-1"]
    assert any(
        item.get("event") == "status"
        and item.get("stage") == "task_status"
        and item.get("data", {}).get("status") == "PARTIAL"
        for item in task_messages
    )
    result_message = next(item for item in task_messages if "resultRef" in item and "event" not in item)
    assert result_message["resultRef"] == "tasks/task-1/analysis-result.json"

    fetched = next(item for item in responses if item.get("id") == "result-1")
    assert fetched["resultRef"] == "tasks/task-1/analysis-result.json"

    result_path = state_dir / "tasks" / "task-1" / "analysis-result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["taskId"] == "task-1"
    assert result["status"] == "partial"
    assert result["inputId"] == input_ref
    assert result["resultRef"] == "tasks/task-1/analysis-result.json"
    assert result["limitations"]
