"""Deterministic executable checks for protocol hypotheses."""

from __future__ import annotations

import binascii
import math
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


def verify_magic(
    hypothesis: ProtocolHypothesis,
    messages: Iterable[BytesLike],
    *,
    minimum_samples: int = 3,
    accept_threshold: float = 0.95,
    reject_threshold: float = 0.5,
) -> ExecutableCheck:
    """Verify an exact magic value at the hypothesized field location."""

    return _verify_fixed_value(
        hypothesis,
        messages,
        check_type="magic",
        minimum_samples=minimum_samples,
        accept_threshold=accept_threshold,
        reject_threshold=reject_threshold,
    )


def verify_constant(
    hypothesis: ProtocolHypothesis,
    messages: Iterable[BytesLike],
    *,
    minimum_samples: int = 3,
    accept_threshold: float = 0.95,
    reject_threshold: float = 0.5,
) -> ExecutableCheck:
    """Verify an exact constant value at the hypothesized field location."""

    return _verify_fixed_value(
        hypothesis,
        messages,
        check_type="constant",
        minimum_samples=minimum_samples,
        accept_threshold=accept_threshold,
        reject_threshold=reject_threshold,
    )


def verify_enum(
    hypothesis: ProtocolHypothesis,
    messages: Iterable[BytesLike],
    *,
    minimum_samples: int = 3,
    accept_threshold: float = 0.95,
    reject_threshold: float = 0.5,
) -> ExecutableCheck:
    """Verify a low-cardinality integer enum or known message-type set.

    ``min_cardinality`` and ``max_cardinality`` define the observed corpus
    bounds. An optional ``allowed_values`` array additionally checks every
    eligible sample against a proposed value set.
    """

    _validate_hypothesis_field(hypothesis)
    endian = _endian(hypothesis)
    min_cardinality = _positive_int(
        hypothesis.parameters.get("min_cardinality", 2), "min_cardinality"
    )
    max_cardinality = _positive_int(
        hypothesis.parameters.get("max_cardinality", 16), "max_cardinality"
    )
    if min_cardinality > max_cardinality:
        raise VerificationError("min_cardinality must not exceed max_cardinality")

    allowed_raw = hypothesis.parameters.get("allowed_values")
    allowed_values: set[int] | None = None
    if allowed_raw is not None:
        if not isinstance(allowed_raw, (list, tuple)):
            raise VerificationError("allowed_values must be an array of integers")
        parsed_values = tuple(
            _non_negative_int(value, "allowed_values item") for value in allowed_raw
        )
        if not parsed_values:
            raise VerificationError("allowed_values must not be empty")
        if len(set(parsed_values)) != len(parsed_values):
            raise VerificationError("allowed_values must not contain duplicates")
        modulus = 1 << (8 * _field_size(hypothesis))
        if any(value >= modulus for value in parsed_values):
            raise VerificationError("allowed_values item does not fit the field")
        allowed_values = set(parsed_values)

    observed = tuple(
        value
        for message in _normalized_messages(messages)
        if (
            value := _read_unsigned(
                message, hypothesis.offset, hypothesis.size, endian
            )
        )
        is not None
    )
    cardinality_valid = min_cardinality <= len(set(observed)) <= max_cardinality
    if cardinality_valid:
        support_count = sum(
            allowed_values is None or value in allowed_values for value in observed
        )
    else:
        support_count = 0
    violation_count = len(observed) - support_count
    return _build_check(
        hypothesis,
        check_type="enum",
        support_count=support_count,
        violation_count=violation_count,
        minimum_samples=minimum_samples,
        accept_threshold=accept_threshold,
        reject_threshold=reject_threshold,
    )


def verify_timestamp(
    hypothesis: ProtocolHypothesis,
    messages: Sequence[BytesLike],
    *,
    session_ids: Sequence[str] | None = None,
    minimum_samples: int = 3,
    accept_threshold: float = 0.9,
    reject_threshold: float = 0.5,
) -> ExecutableCheck:
    """Verify timestamp range and optional within-session monotonicity.

    Supported epochs are ``unix``, ``ntp``, and ``windows_filetime``.
    Supported units are seconds, milliseconds, microseconds, nanoseconds,
    and hundred_nanoseconds.
    """

    _validate_hypothesis_field(hypothesis)
    endian = _endian(hypothesis)
    unit = hypothesis.parameters.get("unit", "seconds")
    divisors = {
        "seconds": 1.0,
        "milliseconds": 1_000.0,
        "microseconds": 1_000_000.0,
        "nanoseconds": 1_000_000_000.0,
        "hundred_nanoseconds": 10_000_000.0,
    }
    if not isinstance(unit, str) or unit not in divisors:
        raise VerificationError(f"unsupported timestamp unit: {unit!r}")

    epoch = hypothesis.parameters.get("epoch", "unix")
    epoch_offsets = {
        "unix": 0.0,
        "ntp": -2_208_988_800.0,
        "windows_filetime": -11_644_473_600.0,
    }
    if not isinstance(epoch, str) or epoch not in epoch_offsets:
        raise VerificationError(f"unsupported timestamp epoch: {epoch!r}")

    minimum = _finite_number(
        hypothesis.parameters.get("min_timestamp", 946_684_800.0),
        "min_timestamp",
    )
    maximum = _finite_number(
        hypothesis.parameters.get("max_timestamp", 4_102_444_800.0),
        "max_timestamp",
    )
    if minimum > maximum:
        raise VerificationError("min_timestamp must not exceed max_timestamp")
    monotonic = _bool_parameter(
        hypothesis.parameters.get("monotonic", True), "monotonic"
    )
    strict_monotonic = _bool_parameter(
        hypothesis.parameters.get("strict_monotonic", False), "strict_monotonic"
    )

    normalized = _normalized_messages(messages)
    if session_ids is not None and len(session_ids) != len(normalized):
        raise VerificationError("session_ids must match the message count")

    previous_by_session: dict[str, float] = {}
    support_count = 0
    violation_count = 0
    for index, message in enumerate(normalized):
        raw_value = _read_unsigned(
            message, hypothesis.offset, hypothesis.size, endian
        )
        if raw_value is None:
            continue
        timestamp = raw_value / divisors[unit] + epoch_offsets[epoch]
        supported = minimum <= timestamp <= maximum
        session_id = session_ids[index] if session_ids is not None else "default"
        previous = previous_by_session.get(session_id)
        if monotonic and previous is not None:
            supported = supported and (
                timestamp > previous if strict_monotonic else timestamp >= previous
            )
        previous_by_session[session_id] = timestamp
        if supported:
            support_count += 1
        else:
            violation_count += 1

    return _build_check(
        hypothesis,
        check_type="timestamp",
        support_count=support_count,
        violation_count=violation_count,
        minimum_samples=minimum_samples,
        accept_threshold=accept_threshold,
        reject_threshold=reject_threshold,
    )


def verify_checksum(
    hypothesis: ProtocolHypothesis,
    messages: Iterable[BytesLike],
    *,
    minimum_samples: int = 3,
    accept_threshold: float = 0.95,
    reject_threshold: float = 0.5,
) -> ExecutableCheck:
    """Verify one explicitly named, known checksum family.

    The checksum field is excluded from the selected data region by default.
    Supported algorithms are sum8, sum16, xor8, crc16_ccitt_false, and crc32.
    """

    _validate_hypothesis_field(hypothesis)
    endian = _endian(hypothesis)
    algorithm = hypothesis.parameters.get("algorithm")
    widths = {
        "sum8": 1,
        "sum16": 2,
        "xor8": 1,
        "crc16_ccitt_false": 2,
        "crc32": 4,
    }
    if not isinstance(algorithm, str) or algorithm not in widths:
        raise VerificationError(f"unsupported checksum algorithm: {algorithm!r}")
    if _field_size(hypothesis) != widths[algorithm]:
        raise VerificationError(
            f"checksum field size must be {widths[algorithm]} for {algorithm}"
        )

    data_start = _non_negative_int(
        hypothesis.parameters.get("data_start", 0), "data_start"
    )
    data_end_raw = hypothesis.parameters.get("data_end")
    data_end = (
        _non_negative_int(data_end_raw, "data_end")
        if data_end_raw is not None
        else None
    )
    if data_end is not None and data_end <= data_start:
        raise VerificationError("data_end must be greater than data_start")
    exclude_field = _bool_parameter(
        hypothesis.parameters.get("exclude_field", True), "exclude_field"
    )

    support_count = 0
    violation_count = 0
    for message in _normalized_messages(messages):
        stored = _read_unsigned(
            message, hypothesis.offset, hypothesis.size, endian
        )
        end = len(message) if data_end is None else data_end
        if stored is None or data_start >= end or end > len(message):
            continue
        data = message[data_start:end]
        if exclude_field:
            overlap_start = max(data_start, hypothesis.offset)
            overlap_end = min(end, hypothesis.offset + _field_size(hypothesis))
            if overlap_start < overlap_end:
                relative_start = overlap_start - data_start
                relative_end = overlap_end - data_start
                data = data[:relative_start] + data[relative_end:]

        computed = _checksum_value(algorithm, data)
        if stored == computed:
            support_count += 1
        else:
            violation_count += 1

    return _build_check(
        hypothesis,
        check_type="checksum",
        support_count=support_count,
        violation_count=violation_count,
        minimum_samples=minimum_samples,
        accept_threshold=accept_threshold,
        reject_threshold=reject_threshold,
    )


def verify_hypothesis(
    hypothesis: ProtocolHypothesis,
    messages: Iterable[BytesLike],
    *,
    session_ids: Sequence[str] | None = None,
    minimum_samples: int = 3,
    accept_threshold: float = 0.95,
    reject_threshold: float = 0.5,
) -> ExecutableCheck:
    """Dispatch one hypothesis to its deterministic verification family."""

    normalized = _normalized_messages(messages)
    if hypothesis.semantic_type == "length":
        return verify_length(
            hypothesis,
            normalized,
            minimum_samples=minimum_samples,
            accept_threshold=accept_threshold,
            reject_threshold=reject_threshold,
        )
    if hypothesis.semantic_type == "sequence":
        return verify_sequence(
            hypothesis,
            normalized,
            session_ids=session_ids,
            minimum_samples=minimum_samples,
            accept_threshold=accept_threshold,
            reject_threshold=reject_threshold,
        )
    if hypothesis.semantic_type == "magic":
        return verify_magic(
            hypothesis,
            normalized,
            minimum_samples=minimum_samples,
            accept_threshold=accept_threshold,
            reject_threshold=reject_threshold,
        )
    if hypothesis.semantic_type == "constant":
        return verify_constant(
            hypothesis,
            normalized,
            minimum_samples=minimum_samples,
            accept_threshold=accept_threshold,
            reject_threshold=reject_threshold,
        )
    if hypothesis.semantic_type in {"enum", "message_type"}:
        return verify_enum(
            hypothesis,
            normalized,
            minimum_samples=minimum_samples,
            accept_threshold=accept_threshold,
            reject_threshold=reject_threshold,
        )
    if hypothesis.semantic_type == "timestamp":
        return verify_timestamp(
            hypothesis,
            normalized,
            session_ids=session_ids,
            minimum_samples=minimum_samples,
            accept_threshold=accept_threshold,
            reject_threshold=reject_threshold,
        )
    if hypothesis.semantic_type == "checksum":
        return verify_checksum(
            hypothesis,
            normalized,
            minimum_samples=minimum_samples,
            accept_threshold=accept_threshold,
            reject_threshold=reject_threshold,
        )
    raise VerificationError(
        f"unsupported semantic type: {hypothesis.semantic_type!r}"
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


def _verify_fixed_value(
    hypothesis: ProtocolHypothesis,
    messages: Iterable[BytesLike],
    *,
    check_type: Literal["magic", "constant"],
    minimum_samples: int,
    accept_threshold: float,
    reject_threshold: float,
) -> ExecutableCheck:
    _validate_hypothesis_field(hypothesis)
    expected = _hex_parameter(
        hypothesis.parameters.get("value"), "value", _field_size(hypothesis)
    )
    support_count = 0
    violation_count = 0
    for message in _normalized_messages(messages):
        end = hypothesis.offset + _field_size(hypothesis)
        if end > len(message):
            continue
        if message[hypothesis.offset:end] == expected:
            support_count += 1
        else:
            violation_count += 1
    return _build_check(
        hypothesis,
        check_type=check_type,
        support_count=support_count,
        violation_count=violation_count,
        minimum_samples=minimum_samples,
        accept_threshold=accept_threshold,
        reject_threshold=reject_threshold,
    )


def _build_check(
    hypothesis: ProtocolHypothesis,
    *,
    check_type: str,
    support_count: int,
    violation_count: int,
    minimum_samples: int,
    accept_threshold: float,
    reject_threshold: float,
) -> ExecutableCheck:
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
        check_id=f"check:{hypothesis.hypothesis_id}:{check_type}",
        hypothesis_id=hypothesis.hypothesis_id,
        check_type=check_type,
        sample_count=sample_count,
        support_count=support_count,
        violation_count=violation_count,
        score=score,
        result=status,
        evidence_ids=hypothesis.supporting_evidence_ids,
    )


def _field_size(hypothesis: ProtocolHypothesis) -> int:
    if (
        hypothesis.size is None
        or isinstance(hypothesis.size, bool)
        or not isinstance(hypothesis.size, int)
        or hypothesis.size <= 0
    ):
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


def _finite_number(value: object, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise VerificationError(f"{name} must be a finite number")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise VerificationError(f"{name} must be a finite number")
    return parsed


def _bool_parameter(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise VerificationError(f"{name} must be a boolean")
    return value


def _hex_parameter(value: object, name: str, size: int) -> bytes:
    if not isinstance(value, str):
        raise VerificationError(f"{name} must be a hexadecimal string")
    normalized = value[2:] if value.startswith(("0x", "0X")) else value
    if len(normalized) != size * 2:
        raise VerificationError(f"{name} must encode exactly {size} bytes")
    try:
        return bytes.fromhex(normalized)
    except ValueError as exc:
        raise VerificationError(f"{name} must be a hexadecimal string") from exc


def _checksum_value(algorithm: object, data: bytes) -> int:
    if algorithm == "sum8":
        return sum(data) & 0xFF
    if algorithm == "sum16":
        return sum(data) & 0xFFFF
    if algorithm == "xor8":
        value = 0
        for byte in data:
            value ^= byte
        return value
    if algorithm == "crc16_ccitt_false":
        return binascii.crc_hqx(data, 0xFFFF)
    if algorithm == "crc32":
        return binascii.crc32(data) & 0xFFFFFFFF
    raise AssertionError("checksum algorithm was validated before execution")
