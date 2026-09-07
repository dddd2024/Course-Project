# Track A — Integration / Contracts / Sidecar / CI

Owner: `@dddd2024`  
Primary tracking Issue: `#12`

## Mission

Keep the four-track system coherent and runnable. Track A owns the boundaries between components rather than taking over the internal algorithms of Tracks B/C/D.

## Read first

1. `AGENTS.md`
2. Issue `#12` and linked blockers
3. `docs/architecture.md`
4. `contracts/README.md`
5. `docs/design-v1.md`
6. `docs/design-v2.md`
7. `docs/testing-plan.md`
8. `docs/team-division.md`

## Primary owned paths

- `contracts/`
- `src/course_project/models.py`
- `src/course_project/sidecar/`
- `src/course_project/exporters/`
- `.github/workflows/`
- integration/E2E tests and shared fixtures
- architecture/integration documentation

## Primary responsibilities

- maintain project-native shared contracts and normalized cross-Track DTOs;
- keep V1 runnable while V2 research evolves;
- implement/version the Python sidecar against the frozen v1 method/config vocabulary;
- maintain `AnalysisResult` evidence/artifact references used by the desktop;
- integrate verified fields into JSON/Kaitai/parser outputs;
- maintain CI and end-to-end smoke tests;
- coordinate cross-track contract migrations;
- freeze reproducible demo/release state.

## Frozen Day-0 contract baseline

Do not rename these without a contract-change PR:

- decision states: `ACCEPTED / REJECTED / UNCERTAIN` externally and lowercase equivalents internally;
- sidecar methods: `register_input`, `inspect_file`, `analyze`, `cancel_task`, `get_result`, `read_range`;
- D→C DTO families: `InputMetadata`, `MessageCandidate`, `MessageFamily`, `AlignmentRegion`, `AlignmentResult`, `FieldCandidate`, `BehaviorFeatures`;
- result linkage: `findings[].evidenceIds`, `evidence[]`, and `artifacts[]`.

## Inputs

- Track D: packet/message/family/alignment/field candidates and deterministic behavior features through project-native DTOs;
- Track C: evidence/hypotheses/verification/accepted fields;
- Track B: desktop contract requirements and integration failures.

## Outputs

- stable schemas and Python models;
- sidecar responses/events;
- controlled result/artifact references;
- exporter artifacts;
- CI gates and E2E evidence;
- integration decisions documented for all affected tracks.

## Do not own by default

- protocol inference algorithms in Track D;
- EvidenceGraph/LLM/verifier internals in Track C;
- React/Tauri feature implementation in Track B.

## First implementation sequence

1. implement a sidecar runtime skeleton that validates/handles the frozen v1 command vocabulary;
2. consume golden fixtures in an integration smoke path;
3. establish producer/consumer serialization for `AnalysisResult` and artifact refs;
4. integrate Track D/C outputs without importing their internal implementations;
5. expand CI as runnable desktop/sidecar components land.

## Immediate completion standard

A Track A change should leave CI green, preserve or migrate shared contracts explicitly, and demonstrate that at least one producer and one consumer agree on the changed interface.
