import pytest

from course_project.models import ProtocolHypothesis
from course_project.verification import (
    VerificationError,
    verification_result,
    verify_enum,
    verify_timestamp,
)


def hypothesis(
    hypothesis_id: str,
    semantic_type: str,
    *,
    offset: int,
    size: int,
    **parameters: object,
) -> ProtocolHypothesis:
    return ProtocolHypothesis(
        hypothesis_id=hypothesis_id,
        offset=offset,
        size=size,
        semantic_type=semantic_type,
        interpretation=hypothesis_id,
        parameters=dict(parameters),
        model_confidence=0.8,
        supporting_evidence_ids=("candidate-evidence",),
    )


def enum_message(value: int) -> bytes:
    return b"H" + value.to_bytes(1, "big") + b"P"


def timestamp_message(value: int, *, size: int = 8) -> bytes:
    return b"T" + value.to_bytes(size, "big")


def test_enum_allowed_values_accepts_known_message_types() -> None:
    candidate = hypothesis(
        "enum-known",
        "message_type",
        offset=1,
        size=1,
        endian="big",
        mode="allowed_values",
        allowed_values=[1, 2, 3],
        max_cardinality=3,
    )

    check = verify_enum(candidate, [enum_message(value) for value in (1, 2, 1, 3, 2)])

    assert check.result == "accepted"
    assert check.sample_count == 5
    assert check.support_count == 5
    assert check.violation_count == 0
    assert check.check_type == "enum"


def test_enum_allowed_values_rejects_out_of_set_values() -> None:
    candidate = hypothesis(
        "enum-false",
        "message_type",
        offset=1,
        size=1,
        endian="big",
        allowed_values=[1, 2],
    )

    check = verify_enum(candidate, [enum_message(value) for value in (7, 8, 9, 1)])

    assert check.result == "rejected"
    assert check.support_count == 1
    assert check.violation_count == 3


def test_enum_family_stability_is_order_invariant() -> None:
    candidate = hypothesis(
        "enum-family",
        "message_type",
        offset=1,
        size=1,
        endian="big",
        mode="family_stable",
        max_cardinality=3,
    )
    messages = [enum_message(value) for value in (1, 1, 2, 2, 3, 3)]
    families = ("a", "a", "b", "b", "c", "c")

    first = verify_enum(candidate, messages, family_ids=families)
    second = verify_enum(candidate, tuple(reversed(messages)), family_ids=tuple(reversed(families)))

    assert first == second
    assert first.result == "accepted"
    assert first.support_count == 6


def test_enum_family_instability_and_cardinality_can_reject() -> None:
    unstable = hypothesis(
        "enum-unstable",
        "message_type",
        offset=1,
        size=1,
        endian="big",
        mode="family_stable",
    )
    high_cardinality = hypothesis(
        "enum-cardinality",
        "message_type",
        offset=1,
        size=1,
        endian="big",
        allowed_values=[1, 2, 3, 4],
        max_cardinality=4,
    )

    unstable_check = verify_enum(
        unstable,
        [enum_message(value) for value in (1, 2, 3, 4)],
        family_ids=("same", "same", "same", "same"),
    )
    cardinality_check = verify_enum(
        high_cardinality,
        [enum_message(value) for value in (1, 2, 3, 4, 5)],
    )

    assert unstable_check.result == "rejected"
    assert unstable_check.violation_count == 4
    assert cardinality_check.result == "rejected"
    assert cardinality_check.support_count == 0


def test_enum_insufficient_samples_abstain() -> None:
    candidate = hypothesis(
        "enum-short",
        "message_type",
        offset=1,
        size=1,
        endian="big",
        allowed_values=[1],
    )

    check = verify_enum(candidate, [enum_message(1), enum_message(1)])

    assert check.result == "uncertain"
    assert check.sample_count == 2


def test_timestamp_range_accepts_seconds() -> None:
    candidate = hypothesis(
        "timestamp-seconds",
        "timestamp",
        offset=1,
        size=8,
        endian="big",
        unit="seconds",
        mode="range",
        minimum_unix_seconds=1_700_000_000,
        maximum_unix_seconds=1_800_000_000,
    )
    messages = [timestamp_message(value) for value in (1_700_000_001, 1_710_000_000, 1_799_999_999)]

    check = verify_timestamp(candidate, messages)

    assert check.result == "accepted"
    assert check.support_count == 3
    assert check.check_type == "timestamp"


def test_timestamp_milliseconds_and_epoch_offset_are_supported() -> None:
    candidate = hypothesis(
        "timestamp-offset",
        "timestamp",
        offset=1,
        size=8,
        endian="big",
        unit="milliseconds",
        mode="range",
        epoch_offset_seconds=946_684_800,
        minimum_unix_seconds=946_684_800,
        maximum_unix_seconds=946_684_805,
    )

    check = verify_timestamp(
        candidate,
        [timestamp_message(value) for value in (0, 1_000, 2_000, 3_000)],
    )

    assert check.result == "accepted"
    assert check.support_count == 4


def test_timestamp_range_rejects_implausible_values() -> None:
    candidate = hypothesis(
        "timestamp-range-false",
        "timestamp",
        offset=1,
        size=8,
        endian="big",
        unit="seconds",
        mode="range",
        minimum_unix_seconds=1_700_000_000,
        maximum_unix_seconds=1_800_000_000,
    )

    check = verify_timestamp(candidate, [timestamp_message(value) for value in (1, 2, 3, 4)])

    assert check.result == "rejected"
    assert check.violation_count == 4


def test_timestamp_monotonicity_does_not_cross_sessions() -> None:
    candidate = hypothesis(
        "timestamp-session",
        "timestamp",
        offset=1,
        size=8,
        endian="big",
        unit="microseconds",
        mode="monotonic",
        strict=True,
    )
    values = (100, 200, 1, 2, 3)

    check = verify_timestamp(
        candidate,
        [timestamp_message(value) for value in values],
        session_ids=("a", "a", "b", "b", "b"),
    )

    assert check.result == "accepted"
    assert check.sample_count == 3
    assert check.support_count == 3


def test_timestamp_monotonicity_rejects_descending_values() -> None:
    candidate = hypothesis(
        "timestamp-descending",
        "timestamp",
        offset=1,
        size=8,
        endian="big",
        unit="nanoseconds",
        mode="monotonic",
        strict=False,
    )

    check = verify_timestamp(
        candidate,
        [timestamp_message(value) for value in (10, 9, 8, 7, 6)],
    )

    assert check.result == "rejected"
    assert check.violation_count == 4


def test_timestamp_range_and_monotonic_can_abstain() -> None:
    candidate = hypothesis(
        "timestamp-mixed",
        "timestamp",
        offset=1,
        size=8,
        endian="big",
        unit="seconds",
        mode="range_and_monotonic",
        minimum_unix_seconds=100,
        maximum_unix_seconds=200,
    )

    check = verify_timestamp(
        candidate,
        [timestamp_message(value) for value in (100, 120, 110, 130)],
    )

    assert check.result == "uncertain"
    assert check.support_count == 3
    assert check.violation_count == 1
    assert check.score == 0.75


def test_verification_result_remains_compatible_for_new_checks() -> None:
    candidate = hypothesis(
        "enum-summary",
        "message_type",
        offset=1,
        size=1,
        endian="big",
        allowed_values=[1, 2],
    )

    result = verification_result(
        verify_enum(candidate, [enum_message(value) for value in (1, 2, 1)])
    )

    assert result.status == "accepted"
    assert result.tests["checkType"] == "enum"
    assert result.tests["evidenceIds"] == ["candidate-evidence"]


def test_invalid_enum_parameters_fail_closed() -> None:
    with pytest.raises(TypeError, match="allowed_values"):
        verify_enum(
            hypothesis(
                "enum-type",
                "message_type",
                offset=1,
                size=1,
                endian="big",
                allowed_values="1,2",
            ),
            [enum_message(1)] * 3,
        )
    with pytest.raises(VerificationError, match="duplicates"):
        verify_enum(
            hypothesis(
                "enum-duplicate",
                "message_type",
                offset=1,
                size=1,
                endian="big",
                allowed_values=[1, 1],
            ),
            [enum_message(1)] * 3,
        )
    with pytest.raises(VerificationError, match="family_ids"):
        verify_enum(
            hypothesis(
                "enum-family-missing",
                "message_type",
                offset=1,
                size=1,
                endian="big",
                mode="family_stable",
            ),
            [enum_message(1)] * 3,
        )


def test_invalid_timestamp_parameters_fail_closed() -> None:
    missing_range = hypothesis(
        "timestamp-missing-range",
        "timestamp",
        offset=1,
        size=8,
        endian="big",
        unit="seconds",
        mode="range",
    )
    invalid_unit = hypothesis(
        "timestamp-unit",
        "timestamp",
        offset=1,
        size=8,
        endian="big",
        unit="minutes",
        mode="monotonic",
    )

    with pytest.raises(VerificationError, match="minimum_unix_seconds"):
        verify_timestamp(missing_range, [timestamp_message(1)] * 3)
    with pytest.raises(VerificationError, match="unit"):
        verify_timestamp(invalid_unit, [timestamp_message(1)] * 4)
    with pytest.raises(VerificationError, match="session_ids"):
        verify_timestamp(
            hypothesis(
                "timestamp-session-count",
                "timestamp",
                offset=1,
                size=8,
                endian="big",
                unit="seconds",
                mode="monotonic",
            ),
            [timestamp_message(1), timestamp_message(2)],
            session_ids=("only-one",),
        )
