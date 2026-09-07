from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

DecisionStatus = Literal["accepted", "rejected", "uncertain"]


@dataclass(slots=True)
class PacketCandidate:
    start_offset: int
    end_offset: int
    confidence: float
    evidence: dict[str, Any] = field(default_factory=dict)
    direction: str | None = None
    timestamp: float | None = None


@dataclass(slots=True)
class FieldHypothesis:
    """V1-compatible field hypothesis used by existing modules."""

    field_id: str
    offset: int
    size: int | None
    semantic_type: str
    endian: Literal["big", "little"] | None = None
    confidence: float = 0.0
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Evidence:
    """Provenance-tagged observation for EvidenceGraph-PRE."""

    evidence_id: str
    source_component: str
    method: str
    feature_family: str
    score: float = 0.0
    observation: dict[str, Any] = field(default_factory=dict)
    parent_evidence_ids: tuple[str, ...] = ()
    independence_group: str | None = None
    sample_ids: tuple[str, ...] = ()


@dataclass(slots=True)
class ProtocolHypothesis:
    """V2 hypothesis that can compete with alternate interpretations."""

    hypothesis_id: str
    offset: int
    size: int | None
    semantic_type: str
    interpretation: str
    parameters: dict[str, Any] = field(default_factory=dict)
    model_confidence: float = 0.0
    supporting_evidence_ids: tuple[str, ...] = ()
    competing_hypothesis_ids: tuple[str, ...] = ()


@dataclass(slots=True)
class ExecutableCheck:
    check_id: str
    hypothesis_id: str
    check_type: str
    sample_count: int
    support_count: int
    violation_count: int
    score: float
    result: DecisionStatus
    evidence_ids: tuple[str, ...] = ()


@dataclass(slots=True)
class VerificationResult:
    hypothesis_id: str
    status: DecisionStatus
    score: float
    support_count: int
    sample_count: int
    tests: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class VerifiedField:
    """Only accepted hypotheses should be promoted to this exportable form."""

    field_id: str
    offset: int
    size: int | None
    semantic_type: str
    interpretation: str
    verification_score: float
    evidence_ids: tuple[str, ...] = ()


@dataclass(slots=True)
class BehaviorPrediction:
    flow_id: str
    label: Literal["QUERY", "DOWNLOAD", "UPLOAD", "HEARTBEAT", "STREAM", "UNKNOWN"]
    confidence: float
    features: dict[str, Any] = field(default_factory=dict)
