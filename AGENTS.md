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

Track B and Track D work packages were swapped on 2026-09-07. The mapping above is authoritative.

If the operator identity is not known, **do not guess**. Ask the human for the GitHub account or Track letter before making non-trivial edits.

## 2. Required read order

Before implementation, read in this order:

1. this `AGENTS.md`;
2. the matching `docs/tracks/track-<letter>.md`;
3. the current tracking Issue (`#12`, `#13`, `#14`, or `#15`) and linked/open sub-tasks when GitHub access is available;
4. `docs/architecture.md`;
5. the design document(s) named by the Track entrypoint;
6. the existing code/tests in the owned paths.

For Track C also read `docs/design-v2.md` and `docs/research-roadmap.md`. For Track B also read `docs/desktop-app-guide.md`. Track D should read both `docs/design-v1.md` and the V2 evidence interface sections because its outputs feed Track C.

## 3. Authority and conflict rule

When instructions disagree, use this order:

1. explicit current human request;
2. current GitHub tracking Issue / accepted project decision;
3. this file and the matching Track entrypoint;
4. `docs/architecture.md` and versioned contracts;
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

- `contracts/`;
- `src/course_project/models.py`;
- `docs/architecture.md`;
- `src/course_project/sidecar/` protocol surface;
- `.github/workflows/`;
- root dependency/build configuration.

For changes to a shared interface:

1. describe old and new contract;
2. update schema/fixture/documentation first where applicable;
3. update producer and consumers;
4. add compatibility/integration tests;
5. request Track A review plus at least one affected consumer/producer owner.

Do not let third-party library objects leak across project-native contracts.

## 6. Project safety and scientific boundaries

This project is for coursework, controlled datasets, and authorized laboratory traffic only.

- Do not add features aimed at unauthorized access, credential theft, persistence, destructive behavior, or unrestricted shell execution.
- Do not claim that modern correctly implemented cryptography can be recovered without keys.
- LLM output is a hypothesis source, never protocol ground truth.
- Accepted protocol-semantic claims must retain evidence and verification records.
- The inference pipeline must not read evaluation ground truth.
- Do not commit private traffic, credentials, test keys, restored sensitive plaintext, or secrets.

## 7. Working protocol for every AI task

Before coding, state internally or in the task record:

- operator / Track;
- tracking Issue;
- owned paths being changed;
- shared interfaces affected, if any;
- acceptance criteria to satisfy.

Then:

1. start from current `main`;
2. use a task-sized branch (`track-a/...`, `track-b/...`, `track-c/...`, `track-d/...`, `fix/...`, `docs/...`, or `experiment/...`);
3. implement the smallest coherent change;
4. add/update tests and fixtures;
5. run relevant local checks;
6. open a PR linked to the Issue;
7. report evidence, known limitations, and interface changes in the PR.

Do not use one long-lived personal branch for unrelated work.

## 8. Definition of done

A task is not done merely because code was written. A Track task is done when:

- the stated Issue acceptance criterion is met;
- tests/fixtures cover the changed behavior;
- shared contracts remain compatible or are explicitly migrated;
- CI is green;
- docs/examples are updated when behavior or usage changed;
- the PR makes ownership and limitations clear.

## 9. Track entrypoints

- Track A: [`docs/tracks/track-a.md`](docs/tracks/track-a.md)
- Track B: [`docs/tracks/track-b.md`](docs/tracks/track-b.md)
- Track C: [`docs/tracks/track-c.md`](docs/tracks/track-c.md)
- Track D: [`docs/tracks/track-d.md`](docs/tracks/track-d.md)

The detailed four-person division remains in [`docs/team-division.md`](docs/team-division.md). CODEOWNERS remains the path-level review map, while tracking Issues remain the current execution truth.

## 10. Tool compatibility

`AGENTS.md` is the single source of truth. Thin compatibility files route common coding agents here without duplicating the ownership map:

- GitHub Copilot: `.github/copilot-instructions.md`
- Claude Code: `CLAUDE.md`
- Gemini CLI: `GEMINI.md`

Human handoff guidance and the recommended startup prompt are documented in [`docs/ai-collaboration.md`](docs/ai-collaboration.md). If a tool does not automatically read any of these files, explicitly tell it to read `AGENTS.md` first.