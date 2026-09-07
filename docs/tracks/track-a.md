# Track A — Integration / Contracts / Sidecar / CI

Owner: `@dddd2024`  
Primary tracking Issue: `#12`

## Mission

Keep the four-track system coherent and runnable. Track A owns the boundaries between components rather than taking over the internal algorithms of Tracks B/C/D.

## Read first

1. `AGENTS.md`
2. Issue `#12` and linked blockers
3. `docs/architecture.md`
4. `docs/design-v1.md`
5. `docs/design-v2.md`
6. `docs/testing-plan.md`
7. `docs/team-division.md`

## Primary owned paths

- `contracts/`
- `src/course_project/models.py`
- `src/course_project/sidecar/`
- `src/course_project/exporters/`
- `.github/workflows/`
- integration/E2E tests and shared fixtures
- architecture/integration documentation

## Primary responsibilities

- maintain project-native shared contracts;
- keep V1 runnable while V2 research evolves;
- define and version the Python sidecar task/progress/error/result protocol;
- integrate verified fields into JSON/Kaitai/parser outputs;
- maintain CI and end-to-end smoke tests;
- coordinate cross-track contract migrations;
- freeze reproducible demo/release state.

## Inputs

- Track D: packet candidates, field candidates, deterministic features/behavior features;
- Track C: evidence/hypotheses/verification/accepted fields;
- Track B: desktop contract requirements and integration failures.

## Outputs

- stable schemas and Python models;
- sidecar responses/events;
- exporter artifacts;
- CI gates and E2E evidence;
- integration decisions documented for all affected tracks.

## Do not own by default

- protocol inference algorithms in Track D;
- EvidenceGraph/LLM/verifier internals in Track C;
- React/Tauri feature implementation in Track B.

## Immediate completion standard

A Track A change should leave `main` green, preserve or migrate shared contracts explicitly, and demonstrate that at least one producer and one consumer agree on the changed interface.