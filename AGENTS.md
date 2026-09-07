# AGENTS.md — AI Collaboration Entry Point

This file is the first repository instruction for AI coding agents working on this project.

The repository is a four-person cybersecurity course project. Work is intentionally split into four ownership tracks so multiple people and their AI agents can work in parallel without silently changing each other's modules.

## 1. Identify the operator before editing

Map the current human operator to exactly one track:

| GitHub account | Track | Primary tracking issue | Responsibility |
|---|---|---:|---|
| `@dddd2024` | A | `#12` | integration, shared contracts, sidecar, CI, export, end-to-end |
| `@hinaLove1` | B | `#13` | React/Tauri desktop, visualization, packaging, final demo |
| `@sunny1ce` | C | `#14` plus research umbrella `#9` | EvidenceGraph-PRE, LLM reasoning, executable verification, experiments |
| `@zhaohongjun20-creator` | D | `#15` | binary analysis, packet boundaries, protocol inference, behavior features |

Track B and Track D work packages were swapped on 2026-09-07. The mapping above is authoritative. All four accounts have collaboration access.

If the operator identity is not known, **do not guess**. Ask the human for the GitHub account or Track letter before making non-trivial edits.

## 2. Required read order

Before implementation, read in this order:

1. this `AGENTS.md`;
2. the matching `docs/tracks/track-<letter>.md`;
3. the current tracking Issue (`#12`, `#13`, `#14`, or `#15`) and linked/open sub-tasks when GitHub access is available;
4. `docs/architecture.md`;
5. the design document(s) named by the Track entrypoint;
6. the existing code/tests in the owned paths.

Also read the following when relevant:

- environment/build/dependency work: `docs/development-environment.md` and `docs/dependency-register.md`;
- shared contract work: `contracts/README.md` and `contracts/fixtures/`;
- final integration/demo work: `docs/delivery-checklist.md`;
- repository governance: `docs/repository-settings.md` and `docs/pre-implementation-readiness.md`.

For Track C also read `docs/design-v2.md` and `docs/research-roadmap.md`. For Track B also read `docs/desktop-app-guide.md`. Track D should read both `docs/design-v1.md` and the V2 evidence interface sections because its outputs feed Track C.

## 3. Authority and conflict rule

When instructions disagree, use this order:

1. explicit current human request;
2. current GitHub tracking Issue / accepted project decision;
3. this file and the matching Track entrypoint;
4. `docs/architecture.md`, versioned contracts and repository readiness rules;
5. V1/V2 design and roadmap documents;
6. README and older historical notes.

Do not silently resolve a real contract conflict. Record it in the PR/Issue and request the affected owner review.

## 4. Stay inside the assigned Track

An agent may inspect the whole repository, but should implement primarily in the Track's owned paths.

Do **not** take over another Track merely because it is convenient. Cross-track work is allowed only when one of these is true:

- the current task explicitly requires a shared-interface change;
- the owning Track requested support;
- a blocking defect cannot be fixed without a narrow cross-track change and the PR documents it.

When cross-track work is required, keep it minimal and preserve the owning Track's design.

## 5. Shared/high-risk interfaces

The following are shared contracts, not private implementation details:

- `contracts/` and its golden fixtures;
- `src/course_project/models.py`;
- `docs/architecture.md`;
- `src/course_project/sidecar/` protocol surface;
- `.github/workflows/`;
- root dependency/build/environment configuration.

For changes to a shared interface:

1. describe old and new contract;
2. update schema + golden fixture + documentation first where applicable;
3. update producer and consumers;
4. add compatibility/integration tests;
5. request Track A review plus at least one affected consumer/producer owner.

Do not let third-party library objects leak across project-native contracts.

### 5.1 Frozen Day-0 names

Unless a shared-contract PR intentionally changes them, agents must use these exact names:

**Semantic decisions**
- JSON/TypeScript/Rust/UI: `ACCEPTED`, `REJECTED`, `UNCERTAIN`;
- Python internal: `accepted`, `rejected`, `uncertain`.

Do not introduce `ACCEPT`, `REJECT`, or `UNSURE` as enum values.

**Sidecar v1 methods**
- `register_input`;
- `inspect_file`;
- `analyze`;
- `cancel_task`;
- `get_result`;
- `read_range`.

Do not invent aliases such as `run_analysis` for convenience.

**D→C project-native DTOs**
- `InputMetadata`;
- `PacketCandidate` / `MessageCandidate`;
- `MessageFamily`;
- `AlignmentRegion` / `AlignmentResult`;
- `FieldCandidate`;
- `BehaviorFeatures`.

**Desktop-facing result linkage**
- findings link through `evidenceIds`;
- small provenance records live in `evidence[]`;
- large views/results are advertised through `artifacts[]` references.

## 6. Environment, LLM and dependency rules

- Canonical local baseline is defined by `.python-version`, `.nvmrc`, `rust-toolchain.toml` and `docs/development-environment.md`.
- CI/offline development must work without a real model credential; `.env.example` defaults to `COURSE_PROJECT_LLM_PROVIDER=mock`.
- Never make baseline CI depend on a paid/cloud LLM call.
- Before introducing a third-party runtime/research dependency, update `docs/dependency-register.md` with exact upstream/version/license/environment/adapter/fallback information.
- If third-party source, data, model assets or substantial examples are copied or redistributed, update `THIRD_PARTY_NOTICES.md` before merge.
- Missing optional analyzers should surface a clear `dependency_unavailable`/degraded state rather than crash unrelated pipeline stages.

## 7. Project safety, data and scientific boundaries

This project is for coursework, teacher-provided evaluation data, controlled datasets, and authorized laboratory traffic only.

- Do not add features aimed at unauthorized access, credential theft, persistence, destructive behavior, or unrestricted shell execution.
- Do not claim that modern correctly implemented cryptography can be recovered without keys.
- LLM output is a hypothesis source, never protocol ground truth.
- Accepted protocol-semantic claims must retain evidence and verification records.
- The inference pipeline must not read evaluation ground truth.
- Teacher-provided raw `.dat` / `.bin` files remain local unless redistribution is explicitly allowed.
- Do not commit private traffic, credentials, test keys, prohibited teacher data, restored sensitive plaintext, or secrets.
- Synthetic contract/unit/mechanism fixtures may be committed but must not be presented as formal course benchmark results.

## 8. Working protocol for every AI task

Before coding, state internally or in the task record:

- operator / Track;
- tracking Issue;
- owned paths being changed;
- shared interfaces affected, if any;
- dependency/environment changes, if any;
- acceptance criteria to satisfy.

Then:

1. start from current `main`;
2. use a task-sized branch (`track-a/...`, `track-b/...`, `track-c/...`, `track-d/...`, `fix/...`, `docs/...`, or `experiment/...`);
3. implement the smallest coherent change;
4. add/update tests and fixtures;
5. run relevant local checks;
6. open a PR linked to the Issue;
7. report evidence, known limitations, environment/dependency changes and interface changes in the PR.

### 8.1 Hard merge gate

No human or AI agent may merge a PR until the latest CI run for the PR's **current head SHA** is completely green.

Immediately before any merge action, fresh-read the PR head SHA and its current CI/check results. A merge is allowed only when:

- every blocking CI job for that exact head has completed with `success`;
- the final `merge-gate` job has completed with `success`;
- no CI job is queued, in progress, failed, cancelled, timed out, action-required, stale, or otherwise non-successful;
- no newer commit has been pushed after the verified run;
- required reviews, Code Owner approval, and conversation-resolution conditions are also satisfied.

Never use an older green commit, `mergeable=true`, partial CI success, or a deadline as justification to merge. If the head changes, discard the previous merge authorization and re-check CI from scratch. If a new blocking CI job is added to `.github/workflows/ci.yml`, add it to `merge-gate.needs` in the same PR.

Repository settings should additionally require the emitted CI check names on `main`; see `docs/repository-settings.md`. Until branch protection/rulesets are enabled, this instruction remains a mandatory fail-closed operating rule for every project agent.

Do not use one long-lived personal branch for unrelated work.

## 9. Definition of done

A task is not done merely because code was written. A Track task is done when:

- the stated Issue acceptance criterion is met;
- tests/fixtures cover the changed behavior;
- shared contracts remain compatible or are explicitly migrated;
- dependency/version/license records are updated when applicable;
- all blocking CI is green for the current PR head and `merge-gate` is green before merge;
- docs/examples are updated when behavior or usage changed;
- the PR makes ownership and limitations clear.

## 10. Track entrypoints

- Track A: [`docs/tracks/track-a.md`](docs/tracks/track-a.md)
- Track B: [`docs/tracks/track-b.md`](docs/tracks/track-b.md)
- Track C: [`docs/tracks/track-c.md`](docs/tracks/track-c.md)
- Track D: [`docs/tracks/track-d.md`](docs/tracks/track-d.md)

The detailed four-person division remains in [`docs/team-division.md`](docs/team-division.md). CODEOWNERS remains the path-level review map, while tracking Issues remain the current execution truth.

## 11. Tool compatibility

`AGENTS.md` is the single source of truth. Thin compatibility files route common coding agents here without duplicating the ownership map:

- GitHub Copilot: `.github/copilot-instructions.md`
- Claude Code: `CLAUDE.md`
- Gemini CLI: `GEMINI.md`

Human handoff guidance and the recommended startup prompt are documented in [`docs/ai-collaboration.md`](docs/ai-collaboration.md). If a tool does not automatically read any of these files, explicitly tell it to read `AGENTS.md` first.
