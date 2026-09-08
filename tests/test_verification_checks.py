import pytest

from course_project.models import ProtocolHypothesis
from course_project.verification import (
    VerificationError,
    verification_result,
    verify_length,
    verify_sequence,
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
        model_confidence=0.99,
        supporting_evidence_ids=("candidate-evidence",),
    )


def length_message(payload: bytes, *, endian: str = "big") -> bytes:
    total = 4 + len(payload)
    return total.to_bytes(2, endian) + b"\x01\x00" + payload


def test_big_endian_full_message_length_is_accepted() -> None:
    messages = [length_message(bytes(index)) for index in range(3, 8)]
    candidate = hypothesis(
        "length-be-total",
        "length",
        offset=0,
        size=2,
        endian="big",
        target="full_message",
    )

    check = verify_length(candidate, messages)

    assert check.result == "accepted"
    assert check.sample_count == 5
    assert check.support_count == 5
    assert check.violation_count == 0
    assert check.evidence_ids == ("candidate-evidence",)


def test_wrong_endian_competing_length_hypothesis_is_rejected() -> None:
    messages = [length_message(bytes(index)) for index in range(3, 8)]
    candidate = hypothesis(
        "length-le-total",
        "length",
        offset=0,
        size=2,
        endian="little",
        target="full_message",
    )

    check = verify_length(candidate, messages)

    assert check.result == "rejected"
    assert check.score == 0.0
    assert check.violation_count == 5


def test_payload_and_constant_adjustment_interpretations() -> None:
    payload_messages = [
        len(bytes(index)).to_bytes(1, "big") + b"HDR" + bytes(index)
        for index in range(3, 7)
    ]
    payload = hypothesis(
        "payload-length",
        "length",
        offset=0,
        size=1,
        endian="big",
        target="payload",
        header_size=4,
    )
    total_with_adjustment = hypothesis(
        "length-plus-header",
        "length",
        offset=0,
        size=1,
        endian="big",
        target="full_message",
        adjustment=4,
    )

    assert verify_length(payload, payload_messages).result == "accepted"
    assert verify_length(total_with_adjustment, payload_messages).result == "accepted"


def test_insufficient_eligible_length_samples_abstain() -> None:
    candidate = hypothesis(
        "too-short",
        "length",
        offset=4,
        size=2,
        endian="big",
    )

    check = verify_length(candidate, (b"abc", b"def"))

    assert check.result == "uncertain"
    assert check.sample_count == 0
    assert check.score == 0.0


def sequence_message(value: int, *, size: int = 1) -> bytes:
    return b"M" + value.to_bytes(size, "big")


def test_strict_sequence_allows_missing_messages() -> None:
    messages = [sequence_message(value) for value in (1, 2, 5, 9, 10)]
    candidate = hypothesis(
        "strict-sequence",
        "sequence",
        offset=1,
        size=1,
        endian="big",
        mode="strict",
    )

    check = verify_sequence(candidate, messages)

    assert check.result == "accepted"
    assert check.sample_count == 4
    assert check.support_count == 4


def test_exact_increment_rejects_a_plausible_but_false_hypothesis() -> None:
    messages = [sequence_message(value) for value in (1, 3, 6, 10, 15)]
    candidate = hypothesis(
        "exact-increment",
        "sequence",
        offset=1,
        size=1,
        endian="big",
        mode="increment",
        step=1,
    )

    check = verify_sequence(candidate, messages)

    assert check.result == "rejected"
    assert check.support_count == 0
    assert check.violation_count == 4


def test_wraparound_sequence_uses_field_modulus() -> None:
    messages = [sequence_message(value) for value in (254, 255, 0, 1, 2)]
    candidate = hypothesis(
        "wrapping-sequence",
        "sequence",
        offset=1,
        size=1,
        endian="big",
        mode="wraparound",
        max_gap=1,
    )

    check = verify_sequence(candidate, messages)

    assert check.result == "accepted"
    assert check.support_count == 4


def test_sequence_comparisons_do_not_cross_session_boundaries() -> None:
    messages = [sequence_message(value) for value in (8, 9, 1, 2, 3)]
    candidate = hypothesis(
        "per-session-sequence",
        "sequence",
        offset=1,
        size=1,
        endian="big",
        mode="strict",
    )

    check = verify_sequence(
        candidate,
        messages,
        session_ids=("session-a", "session-a", "session-b", "session-b", "session-b"),
    )

    assert check.result == "accepted"
    assert check.sample_count == 3
    assert check.support_count == 3


def test_verification_result_preserves_counts_and_check_details() -> None:
    messages = [length_message(bytes(index)) for index in range(3, 6)]
    candidate = hypothesis(
        "summary",
        "length",
        offset=0,
        size=2,
        endian="big",
    )

    result = verification_result(verify_length(candidate, messages))

    assert result.status == "accepted"
    assert result.support_count == result.sample_count == 3
    assert result.tests == {
        "checkId": "check:summary:length",
        "checkType": "length",
        "violationCount": 0,
        "evidenceIds": ["candidate-evidence"],
    }


def test_invalid_hypothesis_parameters_fail_closed() -> None:
    invalid_endian = hypothesis(
        "invalid-endian",
        "length",
        offset=0,
        size=2,
        endian="native",
    )
    invalid_mode = hypothesis(
        "invalid-mode",
        "sequence",
        offset=0,
        size=1,
        endian="big",
        mode="guess",
    )

    with pytest.raises(VerificationError, match="endian"):
        verify_length(invalid_endian, (b"\x00\x02",) * 3)
    with pytest.raises(VerificationError, match="mode"):
        verify_sequence(invalid_mode, (b"\x01",) * 4)
    with pytest.raises(VerificationError, match="session_ids"):
        verify_sequence(
            hypothesis(
                "sessions",
                "sequence",
                offset=0,
                size=1,
                endian="big",
            ),
            (b"\x01", b"\x02"),
            session_ids=("only-one",),
        )
