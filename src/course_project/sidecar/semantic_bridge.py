from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from course_project.models import (
    AlignmentResult,
    AnalysisFinding,
    BehaviorFeatures,
    Evidence,
    FieldCandidate,
    InputMetadata,
    MessageCandidate,
    MessageFamily,
    PacketCandidate,
    VerifiedField,
)

SemanticTaskStatus = Literal["completed", "partial"]


@dataclass(slots=True)
class SemanticAnalysis:
    """Project-native Track C output consumed by the Track A orchestrator.

    The bridge intentionally contains no provider-specific or PRE-library objects.
    A Track C implementation may use any internal architecture, but the Sidecar
    integration boundary accepts only the frozen shared DTOs and these result
    collections.
    """

    producer: str
    status: SemanticTaskStatus = "completed"
    findings: tuple[AnalysisFinding, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    verified_fields: tuple[VerifiedField, ...] = ()
    metrics: dict[str, Any] = field(default_factory=dict)
    limitations: tuple[str, ...] = ()


class SemanticBackend(Protocol):
    """Narrow adapter boundary from Track D preprocessing into Track C semantics."""

    def analyze(
        self,
        *,
        input_metadata: InputMetadata,
        input_path: Path,
        packets: tuple[PacketCandidate, ...],
        messages: tuple[MessageCandidate, ...],
        families: tuple[MessageFamily, ...],
        alignments: tuple[AlignmentResult, ...],
        field_candidates: tuple[FieldCandidate, ...],
        large_raw_profile: Mapping[str, Any] | None,
        behavior: BehaviorFeatures | None,
        config: Mapping[str, Any],
    ) -> SemanticAnalysis: ...


def validate_semantic_analysis(result: SemanticAnalysis) -> None:
    """Fail closed before semantic output is promoted into a Sidecar result."""

    if not result.producer.strip():
        raise ValueError("semantic producer must be non-empty")
    if result.status not in {"completed", "partial"}:
        raise ValueError("semantic status must be completed or partial")

    evidence_ids = [item.evidence_id for item in result.evidence]
    if any(not item for item in evidence_ids):
        raise ValueError("semantic evidence IDs must be non-empty")
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("semantic evidence IDs must be unique")
    evidence_id_set = set(evidence_ids)

    finding_ids = [item.finding_id for item in result.findings]
    if any(not item for item in finding_ids):
        raise ValueError("semantic finding IDs must be non-empty")
    if len(finding_ids) != len(set(finding_ids)):
        raise ValueError("semantic finding IDs must be unique")
    for finding in result.findings:
        missing = set(finding.evidence_ids) - evidence_id_set
        if missing:
            names = ", ".join(sorted(missing))
            raise ValueError(
                f"semantic finding {finding.finding_id} references missing evidence: {names}"
            )

    verified_ids = [item.field_id for item in result.verified_fields]
    if any(not item for item in verified_ids):
        raise ValueError("verified field IDs must be non-empty")
    if len(verified_ids) != len(set(verified_ids)):
        raise ValueError("verified field IDs must be unique")
    for field_item in result.verified_fields:
        missing = set(field_item.evidence_ids) - evidence_id_set
        if missing:
            names = ", ".join(sorted(missing))
            raise ValueError(
                f"verified field {field_item.field_id} references missing evidence: {names}"
            )
