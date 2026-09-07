# Track B — Desktop App / Visualization / Packaging / Demo

Owner: `@hinaLove1`  
Primary tracking Issue: `#13`

## Mission

Build the local desktop workbench that makes the analysis pipeline inspectable and reproducible without duplicating protocol-inference logic in the UI or Rust shell.

## Read first

1. `AGENTS.md`
2. Issue `#13`
3. `docs/desktop-app-guide.md`
4. `docs/architecture.md`
5. `contracts/README.md`
6. `contracts/sidecar-message.schema.json`
7. `contracts/analysis-result.schema.json`
8. `contracts/agent-response.schema.json`
9. `docs/team-division.md`

## Primary owned paths

- `apps/desktop/src/`
- `apps/desktop/src-tauri/`
- desktop-facing fixtures/examples
- desktop-facing parts of `contracts/` only through the shared-contract review process
- `examples/` for reproducible UI/demo flows

## Primary responsibilities

- React + TypeScript interface;
- Tauri 2 / Rust shell;
- controlled local file selection and range reads;
- task lifecycle and Python sidecar integration;
- progress/error/result presentation;
- overview, hex, statistics, alignment, behavior, field and evidence views;
- finding-to-byte-offset navigation;
- packaging and clean-machine demo workflow.

## Frozen contract assumptions

Track B should generate/derive types from the shared contracts rather than inventing UI-specific transport shapes.

Canonical sidecar methods are:

- `register_input`;
- `inspect_file`;
- `analyze`;
- `cancel_task`;
- `get_result`;
- `read_range`.

Semantic finding status is `ACCEPTED / REJECTED / UNCERTAIN`.

`AnalysisResult` provides:
- findings with `evidenceIds` and byte locations;
- small `evidence[]` provenance records;
- `artifacts[]` references for messages, alignment, statistics, behavior, restored output, schema/report and other large views.

Do not require the Python sidecar to inline large packet/alignment tables in JSON messages.

## Inputs

Consume only project-native/versioned interfaces from Track A. Typical inputs include task progress, analysis summaries, evidence records, byte locations, behavior predictions and controlled artifact references.

## Outputs

- typed desktop commands/events;
- stable UI state models derived from contracts;
- reproducible desktop demo and package configuration;
- integration defects reported back to Track A instead of silently changing Python internals.

## Do not own by default

- `src/course_project/io/`, `features/`, `boundary/`, `inference/`, `behavior/` (Track D);
- `evidence/`, `llm/`, `verification/`, experiment logic (Track C);
- sidecar protocol or shared model changes without Track A review.

## First implementation sequence

1. create React/Tauri scaffold + lockfiles;
2. consume the golden sidecar/result fixtures in a fixed-data contract spike;
3. implement controlled `.dat` selection/registration and `read_range`-based overview/hex view;
4. implement task progress/error/result flow;
5. render findings/evidence/artifact-backed inference and behavior views;
6. add desktop CI and packaging/clean-machine rehearsal.

## Completion standard

A UI feature is complete only when it consumes a stable contract/fixture, exposes failure states, links conclusions back to evidence/offsets where applicable, and does not invent protocol facts in the presentation layer.
