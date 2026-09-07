from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

DecisionStatus = Literal["accepted", "rejected", "uncertain"]
PublicDecisionStatus = Literal["ACCEPTED", "REJECTED", "UNCERTAIN"]
InputKind = Literal["dat", "bin", "pcap", "pcapng", "synthetic", "unknown"]
RegionKind = Literal["stable", "variable", "unknown"]
AnalysisTaskStatus = Literal["completed", "failed", "cancelled", "partial"]
ArtifactType = Literal[
    "evidence",
    "packets",
    "messages",
    "alignment",
    "statistics",
    "behavior",
    "restored",
    "schema",
    "report",
]
ArtifactFormat = Literal["json", "jsonl", "parquet", "csv", "text", "binary", "ksy"]


@dataclass(slots=True)
class InputMetadata:
    """Project-native metadata for one registered analysis input."""

    input_id: str
    kind: InputKind
    size_bytes: int
    sha256: str | None = None
    direction_available: bool = False
    timestamp_available: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PacketCandidate:
    start_offset: int
    end_offset: int
    confidence: float
    evidence: dict[str, Any] = field(default_factory=dict)
    direction: str | None = None
    timestamp: float | None = None


@dataclass(slots=True)
class MessageCandidate:
    """Normalized message slice used across Track D, C and A boundaries."""

    message_id: str
    input_id: str
    start_offset: int
    end_offset: int
    confidence: float = 0.0
    family_id: str | None = None
    direction: str | None = None
    timestamp: float | None = None
    evidence_ids: tuple[str, ...] = ()


@dataclass(slots=True)
class MessageFamily:
    """A project-native cluster of structurally similar messages."""

    family_id: str
    message_ids: tuple[str, ...]
    confidence: float = 0.0
    features: dict[str, Any] = field(default_factory=dict)
    evidence_ids: tuple[str, ...] = ()


@dataclass(slots=True)
class AlignmentRegion:
    start_offset: int
    end_offset: int
    kind: RegionKind
    score: float = 0.0
    evidence_ids: tuple[str, ...] = ()


@dataclass(slots=True)
class AlignmentResult:
    """Adapter-neutral alignment output for one message family."""

    family_id: str
    message_ids: tuple[str, ...]
    regions: tuple[AlignmentRegion, ...]
    score: float = 0.0
    evidence_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FieldCandidate:
    """Pre-semantic normalized field candidate produced by deterministic/PRE stages."""

    candidate_id: str
    family_id: str | None
    offset: int
    size: int | None
    candidate_types: tuple[str, ...] = ()
    endian: Literal["big", "little"] | None = None
    score: float = 0.0
    evidence_ids: tuple[str, ...] = ()
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BehaviorFeatures:
    """Adapter-neutral behavior/flow feature vector before classification."""

    flow_id: str
    values: dict[str, float | int | str | bool | None] = field(default_factory=dict)
    sample_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()


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


@dataclass(slots=True)
class ByteLocation:
    """Byte range used by findings to navigate back to the registered input."""

    input_id: str
    offset: int
    length: int


@dataclass(slots=True)
class AnalysisFinding:
    """Small evidence-linked conclusion suitable for the task-level result summary."""

    finding_id: str
    claim: str
    status: DecisionStatus
    evidence_ids: tuple[str, ...] = ()
    semantic_type: str | None = None
    location: ByteLocation | None = None
    scores: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class ArtifactRef:
    """Controlled result-relative reference to a potentially large artifact."""

    artifact_id: str
    type: ArtifactType
    format: ArtifactFormat
    ref: str
    count: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AnalysisResult:
    """Project-native task result serialized through analysis-result.schema.json."""

    task_id: str
    status: AnalysisTaskStatus
    findings: tuple[AnalysisFinding, ...] = ()
    input_id: str | None = None
    result_ref: str | None = None
    evidence: tuple[Evidence, ...] = ()
    artifacts: tuple[ArtifactRef, ...] = ()
    metrics: dict[str, Any] = field(default_factory=dict)
    limitations: tuple[str, ...] = ()
