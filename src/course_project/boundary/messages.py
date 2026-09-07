"""Canonical MessageCandidate conversion for the public D->C boundary (Track D)."""

from __future__ import annotations

from course_project.io.records import ByteStream
from course_project.models import MessageCandidate, PacketCandidate


def to_message_candidates(
    stream: ByteStream,
    packets: list[PacketCandidate],
    *,
    input_id: str | None = None,
    family_ids: list[str | None] | None = None,
) -> list[MessageCandidate]:
    """Map boundary PacketCandidates onto frozen MessageCandidate DTOs.

    ``family_ids`` (when provided) must align 1:1 with ``packets``; the
    inference layer fills it from clustering. Message ids follow the
    ``<input_id>-m<index>`` scheme so consumers can join messages to the
    family/alignment DTOs produced by ``inference.family_analysis``.
    """
    input_id = input_id or stream.source_id
    if family_ids is not None and len(family_ids) != len(packets):
        raise ValueError("family_ids must align with packets")
    messages = []
    for index, packet in enumerate(packets):
        messages.append(
            MessageCandidate(
                message_id=f"{input_id}-m{index}",
                input_id=input_id,
                start_offset=packet.start_offset,
                end_offset=packet.end_offset,
                confidence=packet.confidence,
                family_id=None if family_ids is None else family_ids[index],
                direction=packet.direction,
                timestamp=packet.timestamp,
            )
        )
    return messages
