"""Project-native provenance producer for normalized alignment evidence.

The producer consumes only frozen ``AlignmentResult`` DTOs.  It deliberately
contains no Netzob/BinaryInferno objects and does not define the later fusion
policy; its job is to turn an already-computed alignment into auditable
provenance-tagged evidence.
"""

from __future__ import annotations

from collections.abc import Iterable
from math import isfinite

from course_project.models import AlignmentRegion, AlignmentResult, Evidence


class AlignmentEvidenceError(ValueError):
    """Raised when normalized alignment data is unsafe to promote as evidence."""


def produce_alignment_evidence(
    alignments: Iterable[AlignmentResult],
) -> tuple[Evidence, ...]:
    """Map normalized alignment regions to deterministic provenance evidence.

    One Evidence record is emitted for every alignment region.  Records from
    the same message family share a family-level independence group so later
    provenance-aware fusion can conservatively recognize their correlation.
    """

    records = tuple(alignments)
    by_family: dict[str, AlignmentResult] = {}
    for alignment in records:
        _validate_alignment(alignment)
        if alignment.family_id in by_family:
            raise AlignmentEvidenceError(
                f"duplicate alignment family_id: {alignment.family_id}"
            )
        by_family[alignment.family_id] = alignment

    evidence: list[Evidence] = []
    generated_ids: set[str] = set()
    for family_id in sorted(by_family):
        alignment = by_family[family_id]
        group = f"alignment-family:{family_id}"
        for region in alignment.regions:
            evidence_id = _evidence_id(alignment, region)
            if evidence_id in generated_ids:
                raise AlignmentEvidenceError(
                    f"duplicate generated alignment evidence_id: {evidence_id}"
                )
            generated_ids.add(evidence_id)
            evidence.append(
                Evidence(
                    evidence_id=evidence_id,
                    source_component="track-d-alignment",
                    method="normalized-alignment-region",
                    feature_family="alignment",
                    score=float(region.score),
                    observation={
                        "familyId": alignment.family_id,
                        "alignmentScore": float(alignment.score),
                        "regionStart": region.start_offset,
                        "regionEnd": region.end_offset,
                        "regionKind": region.kind,
                        "regionScore": float(region.score),
                        "alignmentMetadata": dict(alignment.metadata),
                        "upstreamEvidenceIds": list(alignment.evidence_ids),
                    },
                    independence_group=group,
                    sample_ids=tuple(alignment.message_ids),
                )
            )
    return tuple(evidence)


def _validate_alignment(alignment: AlignmentResult) -> None:
    if not isinstance(alignment, AlignmentResult):
        raise TypeError("alignment must use course_project.models.AlignmentResult")
    if not alignment.family_id.strip():
        raise AlignmentEvidenceError("alignment family_id must not be empty")
    if not alignment.message_ids:
        raise AlignmentEvidenceError(
            f"alignment {alignment.family_id} requires message coverage"
        )
    if any(not message_id for message_id in alignment.message_ids):
        raise AlignmentEvidenceError(
            f"alignment {alignment.family_id} contains an empty message_id"
        )
    if len(alignment.message_ids) != len(set(alignment.message_ids)):
        raise AlignmentEvidenceError(
            f"alignment {alignment.family_id} contains duplicate message_ids"
        )
    _validate_score(alignment.score, f"alignment {alignment.family_id} score")
    if not alignment.regions:
        raise AlignmentEvidenceError(
            f"alignment {alignment.family_id} requires at least one region"
        )

    previous_end: int | None = None
    seen_ranges: set[tuple[int, int, str]] = set()
    for region in alignment.regions:
        if not isinstance(region, AlignmentRegion):
            raise TypeError("alignment regions must use course_project.models.AlignmentRegion")
        if region.start_offset < 0 or region.end_offset <= region.start_offset:
            raise AlignmentEvidenceError(
                f"alignment {alignment.family_id} contains an invalid region range"
            )
        if previous_end is not None and region.start_offset < previous_end:
            raise AlignmentEvidenceError(
                f"alignment {alignment.family_id} contains overlapping or unordered regions"
            )
        previous_end = region.end_offset
        _validate_score(
            region.score,
            f"alignment {alignment.family_id} region {region.start_offset}:{region.end_offset} score",
        )
        key = (region.start_offset, region.end_offset, region.kind)
        if key in seen_ranges:
            raise AlignmentEvidenceError(
                f"alignment {alignment.family_id} contains a duplicate region"
            )
        seen_ranges.add(key)


def _validate_score(value: float, label: str) -> None:
    score = float(value)
    if not isfinite(score) or not 0.0 <= score <= 1.0:
        raise AlignmentEvidenceError(f"{label} must be finite and in [0, 1]")


def _evidence_id(alignment: AlignmentResult, region: AlignmentRegion) -> str:
    return (
        f"alignment:{alignment.family_id}:{region.start_offset}:"
        f"{region.end_offset}:{region.kind}"
    )
