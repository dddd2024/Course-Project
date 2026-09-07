from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


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
    field_id: str
    offset: int
    size: int | None
    semantic_type: str
    endian: Literal["big", "little"] | None = None
    confidence: float = 0.0
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class VerificationResult:
    hypothesis_id: str
    status: Literal["accepted", "rejected", "uncertain"]
    score: float
    support_count: int
    sample_count: int
    tests: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BehaviorPrediction:
    flow_id: str
    label: Literal["QUERY", "DOWNLOAD", "UPLOAD", "HEARTBEAT", "STREAM", "UNKNOWN"]
    confidence: float
    features: dict[str, Any] = field(default_factory=dict)
