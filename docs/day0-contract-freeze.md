# Day-0 Contract Freeze

> Status: implementation-start baseline. This document summarizes names that four Tracks and their AI agents may rely on before deep integration begins.

## 1. Decision states

One conceptual state machine is used everywhere:

- `ACCEPTED` / Python `accepted`;
- `REJECTED` / Python `rejected`;
- `UNCERTAIN` / Python `uncertain`.

Legacy `ACCEPT`, `REJECT`, and `UNSURE` are not enum values.

## 2. D -> C intermediate DTOs

Defined in `src/course_project/models.py`:

- `InputMetadata`;
- `PacketCandidate`;
- `MessageCandidate`;
- `MessageFamily`;
- `AlignmentRegion`;
- `AlignmentResult`;
- `FieldCandidate`;
- `BehaviorFeatures`;
- `Evidence` for provenance-tagged observations.

Third-party objects from Netzob, BinaryInferno, Scapy, NFStream, model SDKs, or UI frameworks do not cross Track boundaries.

## 3. A <-> B sidecar v1

Canonical methods:

- `register_input`;
- `inspect_file`;
- `analyze`;
- `cancel_task`;
- `get_result`;
- `read_range`.

Canonical `analyze` config names:

- `inputRef`;
- `mode`;
- `stages`;
- `llmEnabled`;
- `verificationEnabled`;
- `behaviorEnabled`;
- `timeoutSeconds`;
- `optionalDependencyPolicy`.

The schema in `contracts/sidecar-message.schema.json` is authoritative.

## 4. Analysis result linkage

`AnalysisResult` uses three layers:

1. `findings[]` — user-facing claims, statuses, byte locations and `evidenceIds`;
2. `evidence[]` — small provenance records that explain claims;
3. `artifacts[]` — controlled references to larger messages/alignment/statistics/behavior/restored/schema/report outputs.

Large binary/table payloads are not embedded into sidecar JSON.

## 5. Evaluation data

Teacher-provided `.dat` is the authoritative course evaluation input. Synthetic data may be used for unit/integration/verifier/mechanism experiments and must be explicitly labeled as synthetic. It is not a substitute for teacher-data benchmark results.

## 6. Change process

A breaking or semantic change to any item above requires:

1. schema/model/document change;
2. golden fixture update;
3. tests;
4. producer/consumer migration notes;
5. Track A plus affected Track review;
6. protocol version change when compatibility is broken.
