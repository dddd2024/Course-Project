import binascii

import pytest

from course_project.models import ProtocolHypothesis
from course_project.verification import (
    VerificationError,
    verify_checksum,
    verify_constant,
    verify_enum,
    verify_hypothesis,
    verify_magic,
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
        model_confidence=1.0,
        supporting_evidence_ids=("source-evidence",),
    )


def test_magic_and_constant_verify_exact_bytes() -> None:
    messages = tuple(b"CP" + bytes((value,)) for value in range(5))
    magic = hypothesis("magic-cp", "magic", offset=0, size=2, value="4350")
    constant = hypothesis(
        "constant-cp", "constant", offset=0, size=2, value="0x4350"
    )

    magic_check = verify_magic(magic, messages)
    constant_check = verify_constant(constant, messages)

    assert magic_check.result == "accepted"
    assert magic_check.support_count == magic_check.sample_count == 5
    assert magic_check.check_type == "magic"
    assert constant_check.result == "accepted"
    assert constant_check.check_type == "constant"
    assert constant_check.evidence_ids == ("source-evidence",)


def test_wrong_magic_is_rejected_and_short_messages_are_ineligible() -> None:
    candidate = hypothesis("wrong-magic", "magic", offset=1, size=2, value="ffff")

    check = verify_magic(candidate, (b"xCP", b"xCP", b"xCP", b"x"))

    assert check.result == "rejected"
    assert check.sample_count == 3
    assert check.violation_count == 3


@pytest.mark.parametrize("value", [None, "zzzz", "00", 1234])
def test_invalid_magic_values_fail_closed(value: object) -> None:
    candidate = hypothesis("bad-magic", "magic", offset=0, size=2, value=value)

    with pytest.raises(VerificationError, match="value"):
        verify_magic(candidate, (b"CP",) * 3)


def test_enum_accepts_low_cardinality_known_values() -> None:
    candidate = hypothesis(
        "message-types",
        "enum",
        offset=1,
        size=1,
        endian="big",
        allowed_values=[1, 2, 3],
        max_cardinality=4,
    )
    messages = tuple(b"M" + bytes((value,)) for value in (1, 2, 1, 3, 2))

    check = verify_enum(candidate, messages)

    assert check.result == "accepted"
    assert check.sample_count == 5
    assert check.support_count == 5


def test_enum_rejects_constants_and_excessive_cardinality() -> None:
    constant = hypothesis(
        "not-enum-constant",
        "enum",
        offset=0,
        size=1,
        endian="big",
    )
    high_cardinality = hypothesis(
        "not-enum-variable",
        "enum",
        offset=0,
        size=1,
        endian="big",
        max_cardinality=3,
    )

    assert verify_enum(constant, (b"\x01",) * 4).result == "rejected"
    assert verify_enum(
        high_cardinality, tuple(bytes((value,)) for value in range(6))
    ).result == "rejected"


def test_enum_allowed_values_record_individual_violations() -> None:
    candidate = hypothesis(
        "partial-enum",
        "enum",
        offset=0,
        size=1,
        endian="big",
        allowed_values=[1, 2],
    )
    messages = tuple(bytes((value,)) for value in (1, 2, 3, 4))

    check = verify_enum(candidate, messages)

    assert check.result == "rejected"
    assert check.support_count == 2
    assert check.violation_count == 2


@pytest.mark.parametrize(
    "parameters, message",
    [
        ({"allowed_values": "1,2"}, b"\x01"),
        ({"allowed_values": []}, b"\x01"),
        ({"allowed_values": [1, 1]}, b"\x01"),
        ({"allowed_values": [256]}, b"\x01"),
        ({"min_cardinality": 4, "max_cardinality": 2}, b"\x01"),
    ],
)
def test_invalid_enum_parameters_fail_closed(
    parameters: dict[str, object], message: bytes
) -> None:
    candidate = hypothesis(
        "bad-enum", "enum", offset=0, size=1, endian="big", **parameters
    )

    with pytest.raises(VerificationError):
        verify_enum(candidate, (message,) * 3)


def timestamp_message(value: int, *, size: int = 8, endian: str = "big") -> bytes:
    return b"T" + value.to_bytes(size, endian)


def test_unix_timestamp_range_and_monotonicity_are_accepted() -> None:
    candidate = hypothesis(
        "unix-seconds",
        "timestamp",
        offset=1,
        size=8,
        endian="big",
        unit="seconds",
        epoch="unix",
    )
    messages = tuple(
        timestamp_message(value)
        for value in (1_700_000_000, 1_700_000_001, 1_700_000_005, 1_700_000_010)
    )

    check = verify_timestamp(candidate, messages)

    assert check.result == "accepted"
    assert check.support_count == 4


def test_timestamp_supports_units_epochs_and_session_resets() -> None:
    unix_values = (1_700_000_000, 1_700_000_001, 1_600_000_000, 1_600_000_001)
    ntp_offset = 2_208_988_800
    candidate = hypothesis(
        "ntp-milliseconds",
        "timestamp",
        offset=1,
        size=8,
        endian="big",
        unit="milliseconds",
        epoch="ntp",
    )
    messages = tuple(
        timestamp_message((value + ntp_offset) * 1_000) for value in unix_values
    )

    check = verify_timestamp(
        candidate,
        messages,
        session_ids=("a", "a", "b", "b"),
    )

    assert check.result == "accepted"
    assert check.sample_count == 4


def test_implausible_or_reversing_timestamp_is_rejected() -> None:
    implausible = hypothesis(
        "old-time",
        "timestamp",
        offset=0,
        size=4,
        endian="big",
    )
    reversing = hypothesis(
        "reverse-time",
        "timestamp",
        offset=0,
        size=4,
        endian="big",
        strict_monotonic=True,
    )

    assert verify_timestamp(
        implausible, tuple(timestamp_message(10, size=4)[1:] for _ in range(4))
    ).result == "rejected"
    reverse_messages = tuple(
        value.to_bytes(4, "big")
        for value in (1_700_000_004, 1_700_000_003, 1_700_000_002, 1_700_000_001)
    )
    assert verify_timestamp(reversing, reverse_messages).result == "rejected"


@pytest.mark.parametrize(
    "parameters",
    [
        {"unit": "minutes"},
        {"epoch": "gps"},
        {"min_timestamp": 10.0, "max_timestamp": 1.0},
        {"monotonic": "yes"},
    ],
)
def test_invalid_timestamp_parameters_fail_closed(
    parameters: dict[str, object],
) -> None:
    candidate = hypothesis(
        "bad-time", "timestamp", offset=0, size=4, endian="big", **parameters
    )

    with pytest.raises(VerificationError):
        verify_timestamp(candidate, (b"\x00" * 4,) * 3)


def checksum_value(algorithm: str, payload: bytes) -> int:
    if algorithm == "sum8":
        return sum(payload) & 0xFF
    if algorithm == "sum16":
        return sum(payload) & 0xFFFF
    if algorithm == "xor8":
        result = 0
        for value in payload:
            result ^= value
        return result
    if algorithm == "crc16_ccitt_false":
        return binascii.crc_hqx(payload, 0xFFFF)
    if algorithm == "crc32":
        return binascii.crc32(payload) & 0xFFFFFFFF
    raise AssertionError("unknown test algorithm")


@pytest.mark.parametrize(
    "algorithm,size",
    [
        ("sum8", 1),
        ("sum16", 2),
        ("xor8", 1),
        ("crc16_ccitt_false", 2),
        ("crc32", 4),
    ],
)
def test_known_checksum_families_are_accepted(algorithm: str, size: int) -> None:
    payloads = tuple(b"DATA" + bytes((value,)) for value in range(4))
    messages = tuple(
        payload + checksum_value(algorithm, payload).to_bytes(size, "big")
        for payload in payloads
    )
    candidate = hypothesis(
        f"checksum-{algorithm}",
        "checksum",
        offset=5,
        size=size,
        endian="big",
        algorithm=algorithm,
    )

    check = verify_checksum(candidate, messages)

    assert check.result == "accepted"
    assert check.support_count == 4
    assert check.check_type == "checksum"


def test_wrong_checksum_is_rejected() -> None:
    candidate = hypothesis(
        "wrong-crc32",
        "checksum",
        offset=4,
        size=4,
        endian="big",
        algorithm="crc32",
    )

    check = verify_checksum(candidate, (b"DATA" + b"\x00" * 4,) * 4)

    assert check.result == "rejected"
    assert check.violation_count == 4


@pytest.mark.parametrize(
    "parameters,size",
    [
        ({"algorithm": "md5"}, 4),
        ({"algorithm": "crc32"}, 2),
        ({"algorithm": ["crc32"]}, 4),
        ({"algorithm": "sum8", "data_end": 0}, 1),
        ({"algorithm": "sum8", "exclude_field": "yes"}, 1),
    ],
)
def test_invalid_checksum_parameters_fail_closed(
    parameters: dict[str, object], size: int
) -> None:
    candidate = hypothesis(
        "bad-checksum", "checksum", offset=4, size=size, endian="big", **parameters
    )

    with pytest.raises(VerificationError):
        verify_checksum(candidate, (b"DATA" + b"\x00" * size,) * 3)


def test_dispatcher_routes_supported_semantics_and_rejects_unknown() -> None:
    magic = hypothesis("dispatch-magic", "magic", offset=0, size=2, value="4350")
    message_type = hypothesis(
        "dispatch-type",
        "message_type",
        offset=0,
        size=1,
        endian="big",
        allowed_values=[1, 2],
    )
    unknown = hypothesis("dispatch-unknown", "compressed", offset=0, size=1)

    assert verify_hypothesis(magic, (b"CP",) * 3).check_type == "magic"
    assert verify_hypothesis(
        message_type, (b"\x01", b"\x02", b"\x01")
    ).check_type == "enum"
    with pytest.raises(VerificationError, match="unsupported semantic type"):
        verify_hypothesis(unknown, (b"\x00",) * 3)
