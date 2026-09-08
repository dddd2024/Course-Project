"""Deterministic enum and timestamp checks for protocol hypotheses."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from math import isfinite
from typing import Literal

from course_project.models import DecisionStatus, ExecutableCheck, ProtocolHypothesis
from course_project.verification.checks import VerificationError

BytesLike = bytes | bytearray | memoryview
TimestampMode = Literal["range", "monotonic", "range_and_monotonic"]
TimestampUnit = Literal["seconds", "milliseconds", "microseconds", "nanoseconds"]
EnumMode = Literal["allowed_values", "family_stable"]

_UNIT_SCALE: dict[TimestampUnit, int] = {
    "seconds": 1,
    "milliseconds": 1_000,
    "microseconds": 1_000_000,
    "nanoseconds": 1_000_000_000,
}


def verify_enum(
    hypothesis: ProtocolHypothesis,
    messages: Iterable[BytesLike],
    *,
    family_ids: Sequence[str] | None = None,
    minimum_samples: int = 3,
    accept_threshold: float = 0.9,
    reject_threshold: float = 0.5,
) -> ExecutableCheck:
    """Verify an enum/message-type interpretation over eligible messages.

    ``allowed_values`` mode verifies membership in an explicitly declared value
    set. ``family_stable`` mode verifies that one inferred message family uses a
    stable value for the candidate field. ``max_cardinality`` may additionally
    constrain the number of observed values in either mode.
    """

    _validate_hypothesis_field(hypothesis)
    endian = _endian(hypothesis)
    mode = hypothesis.parameters.get("mode", "allowed_values")
    if mode not in {"allowed_values", "family_stable"}:
        raise VerificationError(f"unsupported enum mode: {mode!r}")

    max_cardinality_raw = hypothesis.parameters.get("max_cardinality")
    max_cardinality = (
        _positive_int(max_cardinality_raw, "max_cardinality")
        if max_cardinality_raw is not None
        else None
    )

    allowed_values: frozenset[int] | None = None
    if mode == "allowed_values":
        allowed_values = _allowed_enum_values(hypothesis)
        if max_cardinality is not None and len(allowed_values) > max_cardinality:
            raise VerificationError(
                "allowed_values cardinality must not exceed max_cardinality"
            )

    normalized = _normalized_messages(messages)
    if family_ids is not None and len(family_ids) != len(normalized):
        raise VerificationError("family_ids must match the message count")
    if mode == "family_stable" and family_ids is None:
        raise VerificationError("family_stable enum mode requires family_ids")
    if family_ids is not None:
        _validate_group_ids(family_ids, "family_ids")

    values: list[tuple[int, int]] = []
    for index, message in enumerate(normalized):
        value = _read_unsigned(message, hypothesis.offset, hypothesis.size, endian)
        if value is not None:
            values.append((index, value))

    support_count = 0
    violation_count = 0
    if mode == "allowed_values":
        assert allowed_values is not None
        for _, value in values:
            if value in allowed_values:
                support_count += 1
            else:
                violation_count += 1
    else:
        assert family_ids is not None
        family_values: dict[str, set[int]] = {}
        family_counts: dict[str, int] = {}
        for index, value in values:
            family_id = family_ids[index]
            family_values.setdefault(family_id, set()).add(value)
            family_counts[family_id] = family_counts.get(family_id, 0) + 1
        for family_id, count in family_counts.items():
            if len(family_values[family_id]) == 1:
                support_count += count
            else:
                violation_count += count

    sample_count = support_count + violation_count
    observed_cardinality = len({value for _, value in values})
    if max_cardinality is not None and observed_cardinality > max_cardinality:
        support_count = 0
        violation_count = sample_count

    score = _support_ratio(support_count, sample_count)
    status = _decision(
        score,
        sample_count,
        minimum_samples=minimum_samples,
        accept_threshold=accept_threshold,
        reject_threshold=reject_threshold,
    )
    return ExecutableCheck(
        check_id=f"check:{hypothesis.hypothesis_id}:enum",
        hypothesis_id=hypothesis.hypothesis_id,
        check_type="enum",
        sample_count=sample_count,
        support_count=support_count,
        violation_count=violation_count,
        score=score,
        result=status,
        evidence_ids=hypothesis.supporting_evidence_ids,
    )


def verify_timestamp(
    hypothesis: ProtocolHypothesis,
    messages: Iterable[BytesLike],
    *,
    session_ids: Sequence[str] | None = None,
    minimum_samples: int = 3,
    accept_threshold: float = 0.9,
    reject_threshold: float = 0.5,
) -> ExecutableCheck:
    """Verify timestamp range and/or monotonicity over eligible messages.

    The interpretation requires explicit endianness and unit. Range modes also
    require explicit Unix-second bounds. ``epoch_offset_seconds`` converts an
    arbitrary protocol epoch into Unix seconds without hidden timezone/network
    tables. Monotonicity can be scoped by session and never crosses sessions.
    """

    _validate_hypothesis_field(hypothesis)
    endian = _endian(hypothesis)
    unit = hypothesis.parameters.get("unit")
    if unit not in _UNIT_SCALE:
        raise VerificationError(
            "timestamp unit must be seconds, milliseconds, microseconds, or nanoseconds"
        )
    mode = hypothesis.parameters.get("mode", "range")
    if mode not in {"range", "monotonic", "range_and_monotonic"}:
        raise VerificationError(f"unsupported timestamp mode: {mode!r}")

    strict = hypothesis.parameters.get("strict", False)
    if not isinstance(strict, bool):
        raise TypeError("strict must be a boolean")
    epoch_offset = _finite_number(
        hypothesis.parameters.get("epoch_offset_seconds", 0),
        "epoch_offset_seconds",
    )

    minimum_unix: float | None = None
    maximum_unix: float | None = None
    if mode in {"range", "range_and_monotonic"}:
        if "minimum_unix_seconds" not in hypothesis.parameters:
            raise VerificationError("timestamp range mode requires minimum_unix_seconds")
        if "maximum_unix_seconds" not in hypothesis.parameters:
            raise VerificationError("timestamp range mode requires maximum_unix_seconds")
        minimum_unix = _finite_number(
            hypothesis.parameters["minimum_unix_seconds"],
            "minimum_unix_seconds",
        )
        maximum_unix = _finite_number(
            hypothesis.parameters["maximum_unix_seconds"],
            "maximum_unix_seconds",
        )
        if maximum_unix < minimum_unix:
            raise VerificationError(
                "maximum_unix_seconds must not precede minimum_unix_seconds"
            )

    normalized = _normalized_messages(messages)
    if session_ids is not None and len(session_ids) != len(normalized):
        raise VerificationError("session_ids must match the message count")
    if session_ids is not None:
        _validate_group_ids(session_ids, "session_ids")

    scale = _UNIT_SCALE[unit]
    records: list[tuple[int, str, int, float]] = []
    for index, message in enumerate(normalized):
        raw_value = _read_unsigned(message, hypothesis.offset, hypothesis.size, endian)
        if raw_value is None:
            continue
        session_id = session_ids[index] if session_ids is not None else "default"
        unix_seconds = raw_value / scale + epoch_offset
        records.append((index, session_id, raw_value, unix_seconds))

    support_count = 0
    violation_count = 0
    if mode == "range":
        assert minimum_unix is not None and maximum_unix is not None
        for _, _, _, unix_seconds in records:
            if minimum_unix <= unix_seconds <= maximum_unix:
                support_count += 1
            else:
                violation_count += 1
    elif mode == "monotonic":
        previous_by_session: dict[str, int] = {}
        for _, session_id, raw_value, _ in records:
            previous = previous_by_session.get(session_id)
            previous_by_session[session_id] = raw_value
            if previous is None:
                continue
            supported = raw_value > previous if strict else raw_value >= previous
            if supported:
                support_count += 1
            else:
                violation_count += 1
    else:
        assert minimum_unix is not None and maximum_unix is not None
        previous_by_session = {}
        for _, session_id, raw_value, unix_seconds in records:
            in_range = minimum_unix <= unix_seconds <= maximum_unix
            previous = previous_by_session.get(session_id)
            previous_by_session[session_id] = raw_value
            monotonic = (
                True
                if previous is None
                else raw_value > previous
                if strict
                else raw_value >= previous
            )
            if in_range and monotonic:
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
        check_id=f"check:{hypothesis.hypothesis_id}:timestamp",
        hypothesis_id=hypothesis.hypothesis_id,
        check_type="timestamp",
        sample_count=sample_count,
        support_count=support_count,
        violation_count=violation_count,
        score=score,
        result=status,
        evidence_ids=hypothesis.supporting_evidence_ids,
    )


def _allowed_enum_values(hypothesis: ProtocolHypothesis) -> frozenset[int]:
    raw = hypothesis.parameters.get("allowed_values")
    if not isinstance(raw, (list, tuple)):
        raise TypeError("allowed_values must be a list or tuple of integers")
    if not raw:
        raise VerificationError("allowed_values must not be empty")
    maximum = (1 << (8 * _field_size(hypothesis))) - 1
    parsed: list[int] = []
    for value in raw:
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError("allowed_values must contain only integers")
        if not 0 <= value <= maximum:
            raise VerificationError("allowed_values must fit the unsigned field width")
        parsed.append(value)
    if len(set(parsed)) != len(parsed):
        raise VerificationError("allowed_values must not contain duplicates")
    return frozenset(parsed)


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


def _validate_group_ids(values: Sequence[str], name: str) -> None:
    for value in values:
        if not isinstance(value, str):
            raise TypeError(f"{name} must contain strings")
        if not value.strip():
            raise VerificationError(f"{name} must not contain empty IDs")


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
        raise VerificationError("thresholds must satisfy 0 <= reject < accept <= 1")
    if sample_count < minimum_samples:
        return "uncertain"
    if score >= accept_threshold:
        return "accepted"
    if score <= reject_threshold:
        return "rejected"
    return "uncertain"


def _support_ratio(support_count: int, sample_count: int) -> float:
    return support_count / sample_count if sample_count else 0.0


def _positive_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an integer")
    if value <= 0:
        raise VerificationError(f"{name} must be positive")
    return value


def _finite_number(value: object, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{name} must be numeric")
    parsed = float(value)
    if not isfinite(parsed):
        raise VerificationError(f"{name} must be finite")
    return parsed
