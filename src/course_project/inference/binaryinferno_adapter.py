"""Isolated adapter for the upstream BinaryInferno PRE research baseline.

BinaryInferno itself remains an external GPL-3.0-or-later experiment dependency.
This module invokes a separately checked-out upstream tree through a subprocess,
parses only its documented ``SPECSTART``/``SPECEND`` output, and converts that
output into project-native :class:`FieldCandidate` values.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from course_project.inference.netzob_adapter import PREBaselineResult
from course_project.io.records import ByteStream
from course_project.models import FieldCandidate, PacketCandidate

BINARYINFERNO_UPSTREAM_COMMIT = "cb42a63ada74737c10d01e2c22f4502ba3983976"
_DEFAULT_MAX_OUTPUT_BYTES = 4 * 1024 * 1024
_SAFE_DETECTOR_RE = re.compile(r"^[A-Za-z0-9_]+$")
_SPEC_LINE_RE = re.compile(
    r"^(?P<kind>[A-Za-z][A-Za-z0-9_]*)\s+(?P<token>\S+)\s+\((?P<description>.*)\)$"
)
_FIXED_TOKEN_RE = re.compile(r"^(?P<size>[1-9][0-9]*)V(?:_(?P<endian>BE|LE))?$")


class BinaryInfernoExecutionError(RuntimeError):
    """External BinaryInferno process failed or produced unsafe output."""


class BinaryInfernoOutputError(ValueError):
    """BinaryInferno output cannot be converted without inventing structure."""


@dataclass(frozen=True, slots=True)
class BinaryInfernoConfig:
    """Non-secret configuration for the external BinaryInferno checkout."""

    root: Path | None = None
    python_executable: str = sys.executable
    detectors: tuple[str, ...] = (
        "boundBE",
        "boundLE",
        "length",
        "length2BE",
        "length2LE",
        "length3BE",
        "length3LE",
        "length4BE",
        "length4LE",
    )
    timeout_seconds: float = 120.0
    max_output_bytes: int = _DEFAULT_MAX_OUTPUT_BYTES
    upstream_commit: str = BINARYINFERNO_UPSTREAM_COMMIT

    def __post_init__(self) -> None:
        if not self.python_executable.strip():
            raise ValueError("python_executable must be non-empty")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_output_bytes < 1024:
            raise ValueError("max_output_bytes must be at least 1024")
        if not self.upstream_commit.strip():
            raise ValueError("upstream_commit must be non-empty")
        if not self.detectors:
            raise ValueError("at least one BinaryInferno detector must be configured")
        invalid = [name for name in self.detectors if not _SAFE_DETECTOR_RE.fullmatch(name)]
        if invalid:
            raise ValueError(f"invalid BinaryInferno detector name(s): {invalid!r}")

    @classmethod
    def from_environment(cls) -> BinaryInfernoConfig:
        """Resolve an optional upstream checkout through ``BINARYINFERNO_ROOT``."""
        raw_root = os.environ.get("BINARYINFERNO_ROOT", "").strip()
        return cls(root=Path(raw_root) if raw_root else None)

    @property
    def script_path(self) -> Path | None:
        if self.root is None:
            return None
        return self.root / "binaryinferno" / "blackboard.py"


@runtime_checkable
class BinaryInfernoRunner(Protocol):
    """Injectable execution seam used by unit tests and the subprocess runner."""

    def infer(self, messages: tuple[bytes, ...], config: BinaryInfernoConfig) -> str:
        """Return raw BinaryInferno stdout for normalized messages."""
        ...


class SubprocessBinaryInfernoRunner:
    """Execute the pinned upstream CLI without a shell."""

    def infer(self, messages: tuple[bytes, ...], config: BinaryInfernoConfig) -> str:
        script = config.script_path
        if script is None or not script.is_file():
            raise BinaryInfernoExecutionError("BinaryInferno blackboard.py is unavailable")

        stdin_text = encode_binaryinferno_input(messages)
        command = [
            config.python_executable,
            script.name,
            "--sigmaonly",
            "--detectors",
            *config.detectors,
        ]
        try:
            completed = subprocess.run(  # noqa: S603 - fixed executable/args, shell=False
                command,
                cwd=script.parent,
                input=stdin_text,
                text=True,
                capture_output=True,
                timeout=config.timeout_seconds,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(
                f"BinaryInferno exceeded {config.timeout_seconds:g}s timeout"
            ) from exc
        except OSError as exc:
            raise BinaryInfernoExecutionError(
                f"failed to execute BinaryInferno: {type(exc).__name__}: {exc}"
            ) from exc

        if completed.returncode != 0:
            detail = completed.stderr.strip()[-1000:] or "no stderr"
            raise BinaryInfernoExecutionError(
                f"BinaryInferno exited {completed.returncode}: {detail}"
            )
        encoded = completed.stdout.encode("utf-8")
        if len(encoded) > config.max_output_bytes:
            raise BinaryInfernoExecutionError(
                "BinaryInferno stdout exceeded configured output-size bound"
            )
        return completed.stdout


def is_binaryinferno_available(config: BinaryInfernoConfig | None = None) -> bool:
    """Whether a configured external checkout exposes upstream ``blackboard.py``."""
    resolved = config or BinaryInfernoConfig.from_environment()
    script = resolved.script_path
    return script is not None and script.is_file()


def encode_binaryinferno_input(messages: tuple[bytes, ...]) -> str:
    """Encode messages exactly as the upstream stdin contract: one hex line each."""
    if not messages:
        raise ValueError("BinaryInferno requires at least one message")
    if any(not message for message in messages):
        raise ValueError("BinaryInferno messages must be non-empty")
    return "\n".join(message.hex() for message in messages) + "\n"


def run_binaryinferno_baseline(
    stream: ByteStream,
    packets: list[PacketCandidate],
    *,
    config: BinaryInfernoConfig | None = None,
    runner: BinaryInfernoRunner | None = None,
) -> PREBaselineResult:
    """Run BinaryInferno and convert the documented SPEC block fail-closed."""
    resolved = config or BinaryInfernoConfig.from_environment()
    if runner is None and not is_binaryinferno_available(resolved):
        return PREBaselineResult(
            backend="binaryinferno",
            status="unavailable",
            error_category="dependency_unavailable",
            detail=(
                "BinaryInferno checkout is unavailable; set BINARYINFERNO_ROOT to "
                f"upstream commit {resolved.upstream_commit} for experiment use"
            ),
        )

    messages = _slice_messages(stream, packets)
    if not messages:
        return PREBaselineResult(
            backend="binaryinferno",
            status="failed",
            error_category="invalid_input",
            detail="no packet with valid non-empty offsets inside the stream",
        )

    active_runner = runner or SubprocessBinaryInfernoRunner()
    try:
        stdout = active_runner.infer(messages, resolved)
    except TimeoutError as exc:
        return PREBaselineResult(
            backend="binaryinferno",
            status="failed",
            error_category="timeout",
            detail=str(exc),
        )
    except BinaryInfernoExecutionError as exc:
        return PREBaselineResult(
            backend="binaryinferno",
            status="failed",
            error_category="execution_failed",
            detail=str(exc),
        )

    try:
        candidates = parse_binaryinferno_spec(stdout, sample_count=len(messages))
    except BinaryInfernoOutputError as exc:
        return PREBaselineResult(
            backend="binaryinferno",
            status="failed",
            error_category="output_invalid",
            detail=str(exc),
        )
    if not candidates:
        return PREBaselineResult(
            backend="binaryinferno",
            status="failed",
            error_category="output_invalid",
            detail="BinaryInferno SPEC block contained no fields",
        )
    return PREBaselineResult(
        backend="binaryinferno",
        status="ok",
        field_candidates=tuple(candidates),
    )


def parse_binaryinferno_spec(stdout: str, *, sample_count: int) -> list[FieldCandidate]:
    """Parse exactly one documented ``SPECSTART``/``SPECEND`` block.

    Fixed-width fields advance the running offset. A variable/repetition field may
    be represented only when it is terminal; otherwise later offsets would be
    unknowable and the adapter fails closed instead of inventing them.
    """
    if sample_count < 1:
        raise ValueError("sample_count must be >= 1")
    lines = [line.strip() for line in stdout.splitlines()]
    starts = [index for index, line in enumerate(lines) if line == "SPECSTART"]
    ends = [index for index, line in enumerate(lines) if line == "SPECEND"]
    if len(starts) != 1 or len(ends) != 1 or ends[0] <= starts[0]:
        raise BinaryInfernoOutputError(
            "expected exactly one ordered SPECSTART/SPECEND block"
        )

    spec_lines = [line for line in lines[starts[0] + 1 : ends[0]] if line]
    candidates: list[FieldCandidate] = []
    offset = 0
    for field_index, line in enumerate(spec_lines):
        match = _SPEC_LINE_RE.fullmatch(line)
        if match is None:
            raise BinaryInfernoOutputError(f"unsupported BinaryInferno SPEC line: {line!r}")
        kind = match.group("kind")
        token = match.group("token")
        description = match.group("description").strip()

        fixed = _FIXED_TOKEN_RE.fullmatch(token)
        if fixed is not None:
            size: int | None = int(fixed.group("size"))
            endian = _normalize_endian(fixed.group("endian"), description)
        elif token.startswith("*"):
            if field_index != len(spec_lines) - 1:
                raise BinaryInfernoOutputError(
                    "non-terminal variable-width BinaryInferno field makes later offsets ambiguous"
                )
            size = None
            endian = _normalize_endian(None, description + " " + token)
        else:
            raise BinaryInfernoOutputError(
                f"unsupported BinaryInferno width token: {token!r}"
            )

        semantic_hint = _semantic_hint(kind, description)
        candidates.append(
            FieldCandidate(
                candidate_id=(
                    f"binaryinferno-f{field_index}-{offset}-"
                    f"{size if size is not None else 'v'}"
                ),
                family_id=None,
                offset=offset,
                size=size,
                candidate_types=(semantic_hint,),
                endian=endian,
                score=0.5,
                attributes={
                    "backend": "binaryinferno",
                    "field_index": field_index,
                    "support": sample_count,
                    "sample_count": sample_count,
                    "spec_kind": kind,
                    "spec_token": token,
                    "upstream_description": description,
                    "upstream_commit": BINARYINFERNO_UPSTREAM_COMMIT,
                    "baseline_score_available": False,
                    "verification_status": "not_verified",
                },
            )
        )
        if size is not None:
            offset += size
    return candidates


def _semantic_hint(kind: str, description: str) -> str:
    combined = f"{kind} {description}".lower()
    if kind.lower() == "length" or " message length" in combined:
        return "length"
    if "span seconds" in combined or "timestamp" in combined:
        return "timestamp"
    if "sequence" in combined or kind.lower().startswith("seq"):
        return "sequence"
    if "checksum" in combined or "crc" in combined:
        return "checksum"
    if "constant" in combined:
        return "constant"
    return "unknown"


def _normalize_endian(token_endian: str | None, text: str) -> str | None:
    if token_endian == "BE":
        return "big"
    if token_endian == "LE":
        return "little"
    upper = text.upper()
    if "_BE" in upper or upper.startswith("BE "):
        return "big"
    if "_LE" in upper or upper.startswith("LE "):
        return "little"
    return None


def _slice_messages(stream: ByteStream, packets: list[PacketCandidate]) -> tuple[bytes, ...]:
    base = stream.offset_base
    messages: list[bytes] = []
    for packet in packets:
        start = packet.start_offset - base
        end = packet.end_offset - base
        if 0 <= start < end <= len(stream.data):
            messages.append(stream.data[start:end])
    return tuple(messages)
