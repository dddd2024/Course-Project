from __future__ import annotations

import base64
import hashlib
import json
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Any, Protocol

from course_project.models import AnalysisResult, InputMetadata
from course_project.sidecar.serialization import analysis_result_to_dict

PROTOCOL_VERSION = 1
MAX_READ_RANGE = 1_048_576
SIDE_CAR_METHODS = {
    "register_input",
    "inspect_file",
    "analyze",
    "cancel_task",
    "get_result",
    "read_range",
}
ANALYSIS_STAGES = {
    "inspect",
    "features",
    "boundary",
    "inference",
    "evidence",
    "llm",
    "verification",
    "behavior",
    "export",
}
ANALYSIS_MODES = {"baseline", "evidencegraph"}
OPTIONAL_DEPENDENCY_POLICIES = {"degrade", "fail"}
_INPUT_KINDS = {"dat", "bin", "pcap", "pcapng", "unknown"}
_SUFFIX_TO_KIND = {
    ".dat": "dat",
    ".bin": "bin",
    ".pcap": "pcap",
    ".pcapng": "pcapng",
}
_SAFE_TASK_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class SidecarError(Exception):
    """Machine-readable sidecar failure that maps to the public error envelope."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


@dataclass(slots=True)
class RegisteredInput:
    metadata: InputMetadata
    path: Path
    source_name: str


@dataclass(slots=True)
class TaskRecord:
    task_id: str
    input_ref: str
    status: str
    result_ref: str | None = None
    config: dict[str, Any] = field(default_factory=dict)


class AnalysisBackend(Protocol):
    """Narrow injection boundary for the Track D/C analysis pipeline."""

    def analyze(
        self,
        *,
        task_id: str,
        input_metadata: InputMetadata,
        input_path: Path,
        config: Mapping[str, Any],
    ) -> AnalysisResult: ...


class MetadataOnlyBackend:
    """Safe default until the real analysis orchestrator is connected."""

    def analyze(
        self,
        *,
        task_id: str,
        input_metadata: InputMetadata,
        input_path: Path,
        config: Mapping[str, Any],
    ) -> AnalysisResult:
        del input_path
        limitation = (
            "No Track D/C analysis backend is connected; this result validates only the Track A "
            "sidecar/integration contract."
        )
        return AnalysisResult(
            task_id=task_id,
            status="partial",
            input_id=input_metadata.input_id,
            metrics={"inputSizeBytes": input_metadata.size_bytes, "mode": config["mode"]},
            limitations=(limitation,),
        )


class InputRegistry:
    def __init__(self, allowed_roots: tuple[Path, ...] | None = None) -> None:
        self._records: dict[str, RegisteredInput] = {}
        self._allowed_roots = (
            tuple(root.expanduser().resolve() for root in allowed_roots)
            if allowed_roots is not None
            else None
        )
        self._lock = RLock()

    def register(self, source_ref: str, kind_hint: str | None = None) -> RegisteredInput:
        path = Path(source_ref).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise SidecarError(
                "invalid_input",
                "sourceRef must point to an existing regular file",
                details={"sourceName": path.name or source_ref},
            )
        if self._allowed_roots is not None and not any(
            path.is_relative_to(root) for root in self._allowed_roots
        ):
            raise SidecarError(
                "invalid_input",
                "sourceRef is outside the configured allowed roots",
                details={"sourceName": path.name},
            )

        try:
            sha256 = _sha256_file(path)
            size_bytes = path.stat().st_size
        except OSError as exc:
            raise SidecarError(
                "invalid_input",
                "sourceRef could not be read during registration",
                details={"sourceName": path.name},
            ) from exc

        input_ref = f"input-{sha256[:16]}"
        metadata = InputMetadata(
            input_id=input_ref,
            kind=_resolve_kind(path, kind_hint),
            size_bytes=size_bytes,
            sha256=sha256,
            metadata={"sourceName": path.name},
        )
        record = RegisteredInput(metadata=metadata, path=path, source_name=path.name)
        with self._lock:
            self._records[input_ref] = record
        return record

    def get(self, input_ref: str) -> RegisteredInput:
        with self._lock:
            record = self._records.get(input_ref)
        if record is None:
            raise SidecarError(
                "invalid_input",
                "unknown inputRef",
                details={"inputRef": input_ref},
            )
        self._require_source_available(record)
        return record

    def _require_source_available(self, record: RegisteredInput) -> None:
        try:
            current = record.path.stat()
        except OSError as exc:
            raise SidecarError(
                "invalid_input",
                "registered source file is no longer available",
                details={
                    "inputRef": record.metadata.input_id,
                    "sourceName": record.source_name,
                },
            ) from exc
        if not stat.S_ISREG(current.st_mode):
            raise SidecarError(
                "invalid_input",
                "registered source file is no longer available",
                details={
                    "inputRef": record.metadata.input_id,
                    "sourceName": record.source_name,
                },
            )
        if current.st_size != record.metadata.size_bytes:
            raise SidecarError(
                "invalid_input",
                "registered source file size changed since registration",
                details={
                    "inputRef": record.metadata.input_id,
                    "sourceName": record.source_name,
                    "expectedSizeBytes": record.metadata.size_bytes,
                    "actualSizeBytes": current.st_size,
                },
            )

    def read_range(self, input_ref: str, offset: int, length: int) -> dict[str, Any]:
        record = self.get(input_ref)
        try:
            with record.path.open("rb") as handle:
                handle.seek(offset)
                chunk = handle.read(length)
        except OSError as exc:
            raise SidecarError(
                "invalid_input",
                "registered source file is no longer readable",
                details={"inputRef": input_ref, "sourceName": record.source_name},
            ) from exc
        return {
            "inputRef": input_ref,
            "offset": offset,
            "requestedLength": length,
            "actualLength": len(chunk),
            "encoding": "base64",
            "bytes": base64.b64encode(chunk).decode("ascii"),
            "eof": offset + len(chunk) >= record.metadata.size_bytes,
        }


class ResultStore:
    """Own controlled result-relative refs exposed to the desktop."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def write_analysis_result(self, result: AnalysisResult) -> str:
        _validate_task_id(result.task_id)
        ref = f"tasks/{result.task_id}/analysis-result.json"
        result.result_ref = ref
        payload = analysis_result_to_dict(result)
        target = self.root / ref
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise SidecarError(
                "sidecar_failed",
                "failed to persist analysis result",
                details={"taskId": result.task_id},
            ) from exc
        return ref

    def resolve(self, ref: str) -> Path:
        candidate = (self.root / ref).resolve()
        if not candidate.is_relative_to(self.root):
            raise SidecarError("invalid_input", "resultRef escapes the controlled result root")
        return candidate


class SidecarRuntime:
    """In-process implementation of the frozen Sidecar v1 task protocol."""

    def __init__(
        self,
        *,
        state_dir: Path,
        backend: AnalysisBackend | None = None,
        allowed_roots: tuple[Path, ...] | None = None,
    ) -> None:
        self.inputs = InputRegistry(allowed_roots=allowed_roots)
        self.results = ResultStore(state_dir)
        self.backend = backend or MetadataOnlyBackend()
        self._tasks: dict[str, TaskRecord] = {}
        self._lock = RLock()

    def handle(self, message: Mapping[str, Any]) -> list[dict[str, Any]]:
        message_id = str(message.get("id", "invalid-message"))
        try:
            request = _validate_request(message)
            method = request["method"]
            params = request["params"]
            if method == "register_input":
                return [self._register_input(message_id, params)]
            if method == "inspect_file":
                return [self._inspect_file(message_id, params)]
            if method == "read_range":
                return [self._read_range(message_id, params)]
            if method == "analyze":
                return self._analyze(message_id, params)
            if method == "get_result":
                return self._get_result(message_id, params)
            if method == "cancel_task":
                return [self._cancel_task(message_id, params)]
            raise SidecarError("sidecar_failed", "unreachable sidecar method dispatch")
        except SidecarError as exc:
            return [_error_message(message_id, exc)]

    def _register_input(self, message_id: str, params: Mapping[str, Any]) -> dict[str, Any]:
        record = self.inputs.register(params["sourceRef"], params.get("kindHint"))
        return _status_message(message_id, "registered", _input_metadata_payload(record))

    def _inspect_file(self, message_id: str, params: Mapping[str, Any]) -> dict[str, Any]:
        record = self.inputs.get(params["inputRef"])
        return _status_message(message_id, "inspected", _input_metadata_payload(record))

    def _read_range(self, message_id: str, params: Mapping[str, Any]) -> dict[str, Any]:
        data = self.inputs.read_range(params["inputRef"], params["offset"], params["length"])
        return _status_message(message_id, "range", data)

    def _analyze(self, task_id: str, params: Mapping[str, Any]) -> list[dict[str, Any]]:
        _validate_task_id(task_id)
        input_ref = params["inputRef"]
        config = dict(params)

        with self._lock:
            existing = self._tasks.get(task_id)
            if existing is not None:
                if existing.input_ref != input_ref or existing.config != config:
                    raise SidecarError(
                        "invalid_input",
                        "task id is already bound to a different analyze request",
                        details={"taskId": task_id},
                    )
                return self._existing_task_messages(task_id, existing)

        record = self.inputs.get(input_ref)

        with self._lock:
            existing = self._tasks.get(task_id)
            if existing is not None:
                if existing.input_ref != input_ref or existing.config != config:
                    raise SidecarError(
                        "invalid_input",
                        "task id is already bound to a different analyze request",
                        details={"taskId": task_id},
                    )
                return self._existing_task_messages(task_id, existing)
            task = TaskRecord(task_id=task_id, input_ref=input_ref, status="RUNNING", config=config)
            self._tasks[task_id] = task

        messages = [
            _status_message(task_id, "task_status", _task_payload(task)),
            _progress_message(task_id, "analysis", 0.0),
        ]
        try:
            result = self.backend.analyze(
                task_id=task_id,
                input_metadata=record.metadata,
                input_path=record.path,
                config=config,
            )
        except SidecarError:
            with self._lock:
                task.status = "FAILED"
            raise
        except Exception as exc:
            with self._lock:
                task.status = "FAILED"
            raise SidecarError(
                "inference_failed",
                "analysis backend failed",
                details={"exceptionType": type(exc).__name__},
            ) from exc

        try:
            _validate_backend_result(result, task_id=task_id, input_ref=input_ref)
            result.input_id = input_ref

            with self._lock:
                cancelled = task.status == "CANCELLED"
            if cancelled:
                result = AnalysisResult(
                    task_id=task_id,
                    status="cancelled",
                    input_id=input_ref,
                    limitations=("Task was cancelled before its result was published.",),
                )

            ref = self.results.write_analysis_result(result)
        except SidecarError:
            with self._lock:
                task.result_ref = None
                task.status = "FAILED"
            raise

        with self._lock:
            task.result_ref = ref
            task.status = result.status.upper()

        messages.extend(
            [
                _progress_message(task_id, "analysis", 1.0),
                _status_message(task_id, "task_status", _task_payload(task)),
                _result_message(task_id, ref),
            ]
        )
        return messages

    def _existing_task_messages(self, message_id: str, task: TaskRecord) -> list[dict[str, Any]]:
        messages = [_status_message(message_id, "task_status", _task_payload(task))]
        if task.result_ref is not None:
            messages.append(_result_message(message_id, task.result_ref))
        return messages

    def _get_result(self, message_id: str, params: Mapping[str, Any]) -> list[dict[str, Any]]:
        task_id = params["taskId"]
        with self._lock:
            task = self._tasks.get(task_id)
        if task is None:
            raise SidecarError("invalid_input", "unknown taskId", details={"taskId": task_id})
        if task.result_ref is None:
            return [_status_message(message_id, "task_status", _task_payload(task))]
        return [_result_message(message_id, task.result_ref)]

    def _cancel_task(self, message_id: str, params: Mapping[str, Any]) -> dict[str, Any]:
        task_id = params["taskId"]
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise SidecarError("invalid_input", "unknown taskId", details={"taskId": task_id})
            if task.status in {"QUEUED", "RUNNING"}:
                task.status = "CANCELLED"
        return _status_message(message_id, "task_status", _task_payload(task))


def _validate_backend_result(result: AnalysisResult, *, task_id: str, input_ref: str) -> None:
    if result.task_id != task_id:
        raise SidecarError(
            "sidecar_failed",
            "analysis backend returned a mismatched task id",
            details={"expectedTaskId": task_id, "actualTaskId": result.task_id},
        )
    if result.input_id not in {None, input_ref}:
        raise SidecarError(
            "sidecar_failed",
            "analysis backend returned a mismatched input id",
            details={"expectedInputRef": input_ref, "actualInputId": result.input_id},
        )


def _validate_request(message: Mapping[str, Any]) -> dict[str, Any]:
    if message.get("protocolVersion") != PROTOCOL_VERSION:
        raise SidecarError(
            "contract_version_mismatch",
            "unsupported sidecar protocolVersion",
            details={"expected": PROTOCOL_VERSION, "actual": message.get("protocolVersion")},
        )
    message_id = message.get("id")
    if not isinstance(message_id, str) or not message_id:
        raise SidecarError("invalid_input", "sidecar request id must be a non-empty string")
    method = message.get("method")
    if method not in SIDE_CAR_METHODS:
        raise SidecarError("invalid_input", "unknown sidecar method", details={"method": method})
    params = message.get("params")
    if not isinstance(params, Mapping):
        raise SidecarError("invalid_input", "sidecar params must be an object")

    validators = {
        "register_input": _validate_register_params,
        "inspect_file": _validate_input_ref_params,
        "analyze": _validate_analyze_params,
        "cancel_task": _validate_task_params,
        "get_result": _validate_task_params,
        "read_range": _validate_read_range_params,
    }
    validators[method](params)
    return {"method": method, "params": dict(params)}


def _require_exact_keys(
    params: Mapping[str, Any],
    *,
    required: set[str],
    optional: set[str] | None = None,
) -> None:
    optional = optional or set()
    missing = required - set(params)
    unknown = set(params) - required - optional
    if missing:
        raise SidecarError(
            "invalid_input",
            "missing required sidecar parameters",
            details={"missing": sorted(missing)},
        )
    if unknown:
        raise SidecarError(
            "invalid_input",
            "unknown sidecar parameters",
            details={"unknown": sorted(unknown)},
        )


def _validate_register_params(params: Mapping[str, Any]) -> None:
    _require_exact_keys(params, required={"sourceRef"}, optional={"kindHint"})
    if not isinstance(params["sourceRef"], str) or not params["sourceRef"]:
        raise SidecarError("invalid_input", "sourceRef must be a non-empty string")
    kind_hint = params.get("kindHint")
    if kind_hint is not None and kind_hint not in _INPUT_KINDS:
        raise SidecarError("invalid_input", "unsupported kindHint", details={"kindHint": kind_hint})


def _validate_input_ref_params(params: Mapping[str, Any]) -> None:
    _require_exact_keys(params, required={"inputRef"})
    if not isinstance(params["inputRef"], str) or not params["inputRef"]:
        raise SidecarError("invalid_input", "inputRef must be a non-empty string")


def _validate_task_params(params: Mapping[str, Any]) -> None:
    _require_exact_keys(params, required={"taskId"})
    if not isinstance(params["taskId"], str) or not params["taskId"]:
        raise SidecarError("invalid_input", "taskId must be a non-empty string")


def _validate_read_range_params(params: Mapping[str, Any]) -> None:
    _require_exact_keys(params, required={"inputRef", "offset", "length"})
    if not isinstance(params["inputRef"], str) or not params["inputRef"]:
        raise SidecarError("invalid_input", "inputRef must be a non-empty string")
    offset = params["offset"]
    length = params["length"]
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise SidecarError("invalid_input", "offset must be a non-negative integer")
    if isinstance(length, bool) or not isinstance(length, int) or not 1 <= length <= MAX_READ_RANGE:
        raise SidecarError(
            "invalid_input",
            f"length must be an integer within [1, {MAX_READ_RANGE}]",
        )


def _validate_analyze_params(params: Mapping[str, Any]) -> None:
    optional = {
        "stages",
        "llmEnabled",
        "verificationEnabled",
        "behaviorEnabled",
        "timeoutSeconds",
        "optionalDependencyPolicy",
    }
    _require_exact_keys(params, required={"inputRef", "mode"}, optional=optional)
    if not isinstance(params["inputRef"], str) or not params["inputRef"]:
        raise SidecarError("invalid_input", "inputRef must be a non-empty string")
    if params["mode"] not in ANALYSIS_MODES:
        raise SidecarError("invalid_input", "unsupported analysis mode")

    stages = params.get("stages")
    if stages is not None:
        if not isinstance(stages, list) or any(stage not in ANALYSIS_STAGES for stage in stages):
            raise SidecarError("invalid_input", "stages contains an unsupported analysis stage")
        if len(stages) != len(set(stages)):
            raise SidecarError("invalid_input", "stages must not contain duplicates")

    for key in ("llmEnabled", "verificationEnabled", "behaviorEnabled"):
        if key in params and not isinstance(params[key], bool):
            raise SidecarError("invalid_input", f"{key} must be boolean")

    if "timeoutSeconds" in params:
        timeout = params["timeoutSeconds"]
        if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 86400:
            raise SidecarError("invalid_input", "timeoutSeconds must be within [1, 86400]")

    policy = params.get("optionalDependencyPolicy")
    if policy is not None and policy not in OPTIONAL_DEPENDENCY_POLICIES:
        raise SidecarError("invalid_input", "unsupported optionalDependencyPolicy")


def _input_metadata_payload(record: RegisteredInput) -> dict[str, Any]:
    metadata = record.metadata
    if metadata.sha256 is None:
        raise SidecarError("sidecar_failed", "registered inputs must have a SHA-256 digest")
    return {
        "inputRef": metadata.input_id,
        "kind": metadata.kind if metadata.kind != "synthetic" else "unknown",
        "sizeBytes": metadata.size_bytes,
        "sha256": metadata.sha256,
        "sourceName": record.source_name,
        "directionAvailable": metadata.direction_available,
        "timestampAvailable": metadata.timestamp_available,
    }


def _task_payload(task: TaskRecord) -> dict[str, Any]:
    payload: dict[str, Any] = {"taskId": task.task_id, "status": task.status}
    if task.result_ref is not None:
        payload["resultRef"] = task.result_ref
    return payload


def _status_message(message_id: str, stage: str, data: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "id": message_id,
        "event": "status",
        "stage": stage,
        "data": dict(data),
    }


def _progress_message(message_id: str, stage: str, progress: float) -> dict[str, Any]:
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "id": message_id,
        "event": "progress",
        "stage": stage,
        "progress": progress,
    }


def _result_message(message_id: str, result_ref: str) -> dict[str, Any]:
    return {"protocolVersion": PROTOCOL_VERSION, "id": message_id, "resultRef": result_ref}


def _error_message(message_id: str, error: SidecarError) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "protocolVersion": PROTOCOL_VERSION,
        "id": message_id,
        "error": {"code": error.code, "message": error.message},
    }
    if error.details:
        payload["error"]["details"] = error.details
    return payload


def _resolve_kind(path: Path, kind_hint: str | None) -> str:
    if kind_hint in {"dat", "bin", "pcap", "pcapng"}:
        return kind_hint
    return _SUFFIX_TO_KIND.get(path.suffix.lower(), "unknown")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_task_id(task_id: str) -> None:
    if not _SAFE_TASK_ID.fullmatch(task_id):
        raise SidecarError(
            "invalid_input",
            "task id must use 1-128 ASCII letters, digits, '.', '_' or '-'",
            details={"taskId": task_id},
        )
