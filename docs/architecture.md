# Architecture — V1 Delivery + V2 EvidenceGraph + Desktop

> Status: shared contract baseline for four-person development

This document defines the current package boundaries and dependency direction. V1 remains the minimum runnable analysis path; V2 adds provenance-aware evidence and executable verification; the desktop application consumes the analyzer through versioned sidecar contracts.

## 1. Repository Boundary

```text
apps/desktop/              # React UI + Tauri/Rust shell
contracts/                 # cross-language JSON schemas
experiments/               # baselines and ablations
prompts/                   # versioned Agent prompts
src/course_project/
├── io/                    # input normalization
├── features/              # byte/statistical features
├── boundary/              # packet/message boundary candidates
├── inference/             # clustering/alignment/field inference
├── evidence/              # evidence registry + provenance graph
├── llm/                   # semantic hypothesis generation
├── verification/          # executable/deterministic checks
├── behavior/              # flow/behavior features & classifier
├── exporters/             # JSON/Kaitai/parser export
├── sidecar/               # desktop-facing analyzer protocol
└── models.py              # shared Python contracts
```

## 2. Main Dependency Direction

```text
io
 -> features
 -> boundary
 -> inference
 -> evidence
 -> llm
 -> verification
 -> exporters

io/features/inference
 -> behavior

verified/exported results
 -> sidecar
 -> contracts
 -> Tauri/Rust
 -> React UI
```

Important rules:
- upstream analysis modules do not import desktop code;
- the desktop never imports Python internals directly;
- third-party libraries remain behind adapters;
- cross-language payloads must conform to versioned schemas in `contracts/`;
- LLM output is a hypothesis source, not a protocol-fact authority.

## 3. V2 Shared Python Contracts

### PacketCandidate

```python
PacketCandidate(
    start_offset: int,
    end_offset: int,
    confidence: float,
    evidence: dict,
    direction: str | None,
    timestamp: float | None,
)
```

### Evidence

```python
Evidence(
    evidence_id: str,
    source_component: str,
    method: str,
    feature_family: str,
    score: float,
    observation: dict,
    parent_evidence_ids: tuple[str, ...],
    independence_group: str | None,
    sample_ids: tuple[str, ...],
)
```

### ProtocolHypothesis

```python
ProtocolHypothesis(
    hypothesis_id: str,
    offset: int,
    size: int | None,
    semantic_type: str,
    interpretation: str,
    parameters: dict,
    model_confidence: float,
    supporting_evidence_ids: tuple[str, ...],
    competing_hypothesis_ids: tuple[str, ...],
)
```

### ExecutableCheck

```python
ExecutableCheck(
    check_id: str,
    hypothesis_id: str,
    check_type: str,
    sample_count: int,
    support_count: int,
    violation_count: int,
    score: float,
    result: str,  # accepted / rejected / uncertain
    evidence_ids: tuple[str, ...],
)
```

### VerificationResult

```python
VerificationResult(
    hypothesis_id: str,
    status: str,  # accepted / rejected / uncertain
    score: float,
    support_count: int,
    sample_count: int,
    tests: dict,
)
```

### VerifiedField

Only a verified/accepted hypothesis may be promoted to a schema-exportable field.

```python
VerifiedField(
    field_id: str,
    offset: int,
    size: int | None,
    semantic_type: str,
    interpretation: str,
    verification_score: float,
    evidence_ids: tuple[str, ...],
)
```

### BehaviorPrediction

```python
BehaviorPrediction(
    flow_id: str,
    label: str,
    confidence: float,
    features: dict,
)
```

## 4. EvidenceGraph Rule

Evidence must retain provenance. If an LLM interpretation is produced from a Netzob alignment result, the LLM agreement is derived evidence and must not be counted as an independent second observation.

Minimum evidence lifecycle:

```text
raw observation
 -> evidence record
 -> optional derived evidence
 -> protocol hypothesis
 -> executable checks
 -> provenance-aware fusion
 -> ACCEPTED / REJECTED / UNCERTAIN
```

Accepted fields must retain links to the checks/evidence that justify them.

## 5. Adapter Contracts

```text
Scapy       -> io/scapy_adapter.py              -> project-native input records
Netzob      -> inference/netzob_adapter.py       -> project-native alignment/field data
BinaryInferno -> inference/binaryinferno_adapter.py -> project-native field candidates
NFStream    -> behavior/nfstream_adapter.py      -> project-native flow features
Kaitai      -> exporters/kaitai.py               -> schema/parser artifacts
LLM provider -> llm/<provider>_adapter.py        -> structured hypotheses
```

Third-party objects must not cross these adapter boundaries.

## 6. Desktop / Sidecar Boundary

The desktop architecture follows `docs/desktop-app-guide.md`.

```text
React UI
   |
   | typed commands/events
   v
Tauri/Rust Core
   |
   | JSON Lines / stable result references
   v
Python Sidecar
   |
   v
Analysis Engine
```

The sidecar must expose task-level operations rather than unrestricted shell access. Large binary payloads are referenced by controlled input IDs, offsets and result paths instead of being embedded in JSON messages.

Versioned contracts live in:
- `contracts/sidecar-message.schema.json`
- `contracts/analysis-result.schema.json`
- `contracts/agent-response.schema.json`

## 7. Error Semantics

Common machine-readable categories:
- `invalid_input`
- `insufficient_evidence`
- `unsupported_format`
- `dependency_unavailable`
- `inference_failed`
- `verification_failed`
- `contract_version_mismatch`
- `task_cancelled`
- `sidecar_failed`

Do not convert failures into empty successful results.

## 8. Confidence Semantics

Keep distinct:
- `model_confidence`
- `evidence_score`
- `verification_score`
- `final_confidence` (only when the fusion method is explicit)

A deterministic support ratio and an LLM self-reported probability are not interchangeable.

## 9. Contract Change Rule

For changes to `models.py`, `contracts/`, or sidecar protocol:
1. update this document/schema first;
2. add or update an example fixture;
3. update producer and consumers;
4. add compatibility/integration tests;
5. request Track A review plus at least one affected track owner;
6. document protocol/schema version changes in the PR.

## 10. Four-Track Ownership Boundary

- Track A (`@dddd2024`): shared contracts, sidecar, CI, integration/export.
- Track B (`@hinaLove1`): React/Tauri desktop and presentation layer.
- Track C (`@sunny1ce`): evidence graph, LLM hypotheses, executable verification, experiments.
- Track D (`@zhaohongjun20-creator`): deterministic binary/PRE/behavior feature producers.

Track B and Track D work packages were swapped on 2026-09-07; the account-to-track mapping did not change.

Cross-track dependencies must go through shared contracts instead of importing another track's internal implementation.
