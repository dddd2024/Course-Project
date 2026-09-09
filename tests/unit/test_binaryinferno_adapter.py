from __future__ import annotations

from pathlib import Path

import pytest

from course_project.inference.binaryinferno_adapter import (
    BINARYINFERNO_UPSTREAM_COMMIT,
    BinaryInfernoConfig,
    BinaryInfernoOutputError,
    encode_binaryinferno_input,
    parse_binaryinferno_spec,
    run_binaryinferno_baseline,
)
from course_project.io import load_raw
from course_project.models import FieldCandidate, PacketCandidate


README_SPEC = """
noise before
SPECSTART
FieldFixed 1V (Unknown Type 1 Byte(s))
Length 2V_BE (BE uint16 Length + 0 = Total Message Length)
FieldFixed 4V_BE (BE 32BIT SPAN Seconds 2001-02-08 11:41:41.000000 to 2028-02-08 11:41:41.000000 1.0)
FieldRep *Q_0T_1L_1V_BE (0T_1L_V_big*)
SPECEND
noise after
"""


class FakeRunner:
    def __init__(self, stdout: str) -> None:
        self.stdout = stdout
        self.messages: tuple[bytes, ...] | None = None
        self.config: BinaryInfernoConfig | None = None

    def infer(self, messages: tuple[bytes, ...], config: BinaryInfernoConfig) -> str:
        self.messages = messages
        self.config = config
        return self.stdout


def test_unavailable_checkout_fails_closed() -> None:
    stream = load_raw(b"\x01\x02\x03\x04", source_id="binaryinferno-test")
    result = run_binaryinferno_baseline(
        stream,
        [PacketCandidate(0, 4, 1.0)],
        config=BinaryInfernoConfig(root=Path("definitely-not-present")),
    )

    assert result.backend == "binaryinferno"
    assert result.status == "unavailable"
    assert result.error_category == "dependency_unavailable"
    assert BINARYINFERNO_UPSTREAM_COMMIT in (result.detail or "")


def test_encode_input_is_one_lowercase_hex_message_per_line() -> None:
    assert encode_binaryinferno_input((b"\x01\xAF", b"\x00\x10")) == "01af\n0010\n"
    with pytest.raises(ValueError, match="at least one"):
        encode_binaryinferno_input(())
    with pytest.raises(ValueError, match="non-empty"):
        encode_binaryinferno_input((b"",))


def test_parse_readme_spec_is_exact_and_project_native() -> None:
    candidates = parse_binaryinferno_spec(README_SPEC, sample_count=3)

    assert all(isinstance(candidate, FieldCandidate) for candidate in candidates)
    assert [(candidate.offset, candidate.size) for candidate in candidates] == [
        (0, 1),
        (1, 2),
        (3, 4),
        (7, None),
    ]
    assert [candidate.candidate_types for candidate in candidates] == [
        ("unknown",),
        ("length",),
        ("timestamp",),
        ("unknown",),
    ]
    assert [candidate.endian for candidate in candidates] == [None, "big", "big", "big"]
    assert all(candidate.score == 0.5 for candidate in candidates)
    assert all(candidate.attributes["backend"] == "binaryinferno" for candidate in candidates)
    assert all(candidate.attributes["verification_status"] == "not_verified" for candidate in candidates)
    assert all(candidate.attributes["baseline_score_available"] is False for candidate in candidates)
    assert all(candidate.attributes["support"] == 3 for candidate in candidates)


def test_parser_rejects_ambiguous_nonterminal_variable_field() -> None:
    stdout = """
SPECSTART
FieldRep *Q_ANY (variable payload)
FieldFixed 2V_BE (BE trailer)
SPECEND
"""
    with pytest.raises(BinaryInfernoOutputError, match="non-terminal variable-width"):
        parse_binaryinferno_spec(stdout, sample_count=2)


def test_parser_rejects_missing_duplicate_or_unknown_spec_shapes() -> None:
    bad_outputs = [
        "no spec here",
        "SPECSTART\nFieldFixed 1V (x)\nSPECEND\nSPECSTART\nSPECEND",
        "SPECSTART\nFieldFixed weird (x)\nSPECEND",
        "SPECSTART\nnot a documented line\nSPECEND",
    ]
    for stdout in bad_outputs:
        with pytest.raises(BinaryInfernoOutputError):
            parse_binaryinferno_spec(stdout, sample_count=1)


def test_fake_runner_receives_only_valid_packet_slices_and_materializes_spec() -> None:
    stream = load_raw(b"ABCDEFGH", source_id="binaryinferno-test")
    packets = [
        PacketCandidate(0, 4, 1.0),
        PacketCandidate(4, 8, 1.0),
        PacketCandidate(8, 10, 1.0),
    ]
    runner = FakeRunner("SPECSTART\nFieldFixed 4V (Unknown Type 4 Byte(s))\nSPECEND")
    config = BinaryInfernoConfig(root=None, detectors=("boundBE",))

    result = run_binaryinferno_baseline(stream, packets, config=config, runner=runner)

    assert result.status == "ok"
    assert runner.messages == (b"ABCD", b"EFGH")
    assert runner.config == config
    assert len(result.field_candidates) == 1
    candidate = result.field_candidates[0]
    assert candidate.offset == 0
    assert candidate.size == 4
    assert candidate.attributes["sample_count"] == 2


def test_invalid_input_and_invalid_output_fail_closed() -> None:
    stream = load_raw(b"AB", source_id="binaryinferno-test")
    config = BinaryInfernoConfig(root=None, detectors=("boundBE",))

    invalid_input = run_binaryinferno_baseline(
        stream,
        [PacketCandidate(2, 3, 1.0)],
        config=config,
        runner=FakeRunner(README_SPEC),
    )
    assert invalid_input.status == "failed"
    assert invalid_input.error_category == "invalid_input"

    invalid_output = run_binaryinferno_baseline(
        stream,
        [PacketCandidate(0, 2, 1.0)],
        config=config,
        runner=FakeRunner("malformed"),
    )
    assert invalid_output.status == "failed"
    assert invalid_output.error_category == "output_invalid"


def test_config_rejects_unsafe_detector_names_and_invalid_bounds() -> None:
    with pytest.raises(ValueError, match="detector"):
        BinaryInfernoConfig(detectors=("boundBE;rm",))
    with pytest.raises(ValueError, match="timeout"):
        BinaryInfernoConfig(timeout_seconds=0)
    with pytest.raises(ValueError, match="max_output"):
        BinaryInfernoConfig(max_output_bytes=100)
