"""Deterministic length and sequence checks for protocol hypotheses."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from itertools import pairwise
from typing import Literal

from course_project.models import (
    DecisionStatus,
    ExecutableCheck,
    ProtocolHypothesis,
    VerificationResult,
)

BytesLike = bytes | bytearray | memoryview


class VerificationError(ValueError):
    """Raised when a hypothesis cannot be translated into a safe check."""


def verify_length(
    hypothesis: ProtocolHypothesis,
    messages: Iterable[BytesLike],
    *,
    minimum_samples: int = 3,
    accept_threshold: float = 0.95,
    reject_threshold: float = 0.5,
) -> ExecutableCheck:
    """Verify an integer length interpretation over all eligible messages.

    The endian parameter is required. The target parameter supports
    full_message, payload, and region. Optional parameters specify header
    size, fixed region bounds, and a constant adjustment.
    """

    _validate_hypothesis_field(hypothesis)
    endian = _endian(hypothesis)
    target = hypothesis.parameters.get("target", "full_message")
    if target not in {"full_message", "payload", "region"}:
        raise VerificationError(f"unsupported length target: {target!r}")

    header_size = _non_negative_int(hypothesis.parameters.get("header_size", 0), "header_size")
    adjustment = _int_parameter(hypothesis.parameters.get("adjustment", 0), "adjustment")
    region_start = _non_negative_int(
        hypothesis.parameters.get("region_start", 0), "region_start"
    )
    region_end_raw = hypothesis.parameters.get("region_end")
    if target == "region" and region_end_raw is None:
        raise VerificationError("region target requires region_end")
    region_end = (
        _non_negative_int(region_end_raw, "region_end")
        if region_end_raw is not None
        else None
    )
    if region_end is not None and region_end < region_start:
        raise VerificationError("region_end must not precede region_start")

    support_count = 0
    violation_count = 0
    for message in _normalized_messages(messages):
        value = _read_unsigned(message, hypothesis.offset, hypothesis.size, endian)
        if value is None:
            continue
        if target == "full_message":
            expected = len(message)
        elif target == "payload":
            if header_size > len(message):
                continue
            expected = len(message) - header_size
        else:
            assert region_end is not None
            if region_end > len(message):
                continue
            expected = region_end - region_start

        if value + adjustment == expected:
            support_count += 1
        else:
            violation_count += 1

    sample_count = support_count + violation_count
    score = _support_ratio(support_count, sample_count)
    status = _decision(
        score,
        sample_count,
        minimum_samples=minimum_samples,
        accept_threshold=accept_threshold,
        reject_threshold=reject_threshold,
    )
    return ExecutableCheck(
        check_id=f"check:{hypothesis.hypothesis_id}:length",
        hypothesis_id=hypothesis.hypothesis_id,
        check_type="length",
        sample_count=sample_count,
        support_count=support_count,
        violation_count=violation_count,
        score=score,
        result=status,
        evidence_ids=hypothesis.supporting_evidence_ids,
    )


def verify_sequence(
    hypothesis: ProtocolHypothesis,
    messages: Sequence[BytesLike],
    *,
    session_ids: Sequence[str] | None = None,
    minimum_samples: int = 3,
    accept_threshold: float = 0.9,
    reject_threshold: float = 0.5,
) -> ExecutableCheck:
    """Verify ordered sequence values, optionally within separate sessions.

    Modes include strict, increment, monotonic_missing, and wraparound.
    The sample count is the number of eligible within-session transitions.
    """

    _validate_hypothesis_field(hypothesis)
    endian = _endian(hypothesis)
    mode = hypothesis.parameters.get("mode", "strict")
    if mode not in {"strict", "increment", "monotonic_missing", "wraparound"}:
        raise VerificationError(f"unsupported sequence mode: {mode!r}")

    step = _positive_int(hypothesis.parameters.get("step", 1), "step")
    max_gap_raw = hypothesis.parameters.get("max_gap")
    if mode == "wraparound" and max_gap_raw is None:
        max_gap_raw = step
    max_gap = (
        _positive_int(max_gap_raw, "max_gap") if max_gap_raw is not None else None
    )
    normalized = _normalized_messages(messages)
    if session_ids is not None and len(session_ids) != len(normalized):
        raise VerificationError("session_ids must match the message count")

    sessions: dict[str, list[int]] = {}
    for index, message in enumerate(normalized):
        value = _read_unsigned(message, hypothesis.offset, hypothesis.size, endian)
        if value is None:
            continue
        session_id = session_ids[index] if session_ids is not None else "default"
        sessions.setdefault(session_id, []).append(value)

    modulus = 1 << (8 * _field_size(hypothesis))
    support_count = 0
    violation_count = 0
    for values in sessions.values():
        for previous, current in pairwise(values):
            if mode == "strict":
                supported = current > previous
            elif mode == "increment":
                supported = current - previous == step
            elif mode == "monotonic_missing":
                delta = current - previous
                supported = delta > 0 and (max_gap is None or delta <= max_gap)
            else:
                delta = (current - previous) % modulus
                assert max_gap is not None
                supported = 0 < delta <= max_gap

            if supported:
                support_count += 1
            else:
                violation_count += 1

    sample_count = support_count + violation_count
    score = _support_ratio(support_count, sample_count)
    status = _decision(
        score,
        sample_count,
        minimum_samples=minimum_samples,
        accept_threshold=accept_threshold,
        reject_threshold=reject_threshold,
    )
    return ExecutableCheck(
        check_id=f"check:{hypothesis.hypothesis_id}:sequence",
        hypothesis_id=hypothesis.hypothesis_id,
        check_type="sequence",
        sample_count=sample_count,
        support_count=support_count,
        violation_count=violation_count,
        score=score,
        result=status,
        evidence_ids=hypothesis.supporting_evidence_ids,
    )


def verification_result(check: ExecutableCheck) -> VerificationResult:
    """Convert one executable check into the shared verification summary."""

    return VerificationResult(
        hypothesis_id=check.hypothesis_id,
        status=check.result,
        score=check.score,
        support_count=check.support_count,
        sample_count=check.sample_count,
        tests={
            "checkId": check.check_id,
            "checkType": check.check_type,
            "violationCount": check.violation_count,
            "evidenceIds": list(check.evidence_ids),
        },
    )


def _validate_hypothesis_field(hypothesis: ProtocolHypothesis) -> None:
    if not isinstance(hypothesis, ProtocolHypothesis):
        raise TypeError("hypothesis must use course_project.models.ProtocolHypothesis")
    if hypothesis.offset < 0:
        raise VerificationError("hypothesis offset must be non-negative")
    _field_size(hypothesis)


def _field_size(hypothesis: ProtocolHypothesis) -> int:
    if hypothesis.size is None or hypothesis.size <= 0:
        raise VerificationError("executable checks require a positive field size")
    return hypothesis.size


def _endian(hypothesis: ProtocolHypothesis) -> Literal["big", "little"]:
    endian = hypothesis.parameters.get("endian")
    if endian not in {"big", "little"}:
        raise VerificationError("hypothesis endian must be 'big' or 'little'")
    return endian


def _normalized_messages(messages: Iterable[BytesLike]) -> tuple[bytes, ...]:
    normalized: list[bytes] = []
    for message in messages:
        if not isinstance(message, (bytes, bytearray, memoryview)):
            raise TypeError("messages must contain bytes-like values")
        normalized.append(bytes(message))
    return tuple(normalized)


def _read_unsigned(
    message: bytes,
    offset: int,
    size: int | None,
    endian: Literal["big", "little"],
) -> int | None:
    assert size is not None
    end = offset + size
    if end > len(message):
        return None
    return int.from_bytes(message[offset:end], byteorder=endian, signed=False)


def _decision(
    score: float,
    sample_count: int,
    *,
    minimum_samples: int,
    accept_threshold: float,
    reject_threshold: float,
) -> DecisionStatus:
    if minimum_samples <= 0:
        raise VerificationError("minimum_samples must be positive")
    if not 0.0 <= reject_threshold < accept_threshold <= 1.0:
        raise VerificationError(
            "thresholds must satisfy 0 <= reject < accept <= 1"
        )
    if sample_count < minimum_samples:
        return "uncertain"
    if score >= accept_threshold:
        return "accepted"
    if score <= reject_threshold:
        return "rejected"
    return "uncertain"


def _support_ratio(support_count: int, sample_count: int) -> float:
    return support_count / sample_count if sample_count else 0.0


def _int_parameter(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise VerificationError(f"{name} must be an integer")
    return value


def _non_negative_int(value: object, name: str) -> int:
    parsed = _int_parameter(value, name)
    if parsed < 0:
        raise VerificationError(f"{name} must be non-negative")
    return parsed


def _positive_int(value: object, name: str) -> int:
    parsed = _int_parameter(value, name)
    if parsed <= 0:
        raise VerificationError(f"{name} must be positive")
    return parsed
