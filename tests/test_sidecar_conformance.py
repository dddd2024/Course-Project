from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from io import StringIO
from pathlib import Path
from threading import Event, Thread
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from course_project.models import AnalysisResult, InputMetadata
from course_project.sidecar.cli import serve_stream
from course_project.sidecar.runtime import MAX_READ_RANGE, SidecarRuntime

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"


def _schema() -> dict[str, Any]:
    return json.loads((CONTRACTS / "sidecar-message.schema.json").read_text(encoding="utf-8"))


def _assert_valid(messages: list[dict[str, Any]]) -> None:
    validator = Draft202012Validator(_schema())
    for message in messages:
        errors = list(validator.iter_errors(message))
        assert not errors, "; ".join(error.message for error in errors)


def _register(runtime: SidecarRuntime, sample: Path, *, request_id: str = "register-1") -> str:
    messages = runtime.handle(
        {
            "protocolVersion": 1,
            "id": request_id,
            "method": "register_input",
            "params": {"sourceRef": str(sample)},
        }
    )
    _assert_valid(messages)
    assert "error" not in messages[0]
    return messages[0]["data"]["inputRef"]


class BlockingBackend:
    def __init__(self) -> None:
        self.started = Event()
        self.release = Event()

    def analyze(
        self,
        *,
        task_id: str,
        input_metadata: InputMetadata,
        input_path: Path,
        config: Mapping[str, Any],
    ) -> AnalysisResult:
        del input_path, config
        self.started.set()
        if not self.release.wait(timeout=5):
            raise RuntimeError("blocking backend was not released")
        return AnalysisResult(
            task_id=task_id,
            status="completed",
            input_id=input_metadata.input_id,
        )


class FailingBackend:
    def analyze(
        self,
        *,
        task_id: str,
        input_metadata: InputMetadata,
        input_path: Path,
        config: Mapping[str, Any],
    ) -> AnalysisResult:
        del task_id, input_metadata, input_path, config
        raise RuntimeError("synthetic backend failure")


def test_cancel_running_task_is_published_as_cancelled(tmp_path: Path) -> None:
    sample = tmp_path / "sample.dat"
    sample.write_bytes(b"abcdefgh")
    backend = BlockingBackend()
    runtime = SidecarRuntime(state_dir=tmp_path / "state", backend=backend)
    input_ref = _register(runtime, sample)

    result_holder: list[list[dict[str, Any]]] = []

    def run_analysis() -> None:
        result_holder.append(
            runtime.handle(
                {
                    "protocolVersion": 1,
                    "id": "task-active",
                    "method": "analyze",
                    "params": {"inputRef": input_ref, "mode": "baseline"},
                }
            )
        )

    worker = Thread(target=run_analysis)
    worker.start()
    assert backend.started.wait(timeout=5)

    cancelled = runtime.handle(
        {
            "protocolVersion": 1,
            "id": "cancel-1",
            "method": "cancel_task",
            "params": {"taskId": "task-active"},
        }
    )
    _assert_valid(cancelled)
    assert cancelled[0]["data"]["status"] == "CANCELLED"

    backend.release.set()
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert len(result_holder) == 1
    analysis_messages = result_holder[0]
    _assert_valid(analysis_messages)
    assert analysis_messages[-2]["data"]["status"] == "CANCELLED"

    result_ref = analysis_messages[-1]["resultRef"]
    payload = json.loads((tmp_path / "state" / result_ref).read_text(encoding="utf-8"))
    assert payload["status"] == "CANCELLED"
    assert payload["limitations"]

    fetched = runtime.handle(
        {
            "protocolVersion": 1,
            "id": "get-cancelled",
            "method": "get_result",
            "params": {"taskId": "task-active"},
        }
    )
    _assert_valid(fetched)
    assert fetched[0]["resultRef"] == result_ref


def test_cancel_completed_or_partial_task_is_idempotent_noop(tmp_path: Path) -> None:
    sample = tmp_path / "sample.dat"
    sample.write_bytes(b"1234")
    runtime = SidecarRuntime(state_dir=tmp_path / "state")
    input_ref = _register(runtime, sample)

    analyzed = runtime.handle(
        {
            "protocolVersion": 1,
            "id": "task-finished",
            "method": "analyze",
            "params": {"inputRef": input_ref, "mode": "baseline"},
        }
    )
    assert analyzed[-2]["data"]["status"] == "PARTIAL"
    result_ref = analyzed[-1]["resultRef"]

    for request_id in ("cancel-finished-1", "cancel-finished-2"):
        messages = runtime.handle(
            {
                "protocolVersion": 1,
                "id": request_id,
                "method": "cancel_task",
                "params": {"taskId": "task-finished"},
            }
        )
        _assert_valid(messages)
        assert messages[0]["data"]["status"] == "PARTIAL"
        assert messages[0]["data"]["resultRef"] == result_ref


def test_backend_failure_is_machine_readable_and_task_remains_failed(tmp_path: Path) -> None:
    sample = tmp_path / "sample.bin"
    sample.write_bytes(b"failure")
    runtime = SidecarRuntime(state_dir=tmp_path / "state", backend=FailingBackend())
    input_ref = _register(runtime, sample)

    failed = runtime.handle(
        {
            "protocolVersion": 1,
            "id": "task-failed",
            "method": "analyze",
            "params": {"inputRef": input_ref, "mode": "baseline"},
        }
    )
    _assert_valid(failed)
    assert failed == [
        {
            "protocolVersion": 1,
            "id": "task-failed",
            "error": {
                "code": "inference_failed",
                "message": "analysis backend failed",
                "details": {"exceptionType": "RuntimeError"},
            },
        }
    ]

    status = runtime.handle(
        {
            "protocolVersion": 1,
            "id": "get-failed",
            "method": "get_result",
            "params": {"taskId": "task-failed"},
        }
    )
    _assert_valid(status)
    assert status[0]["data"]["status"] == "FAILED"
    assert "resultRef" not in status[0]["data"]


@pytest.mark.parametrize(
    ("offset", "length"),
    [
        (-1, 1),
        (True, 1),
        (0, 0),
        (0, -1),
        (0, True),
        (0, MAX_READ_RANGE + 1),
    ],
)
def test_read_range_rejects_invalid_bounds(
    tmp_path: Path,
    offset: int,
    length: int,
) -> None:
    sample = tmp_path / "sample.dat"
    sample.write_bytes(bytes(range(8)))
    runtime = SidecarRuntime(state_dir=tmp_path / "state")
    input_ref = _register(runtime, sample)

    messages = runtime.handle(
        {
            "protocolVersion": 1,
            "id": "bad-range",
            "method": "read_range",
            "params": {"inputRef": input_ref, "offset": offset, "length": length},
        }
    )
    _assert_valid(messages)
    assert messages[0]["error"]["code"] == "invalid_input"


def test_read_range_past_eof_is_bounded_and_explicit(tmp_path: Path) -> None:
    sample = tmp_path / "sample.dat"
    sample.write_bytes(b"abcd")
    runtime = SidecarRuntime(state_dir=tmp_path / "state")
    input_ref = _register(runtime, sample)

    messages = runtime.handle(
        {
            "protocolVersion": 1,
            "id": "range-eof",
            "method": "read_range",
            "params": {"inputRef": input_ref, "offset": 99, "length": 16},
        }
    )
    _assert_valid(messages)
    data = messages[0]["data"]
    assert data["requestedLength"] == 16
    assert data["actualLength"] == 0
    assert base64.b64decode(data["bytes"]) == b""
    assert data["eof"] is True


def test_allowed_roots_reject_outside_input(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside.dat"
    outside.write_bytes(b"outside")
    runtime = SidecarRuntime(state_dir=tmp_path / "state", allowed_roots=(allowed,))

    messages = runtime.handle(
        {
            "protocolVersion": 1,
            "id": "register-outside",
            "method": "register_input",
            "params": {"sourceRef": str(outside)},
        }
    )
    _assert_valid(messages)
    assert messages[0]["error"]["code"] == "invalid_input"
    assert "outside the configured allowed roots" in messages[0]["error"]["message"]


def test_registered_source_deletion_fails_closed(tmp_path: Path) -> None:
    sample = tmp_path / "sample.dat"
    sample.write_bytes(b"mutable")
    runtime = SidecarRuntime(state_dir=tmp_path / "state")
    input_ref = _register(runtime, sample)
    sample.unlink()

    requests = [
        {
            "protocolVersion": 1,
            "id": "inspect-missing",
            "method": "inspect_file",
            "params": {"inputRef": input_ref},
        },
        {
            "protocolVersion": 1,
            "id": "range-missing",
            "method": "read_range",
            "params": {"inputRef": input_ref, "offset": 0, "length": 1},
        },
        {
            "protocolVersion": 1,
            "id": "analyze-missing",
            "method": "analyze",
            "params": {"inputRef": input_ref, "mode": "baseline"},
        },
    ]
    for request in requests:
        messages = runtime.handle(request)
        _assert_valid(messages)
        assert messages[0]["error"]["code"] == "invalid_input"
        assert "no longer available" in messages[0]["error"]["message"]


def test_registered_source_size_change_fails_closed(tmp_path: Path) -> None:
    sample = tmp_path / "sample.dat"
    sample.write_bytes(b"1234")
    runtime = SidecarRuntime(state_dir=tmp_path / "state")
    input_ref = _register(runtime, sample)
    sample.write_bytes(b"12345678")

    messages = runtime.handle(
        {
            "protocolVersion": 1,
            "id": "inspect-changed",
            "method": "inspect_file",
            "params": {"inputRef": input_ref},
        }
    )
    _assert_valid(messages)
    assert messages[0]["error"]["code"] == "invalid_input"
    assert "size changed since registration" in messages[0]["error"]["message"]


def test_unknown_method_task_and_extra_params_fail_closed(tmp_path: Path) -> None:
    runtime = SidecarRuntime(state_dir=tmp_path / "state")
    cases = [
        {
            "protocolVersion": 1,
            "id": "unknown-method",
            "method": "run_analysis",
            "params": {},
        },
        {
            "protocolVersion": 1,
            "id": "unknown-task",
            "method": "get_result",
            "params": {"taskId": "does-not-exist"},
        },
        {
            "protocolVersion": 1,
            "id": "extra-param",
            "method": "get_result",
            "params": {"taskId": "x", "unexpected": True},
        },
    ]
    for request in cases:
        messages = runtime.handle(request)
        _assert_valid(messages)
        assert messages[0]["error"]["code"] == "invalid_input"


def test_jsonl_server_recovers_after_malformed_line(tmp_path: Path) -> None:
    sample = tmp_path / "sample.dat"
    sample.write_bytes(b"stream")
    runtime = SidecarRuntime(state_dir=tmp_path / "state", allowed_roots=(tmp_path,))
    valid = json.dumps(
        {
            "protocolVersion": 1,
            "id": "register-after-bad-line",
            "method": "register_input",
            "params": {"sourceRef": str(sample)},
        }
    )
    instream = StringIO("{not-json}\n" + valid + "\n")
    outstream = StringIO()
    errstream = StringIO()

    assert serve_stream(runtime, instream, outstream, errstream) == 0
    responses = [json.loads(line) for line in outstream.getvalue().splitlines()]
    assert len(responses) == 2
    _assert_valid(responses)
    assert responses[0]["id"] == "invalid-line-1"
    assert responses[0]["error"]["code"] == "invalid_input"
    assert responses[1]["id"] == "register-after-bad-line"
    assert responses[1]["stage"] == "registered"
    assert "sidecar input error on line 1" in errstream.getvalue()
