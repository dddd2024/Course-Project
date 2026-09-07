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
├── sidecar/               # desktop-facing analyzer protocol/runtime
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

## 3. Shared Python Contracts

Exact definitions live in `src/course_project/models.py`. These objects are the project-native intermediate language between Tracks; third-party library objects must not cross Track boundaries.

### 3.1 Input and deterministic/PRE DTOs

`InputMetadata` records a registered input without embedding raw bytes in shared messages.

```text
InputMetadata
- input_id
- kind: dat | bin | pcap | pcapng | synthetic | unknown
- size_bytes
- sha256 (optional)
- direction_available
- timestamp_available
- metadata
```

`PacketCandidate` remains the lightweight V1 boundary record.

```text
PacketCandidate
- start_offset
- end_offset
- confidence
- evidence
- direction (optional)
- timestamp (optional)
```

`MessageCandidate` gives a stable message identifier and source byte range.

```text
MessageCandidate
- message_id
- input_id
- start_offset
- end_offset
- confidence
- family_id (optional)
- direction/timestamp (optional)
- evidence_ids
```

`MessageFamily` is an adapter-neutral cluster of structurally similar messages.

```text
MessageFamily
- family_id
- message_ids
- confidence
- features
- evidence_ids
```

`AlignmentRegion` / `AlignmentResult` are the canonical D→C alignment representation.

```text
AlignmentRegion
- start_offset
- end_offset
- kind: stable | variable | unknown
- score
- evidence_ids

AlignmentResult
- family_id
- message_ids
- regions
- score
- evidence_ids
- metadata
```

`FieldCandidate` is the deterministic/PRE candidate before Track C promotes it into a semantic protocol hypothesis.

```text
FieldCandidate
- candidate_id
- family_id
- offset
- size
- candidate_types
- endian (optional)
- score
- evidence_ids
- attributes
```

`BehaviorFeatures` is the adapter-neutral feature record before behavior classification.

```text
BehaviorFeatures
- flow_id
- values
- sample_ids
- evidence_ids
```

### 3.2 V1/V2 semantic and verification DTOs

`FieldHypothesis` remains the V1-compatible semantic field candidate.

```text
FieldHypothesis
- field_id
- offset
- size
- semantic_type
- endian
- confidence
- evidence
```

`Evidence`:

```text
Evidence
- evidence_id
- source_component
- method
- feature_family
- score
- observation
- parent_evidence_ids
- independence_group
- sample_ids
```

`ProtocolHypothesis`:

```text
ProtocolHypothesis
- hypothesis_id
- offset
- size
- semantic_type
- interpretation
- parameters
- model_confidence
- supporting_evidence_ids
- competing_hypothesis_ids
```

`ExecutableCheck`:

```text
ExecutableCheck
- check_id
- hypothesis_id
- check_type
- sample_count
- support_count
- violation_count
- score
- result: accepted | rejected | uncertain
- evidence_ids
```

`VerificationResult`:

```text
VerificationResult
- hypothesis_id
- status: accepted | rejected | uncertain
- score
- support_count
- sample_count
- tests
```

`VerifiedField` is schema-exportable only after accepted verification.

`BehaviorPrediction` remains the final behavior classification output.

### 3.3 Task result DTOs

Track A owns the project-native result representation that is serialized into `analysis-result.schema.json`:

```text
ByteLocation
- input_id
- offset
- length

AnalysisFinding
- finding_id
- claim
- status: accepted | rejected | uncertain
- evidence_ids
- semantic_type (optional)
- location (optional)
- scores: model/evidence/verification only

ArtifactRef
- artifact_id
- type
- format
- ref
- count (optional)
- metadata

AnalysisResult
- task_id
- status: completed | failed | cancelled | partial
- input_id
- result_ref
- findings
- evidence
- artifacts
- metrics
- limitations
```

The serializer maps internal snake_case/lowercase status values to the frozen camelCase/uppercase JSON contract and rejects unresolved evidence references, duplicate evidence/artifact IDs, invalid scores and unsafe result refs.

## 4. Decision Status Contract

There is one conceptual three-way decision model:

```text
ACCEPTED
REJECTED
UNCERTAIN
```

Mapping by layer:

| Layer | Accepted | Rejected | Uncertain |
|---|---|---|---|
| Python internal | `accepted` | `rejected` | `uncertain` |
| JSON / TypeScript / Rust | `ACCEPTED` | `REJECTED` | `UNCERTAIN` |
| Human-facing docs/UI | ACCEPTED | REJECTED | UNCERTAIN |

Legacy `ACCEPT`, `REJECT`, and `UNSURE` spellings must not be introduced as enum values.

## 5. EvidenceGraph Rule

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

## 6. Adapter Contracts

```text
Scapy         -> io/scapy_adapter.py                    -> project-native input/message records
Netzob        -> inference/netzob_adapter.py             -> MessageFamily / AlignmentResult / FieldCandidate
BinaryInferno -> inference/binaryinferno_adapter.py      -> FieldCandidate / Evidence
NFStream      -> behavior/nfstream_adapter.py            -> BehaviorFeatures
Kaitai        -> exporters/kaitai.py                     -> schema/parser artifacts
LLM provider  -> llm/<provider>_adapter.py               -> ProtocolHypothesis
```

Third-party objects must not cross these adapter boundaries. Optional dependency failure is represented explicitly as `dependency_unavailable` and must not crash unrelated stages.

## 7. Desktop / Sidecar Boundary

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
Analysis Backend interface
   |
   +--> Track D deterministic/PRE producers
   +--> Track C evidence/verification producers
```

The sidecar exposes task-level operations rather than unrestricted shell access. Large binary payloads are referenced by controlled input IDs, offsets and result paths instead of being embedded in JSON messages.

### 7.1 Canonical sidecar methods

Protocol version 1 reserves this method vocabulary:

- `register_input` — register a controlled file/input reference and return an `inputRef`;
- `inspect_file` — obtain deterministic metadata/overview for one input;
- `analyze` — start configured analysis stages;
- `cancel_task` — cancel a known task;
- `get_result` — retrieve/reference the result of a known task;
- `read_range` — request a bounded byte range for Hex/offset UI use.

Do not invent synonyms such as `run_analysis` or pass arbitrary shell commands.

### 7.2 Canonical analysis configuration

The `analyze` request uses stable names for:

```text
inputRef
mode: baseline | evidencegraph
stages[]
llmEnabled
verificationEnabled
behaviorEnabled
timeoutSeconds
optionalDependencyPolicy: degrade | fail
```

A Track that needs a new shared option changes the schema/fixture first.

### 7.3 Task, status and event rules

- stdout contains protocol JSON only; diagnostics go to stderr;
- every message contains `protocolVersion` and a correlated task/message `id`;
- progress uses `event=progress`, a stage and `progress` in `[0,1]`;
- immediate responses use `event=status`, a canonical status stage and a stage-specific `data` object;
- `registered` and `inspected` expose only controlled metadata (`inputRef`, kind, size, SHA-256, basename and capability flags), not arbitrary raw paths;
- `range` returns at most 1 MiB of Base64 data with offset/length/EOF metadata;
- `task_status` uses `QUEUED | RUNNING | COMPLETED | PARTIAL | FAILED | CANCELLED`;
- errors use stable machine-readable error codes;
- result messages return `resultRef`, not a large result document inline;
- cancellation, timeout and sidecar failure remain explicit states.

Versioned contracts live in:
- `contracts/sidecar-message.schema.json`;
- `contracts/analysis-result.schema.json`;
- `contracts/agent-response.schema.json`.

### 7.4 Runtime implementation

The in-process runtime is `course_project.sidecar.runtime.SidecarRuntime`; JSONL stdio hosting is `course_project.sidecar.cli` and is available through `python -m course_project.sidecar` or the `course-project-sidecar` console script.

Input registration computes SHA-256 and creates a stable `input-<digest-prefix>` handle. The raw source path remains sidecar-internal. Optional configured roots can restrict which local files may be registered.

Task result files are stored below a controlled state root and exposed only through POSIX-style relative `resultRef` values such as:

```text
tasks/<task-id>/analysis-result.json
```

The default `MetadataOnlyBackend` deliberately returns `PARTIAL` with no protocol findings until the Track D/C orchestrator is injected. This gives Track B a real process/protocol to integrate against without falsely presenting mock analysis as scientific output.

## 8. Analysis Result and Artifact Manifest

`AnalysisResult` is the task-level summary. It contains findings plus small evidence records and references to potentially large artifacts.

Each finding can reference `evidenceIds` and a byte location. Evidence records carry provenance sufficient for the UI/reviewer to understand what produced the claim.

Large or structured views are advertised through `artifacts[]` entries:

```text
ArtifactRef
- artifactId
- type: evidence | packets | messages | alignment | statistics | behavior | restored | schema | report
- format: json | jsonl | parquet | csv | text | binary | ksy
- ref
- count (optional)
- metadata (optional)
```

This allows Track B to render Hex/alignment/statistics/behavior/evidence views without embedding large tables in the sidecar protocol. Artifact refs are controlled result-relative references, not arbitrary shell/file paths supplied by the WebView.

Track A's JSON protocol exporter accepts `VerifiedField` objects only and writes deterministic project-native schema output; Track C therefore does not need to expose verifier internals to the exporter.

## 9. Error Semantics

Common machine-readable categories:
- `invalid_input`;
- `insufficient_evidence`;
- `unsupported_format`;
- `dependency_unavailable`;
- `inference_failed`;
- `verification_failed`;
- `contract_version_mismatch`;
- `task_cancelled`;
- `sidecar_failed`.

Do not convert failures into empty successful results.

## 10. Confidence Semantics

Keep distinct:
- `model_confidence`;
- `evidence_score`;
- `verification_score`;
- `final_confidence` only when the fusion method is explicit.

A deterministic support ratio and an LLM self-reported probability are not interchangeable.

## 11. Contract Change Rule

For changes to `models.py`, `contracts/`, shared sidecar methods/config, or artifact semantics:

1. describe the old and new shape/behavior;
2. update schema and golden fixture first;
3. update `docs/architecture.md` when the semantic boundary changes;
4. update producer and consumers;
5. add compatibility/integration tests;
6. obtain the single required human review selected by `AGENTS.md`;
7. intentionally change `protocolVersion` when the change is incompatible.

## 12. Four-Track Ownership Boundary

- Track A (`@dddd2024`): shared contracts, sidecar, CI, integration/export.
- Track B (`@hinaLove1`): React/Tauri desktop and presentation layer.
- Track C (`@sunny1ce`): evidence graph, LLM hypotheses, executable verification, experiments.
- Track D (`@zhaohongjun20-creator`): deterministic binary/PRE/behavior feature producers.

Track B and Track D work packages were swapped on 2026-09-07; the account-to-track mapping did not change.

Cross-track dependencies must go through shared contracts instead of importing another Track's internal implementation.
