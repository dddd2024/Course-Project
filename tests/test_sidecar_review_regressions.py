from __future__ import annotations

from pathlib import Path

from course_project.models import AnalysisResult
from course_project.sidecar.runtime import SidecarError, SidecarRuntime


def _register(runtime: SidecarRuntime, sample: Path) -> str:
    messages = runtime.handle(
        {
            "protocolVersion": 1,
            "id": "register-review-regression",
            "method": "register_input",
            "params": {"sourceRef": str(sample)},
        }
    )
    assert "error" not in messages[0]
    return messages[0]["data"]["inputRef"]


def test_completed_analyze_retry_survives_source_removal(tmp_path: Path) -> None:
    sample = tmp_path / "sample.dat"
    sample.write_bytes(b"retry-me")
    runtime = SidecarRuntime(state_dir=tmp_path / "state")
    input_ref = _register(runtime, sample)
    request = {
        "protocolVersion": 1,
        "id": "task-retry-after-removal",
        "method": "analyze",
        "params": {"inputRef": input_ref, "mode": "baseline"},
    }

    first = runtime.handle(request)
    assert first[-2]["data"]["status"] == "PARTIAL"
    result_ref = first[-1]["resultRef"]

    sample.unlink()

    retried = runtime.handle(request)
    assert "error" not in retried[0]
    assert retried[0]["data"]["status"] == "PARTIAL"
    assert retried[-1]["resultRef"] == result_ref


def test_result_persistence_failure_marks_task_failed(tmp_path: Path) -> None:
    sample = tmp_path / "sample.dat"
    sample.write_bytes(b"persist-me")
    runtime = SidecarRuntime(state_dir=tmp_path / "state")
    input_ref = _register(runtime, sample)

    def fail_write(result: AnalysisResult) -> str:
        raise SidecarError(
            "sidecar_failed",
            "synthetic persistence failure",
            details={"taskId": result.task_id},
        )

    runtime.results.write_analysis_result = fail_write  # type: ignore[method-assign]

    failed = runtime.handle(
        {
            "protocolVersion": 1,
            "id": "task-persist-failed",
            "method": "analyze",
            "params": {"inputRef": input_ref, "mode": "baseline"},
        }
    )
    assert failed[0]["error"]["code"] == "sidecar_failed"

    status = runtime.handle(
        {
            "protocolVersion": 1,
            "id": "get-persist-failed",
            "method": "get_result",
            "params": {"taskId": "task-persist-failed"},
        }
    )
    assert status[0]["data"]["status"] == "FAILED"
    assert "resultRef" not in status[0]["data"]
