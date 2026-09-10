"""Public D->C boundary for inference results (Track D).

This module is the only place where internal Track D profiles are mapped onto
the frozen project-native DTOs (``models.MessageFamily``,
``models.AlignmentResult``, ``models.FieldCandidate``). Internal heuristic
types (``FamilyProfile``, ``ColumnProfile``, ``FieldHypothesis``) never cross
this boundary.

Track C consumes these DTOs and owns the promotion into semantic protocol
hypotheses, evidence fusion and the final ACCEPTED/REJECTED/UNCERTAIN
decisions.
"""

from __future__ import annotations

from course_project.inference.alignment import ColumnKind, FamilyProfile, align_family
from course_project.inference.clustering import cluster_messages, message_similarity
from course_project.inference.fields import infer_fields
from course_project.io.records import ByteStream
from course_project.models import (
    AlignmentRegion,
    AlignmentResult,
    FieldCandidate,
    FieldHypothesis,
    MessageFamily,
    PacketCandidate,
    RegionKind,
)

_REGION_KIND: dict[ColumnKind, RegionKind] = {
    "constant": "stable",
    "enum": "variable",
    "variable": "variable",
}


def to_field_candidate(
    hypothesis: FieldHypothesis, *, family_id: str | None = None
) -> FieldCandidate:
    """Map an internal semantic-tagged hypothesis to a pre-semantic DTO.

    The heuristic label becomes one of ``candidate_types`` and the confidence
    becomes ``score``; nothing is lost, but the DTO no longer claims a
    semantic decision (that promotion belongs to Track C).
    """
    evidence = hypothesis.evidence
    cluster = evidence.get("cluster_id")
    if family_id is None and isinstance(cluster, int):
        family_id = f"family-{cluster}"
    return FieldCandidate(
        candidate_id=hypothesis.field_id,
        family_id=family_id,
        offset=hypothesis.offset,
        size=hypothesis.size,
        candidate_types=(hypothesis.semantic_type,),
        endian=hypothesis.endian,
        score=hypothesis.confidence,
        attributes=dict(evidence),
    )


def infer_field_candidates(
    stream: ByteStream,
    packets: list[PacketCandidate],
    *,
    header_len: int = 8,
    cluster_threshold: float = 0.9,
) -> list[FieldCandidate]:
    """Public boundary: pre-semantic field candidates for Track C."""
    return [
        to_field_candidate(hypothesis)
        for hypothesis in infer_fields(
            stream,
            packets,
            header_len=header_len,
            cluster_threshold=cluster_threshold,
        )
    ]


def family_analysis(
    stream: ByteStream,
    packets: list[PacketCandidate],
    *,
    input_id: str | None = None,
    header_len: int = 8,
    cluster_threshold: float = 0.9,
) -> tuple[list[MessageFamily], list[AlignmentResult]]:
    """Public boundary: frozen family/alignment DTOs for Track C.

    Message ids follow the same ``<input_id>-m<index>`` scheme as
    ``boundary.to_message_candidates`` so the two views join cleanly.
    """
    input_id = input_id or stream.source_id
    base = stream.offset_base
    messages = []
    for packet in packets:
        start = packet.start_offset - base
        end = packet.end_offset - base
        if 0 <= start < end <= len(stream.data):
            messages.append(stream.data[start:end])
    if not messages:
        return [], []

    labels = cluster_messages(
        messages, header_len=header_len, threshold=cluster_threshold
    )
    families: dict[int, list[int]] = {}
    for index, label in enumerate(labels):
        families.setdefault(label, []).append(index)

    family_dtos: list[MessageFamily] = []
    alignment_dtos: list[AlignmentResult] = []
    for cluster_id in sorted(families):
        indices = families[cluster_id]
        family_id = f"family-{cluster_id}"
        family_messages = [messages[i] for i in indices]
        profile = align_family(family_messages, cluster_id=cluster_id)
        regions = _alignment_regions(profile)

        member_ids = tuple(f"{input_id}-m{i}" for i in indices)
        representative = family_messages[0]
        member_similarity = [
            message_similarity(m, representative, header_len=header_len)
            for m in family_messages
        ]
        family_dtos.append(
            MessageFamily(
                family_id=family_id,
                message_ids=member_ids,
                confidence=round(sum(member_similarity) / len(member_similarity), 6),
                features={
                    "message_count": profile.message_count,
                    "min_length": profile.min_length,
                    "max_length": profile.max_length,
                },
            )
        )
        alignment_dtos.append(
            AlignmentResult(
                family_id=family_id,
                message_ids=member_ids,
                regions=tuple(regions),
                score=round(
                    sum(region.score for region in regions) / max(len(regions), 1), 6
                ),
                metadata={
                    "cluster_id": cluster_id,
                    "has_variable_tail": profile.has_variable_tail,
                },
            )
        )
    return family_dtos, alignment_dtos


def _alignment_regions(profile: FamilyProfile) -> list[AlignmentRegion]:
    """Merge consecutive columns of the same public kind into DTO regions."""
    regions: list[AlignmentRegion] = []
    start: int | None = None
    kind: RegionKind | None = None
    scores: list[float] = []

    def flush(end: int) -> None:
        nonlocal start, kind
        if start is not None and kind is not None:
            regions.append(
                AlignmentRegion(
                    start_offset=start,
                    end_offset=end,
                    kind=kind,
                    score=round(sum(scores) / len(scores), 6),
                )
            )
        start, kind = None, None
        scores.clear()

    for column in profile.regions:
        column_kind = _REGION_KIND[column.kind]
        score = _column_score(column.kind, column.cardinality)
        if start is None:
            start, kind = column.offset, column_kind
            scores.append(score)
        elif column_kind == kind:
            scores.append(score)
        else:
            flush(column.offset)
            start, kind = column.offset, column_kind
            scores.append(score)
    flush(len(profile.regions))
    return regions


def _column_score(kind: ColumnKind, cardinality: int) -> float:
    if kind == "constant":
        return 1.0
    if kind == "enum":
        return 1.0 - (cardinality - 1) / 16.0
    return 0.5


def refine_boundaries(
    stream: ByteStream,
    packets: list[PacketCandidate],
    *,
    header_len: int = 8,
    cluster_threshold: float = 0.9,
    blend: float = 0.4,
) -> list[PacketCandidate]:
    """Adjust boundary confidence with alignment gain (design-v1 §5.3).

    Clusters and aligns the current segmentation, then recalibrates each
    packet's confidence: packets belonging to families with stable column
    structure get a boost, garbage-like families get a penalty. Positions are
    never changed — this only recalibrates confidence and annotates
    ``evidence["alignment_gain"]`` / ``evidence["family_id"]``.
    """
    if not 0.0 <= blend <= 1.0:
        raise ValueError("blend must be in [0, 1]")

    base = stream.offset_base
    valid: list[tuple[int, bytes]] = []
    for index, packet in enumerate(packets):
        start = packet.start_offset - base
        end = packet.end_offset - base
        if 0 <= start < end <= len(stream.data):
            valid.append((index, stream.data[start:end]))
    if not valid:
        return list(packets)

    labels = cluster_messages(
        [message for _, message in valid],
        header_len=header_len,
        threshold=cluster_threshold,
    )
    families: dict[int, list[int]] = {}
    for j, label in enumerate(labels):
        families.setdefault(label, []).append(j)

    gain_by_label: dict[int, float] = {}
    for label, member_js in families.items():
        profile = align_family([valid[j][1] for j in member_js], cluster_id=label)
        gain_by_label[label] = _alignment_gain(profile)

    label_by_index = {valid[j][0]: labels[j] for j in range(len(labels))}

    adjusted: list[PacketCandidate] = []
    for index, packet in enumerate(packets):
        label = label_by_index.get(index)
        if label is None:
            adjusted.append(packet)
            continue
        gain = gain_by_label[label]
        confidence = round(
            max(0.0, min(1.0, (1.0 - blend) * packet.confidence + blend * gain)),
            6,
        )
        adjusted.append(
            PacketCandidate(
                start_offset=packet.start_offset,
                end_offset=packet.end_offset,
                confidence=confidence,
                direction=packet.direction,
                timestamp=packet.timestamp,
                evidence={
                    **packet.evidence,
                    "alignment_gain": round(gain, 6),
                    "family_id": f"family-{label}",
                },
            )
        )
    return adjusted


def _alignment_gain(profile: FamilyProfile) -> float:
    """Stability score of a family's columns: 1.0 = fully structured."""
    if profile.message_count < 2:
        return 0.5  # singletons prove nothing about alignment
    if not profile.regions:
        return 0.5
    weights = {"constant": 1.0, "enum": 0.5, "variable": 0.0}
    return sum(weights[region.kind] for region in profile.regions) / len(
        profile.regions
    )
