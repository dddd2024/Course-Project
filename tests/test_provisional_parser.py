from __future__ import annotations

import pytest

from course_project.models import VerifiedField
from course_project.verification.provisional_parser import (
    ParseSample,
    execute_provisional_schema,
)


def _field(
    field_id: str,
    offset: int,
    size: int | None,
) -> VerifiedField:
    return VerifiedField(
        field_id=field_id,
        offset=offset,
        size=size,
        semantic_type="test",
        interpretation="controlled synthetic fixture",
        verification_score=1.0,
        evidence_ids=(f"evidence-{field_id}",),
    )


def test_provisional_schema_executes_and_reports_full_parse_coverage() -> None:
    report = execute_provisional_schema(
        (_field("prefix", 0, 2), _field("kind", 4, 1)),
        (
            ParseSample("msg-2", b"ABxxZtail"),
            ParseSample("msg-1", b"CDyyQ"),
        ),
        corpus_id="synthetic-full",
        corpus_kind="synthetic",
    )

    assert report.corpus_id == "synthetic-full"
    assert report.corpus_kind == "synthetic"
    assert report.eligible_messages == 2
    assert report.successfully_parsed_messages == 2
    assert report.failed_messages == 0
    assert report.parse_coverage == 1.0
    assert tuple(item.sample_id for item in report.samples) == ("msg-1", "msg-2")
    assert tuple(field.value for field in report.samples[0].fields) == (b"CD", b"Q")
    assert tuple(field.value for field in report.samples[1].fields) == (b"AB", b"Z")


def test_provisional_schema_reports_partial_coverage_and_auditable_failure() -> None:
    report = execute_provisional_schema(
        (_field("prefix", 0, 2), _field("kind", 4, 1)),
        (
            ParseSample("good", b"ABxxZ"),
            ParseSample("short", b"ABxx"),
        ),
        corpus_id="synthetic-partial",
        corpus_kind="synthetic",
    )

    assert report.eligible_messages == 2
    assert report.successfully_parsed_messages == 1
    assert report.failed_messages == 1
    assert report.parse_coverage == 0.5

    good, short = report.samples
    assert good.sample_id == "good"
    assert good.success is True
    assert short.sample_id == "short"
    assert short.success is False
    assert short.failed_field_id == "kind"
    assert short.error is not None
    assert "requires bytes [4:5)" in short.error
    assert tuple(field.field_id for field in short.fields) == ("prefix",)


def test_variable_final_verified_field_executes_to_end_of_sample() -> None:
    report = execute_provisional_schema(
        (_field("header", 0, 2), _field("payload", 2, None)),
        (ParseSample("msg", b"ABpayload"),),
        corpus_id="synthetic-variable-tail",
        corpus_kind="synthetic",
    )

    assert report.parse_coverage == 1.0
    assert tuple(field.value for field in report.samples[0].fields) == (b"AB", b"payload")


@pytest.mark.parametrize(
    ("fields", "samples", "corpus_id", "corpus_kind", "error_type", "message"),
    [
        ((), (ParseSample("msg", b"abc"),), "c", "synthetic", ValueError, "at least one"),
        ((_field("a", 0, 1),), (), "c", "synthetic", ValueError, "at least one sample"),
        (
            (_field("a", 0, 1),),
            (ParseSample("dup", b"a"), ParseSample("dup", b"b")),
            "c",
            "synthetic",
            ValueError,
            "duplicate sample_id",
        ),
        (
            (_field("a", 0, 1),),
            (ParseSample("msg", "not-bytes"),),  # type: ignore[arg-type]
            "c",
            "synthetic",
            TypeError,
            "payload must be bytes",
        ),
        (
            (_field("a", 0, 1),),
            (ParseSample("msg", b"a"),),
            " ",
            "synthetic",
            ValueError,
            "corpus_id",
        ),
        (
            (_field("a", 0, 1),),
            (ParseSample("msg", b"a"),),
            "c",
            "formal",  # type: ignore[arg-type]
            ValueError,
            "corpus_kind",
        ),
    ],
)
def test_provisional_schema_fails_closed_on_malformed_inputs(
    fields: tuple[VerifiedField, ...],
    samples: tuple[ParseSample, ...],
    corpus_id: str,
    corpus_kind: str,
    error_type: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error_type, match=message):
        execute_provisional_schema(
            fields,
            samples,
            corpus_id=corpus_id,
            corpus_kind=corpus_kind,  # type: ignore[arg-type]
        )


def test_provisional_schema_reuses_kaitai_layout_validation() -> None:
    with pytest.raises(ValueError, match="overlaps"):
        execute_provisional_schema(
            (_field("first", 0, 4), _field("second", 2, 2)),
            (ParseSample("msg", b"abcdef"),),
            corpus_id="synthetic-overlap",
            corpus_kind="synthetic",
        )
