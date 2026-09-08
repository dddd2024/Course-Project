from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from course_project.exporters.kaitai import build_kaitai_schema
from course_project.models import VerifiedField

CorpusKind = Literal["teacher", "synthetic", "other"]


@dataclass(frozen=True, slots=True)
class ParseSample:
    """One named message eligible for provisional-schema execution."""

    sample_id: str
    payload: bytes


@dataclass(frozen=True, slots=True)
class ParsedField:
    """Actual bytes extracted for one verified field from one sample."""

    field_id: str
    offset: int
    value: bytes


@dataclass(frozen=True, slots=True)
class ParseSampleResult:
    """Auditable parser result for one eligible sample."""

    sample_id: str
    success: bool
    fields: tuple[ParsedField, ...]
    failed_field_id: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ParseCoverageReport:
    """Corpus execution summary using the V2 ParseCoverage definition."""

    corpus_id: str
    corpus_kind: CorpusKind
    eligible_messages: int
    successfully_parsed_messages: int
    failed_messages: int
    parse_coverage: float
    samples: tuple[ParseSampleResult, ...]


def execute_provisional_schema(
    fields: Iterable[VerifiedField],
    samples: Iterable[ParseSample],
    *,
    corpus_id: str,
    corpus_kind: CorpusKind,
) -> ParseCoverageReport:
    """Execute the conservative verified-field schema over an eligible corpus.

    The current exported Kaitai schema is intentionally limited to verified byte
    ranges plus explicit gaps. Reusing ``build_kaitai_schema`` here keeps overlap,
    variable-tail and field validation aligned with the external ``.ksy`` output
    without embedding the Kaitai compiler/runtime into the installed application.

    ``ParseCoverage`` is defined by ``docs/design-v2.md`` as
    ``successfully_parsed_messages / eligible_messages``. A sample succeeds only
    when every verified field range can be executed against that sample.
    """

    normalized_corpus_id = corpus_id.strip()
    if not normalized_corpus_id:
        raise ValueError("corpus_id must be non-empty")
    if corpus_kind not in {"teacher", "synthetic", "other"}:
        raise ValueError(f"unsupported corpus_kind: {corpus_kind!r}")

    normalized_fields = tuple(sorted(fields, key=lambda item: (item.offset, item.field_id)))
    if not normalized_fields:
        raise ValueError("provisional schema requires at least one VerifiedField")

    # This validates IDs, offsets, overlaps, variable-size placement and scores
    # against the same conservative semantics used for the emitted Kaitai schema.
    build_kaitai_schema(normalized_fields, protocol_name="provisional_protocol")

    normalized_samples = tuple(sorted(samples, key=lambda item: item.sample_id))
    if not normalized_samples:
        raise ValueError("eligible corpus must contain at least one sample")

    seen_sample_ids: set[str] = set()
    for sample in normalized_samples:
        if not isinstance(sample, ParseSample):
            raise TypeError("samples must contain ParseSample objects")
        sample_id = sample.sample_id.strip()
        if not sample_id:
            raise ValueError("sample_id must be non-empty")
        if sample_id in seen_sample_ids:
            raise ValueError(f"duplicate sample_id: {sample_id}")
        seen_sample_ids.add(sample_id)
        if not isinstance(sample.payload, bytes):
            raise TypeError(f"sample {sample_id} payload must be bytes")

    outcomes: list[ParseSampleResult] = []
    success_count = 0

    for sample in normalized_samples:
        parsed_fields: list[ParsedField] = []
        failed_field_id: str | None = None
        error: str | None = None

        for field in normalized_fields:
            start = field.offset
            if start > len(sample.payload):
                failed_field_id = field.field_id
                error = (
                    f"field {field.field_id} starts at {start}, "
                    f"beyond sample length {len(sample.payload)}"
                )
                break

            end = len(sample.payload) if field.size is None else start + field.size
            if end > len(sample.payload):
                failed_field_id = field.field_id
                error = (
                    f"field {field.field_id} requires bytes [{start}:{end}), "
                    f"sample length is {len(sample.payload)}"
                )
                break

            parsed_fields.append(
                ParsedField(
                    field_id=field.field_id,
                    offset=start,
                    value=sample.payload[start:end],
                )
            )

        success = error is None
        if success:
            success_count += 1

        outcomes.append(
            ParseSampleResult(
                sample_id=sample.sample_id,
                success=success,
                fields=tuple(parsed_fields),
                failed_field_id=failed_field_id,
                error=error,
            )
        )

    eligible = len(normalized_samples)
    failed = eligible - success_count
    return ParseCoverageReport(
        corpus_id=normalized_corpus_id,
        corpus_kind=corpus_kind,
        eligible_messages=eligible,
        successfully_parsed_messages=success_count,
        failed_messages=failed,
        parse_coverage=success_count / eligible,
        samples=tuple(outcomes),
    )
