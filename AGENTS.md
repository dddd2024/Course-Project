# AGENTS.md — AI Collaboration Entry Point

This is the first repository instruction for AI coding agents working on this four-person cybersecurity course project.

## 1. Identify the operator

| GitHub account | Track | Issue | Responsibility |
|---|---|---:|---|
| `@dddd2024` | A | `#12` | integration, shared contracts, sidecar, CI, export, end-to-end |
| `@hinaLove1` | B | `#13` | React/Tauri desktop, visualization, packaging, final demo |
| `@sunny1ce` | C | `#14` + research `#9` | EvidenceGraph-PRE, LLM reasoning, executable verification, experiments |
| `@zhaohongjun20-creator` | D | `#15` | binary analysis, packet boundaries, protocol inference, behavior features |

Track B and Track D work packages were swapped on 2026-09-07. The mapping above is authoritative.

If the operator identity is unknown, do not guess before making non-trivial edits.

## 2. Read order

Before implementation, read:

1. `AGENTS.md`;
2. the matching `docs/tracks/track-<letter>.md`;
3. the current tracking Issue;
4. `docs/architecture.md`;
5. relevant design/contracts/tests in the owned paths.

Also read `docs/dependency-register.md` for dependency work, `contracts/README.md` for shared-contract work, and `docs/repository-settings.md` for merge governance.

## 3. Authority and ownership

When instructions disagree, use this order:

1. explicit current human request;
2. current GitHub tracking Issue / accepted project decision;
3. this file and the matching Track entrypoint;
4. architecture and versioned contracts;
5. older design/README notes.

Agents may inspect the whole repository but should implement primarily in their Track's owned paths. Cross-Track edits should be narrow and justified by an actual shared-interface or blocking integration need.

## 4. Shared interfaces

These are shared/high-risk surfaces:

- `contracts/` and golden fixtures;
- `src/course_project/models.py`;
- `docs/architecture.md`;
- `src/course_project/sidecar/` protocol surface;
- `.github/workflows/`;
- root dependency/build/environment configuration.

For a shared-interface change, document the old/new behavior, update producer/consumer tests and fixtures as needed, and make the change explicit in the PR. Do not silently change a frozen contract.

### Frozen Day-0 names

Semantic decisions:
- JSON / TypeScript / Rust / UI: `ACCEPTED`, `REJECTED`, `UNCERTAIN`;
- Python internal: `accepted`, `rejected`, `uncertain`.

Sidecar v1 methods:
- `register_input`;
- `inspect_file`;
- `analyze`;
- `cancel_task`;
- `get_result`;
- `read_range`.

D→C project-native DTOs:
- `InputMetadata`;
- `PacketCandidate` / `MessageCandidate`;
- `MessageFamily`;
- `AlignmentRegion` / `AlignmentResult`;
- `FieldCandidate`;
- `BehaviorFeatures`.

Desktop-facing result linkage:
- findings use `evidenceIds`;
- provenance lives in `evidence[]`;
- large views/results use `artifacts[]` refs.

## 5. Environment, dependency and safety rules

- Follow `.python-version`, `.nvmrc`, `rust-toolchain.toml` and `docs/development-environment.md`.
- Baseline CI must work without real model credentials; use the mock/offline LLM path.
- Register new dependencies in `docs/dependency-register.md` with version, license, environment constraints and fallback behavior.
- Do not leak third-party library objects across project-native contracts.
- Missing optional analyzers should degrade clearly instead of crashing unrelated stages.
- Do not commit secrets, private traffic, prohibited teacher data or sensitive plaintext.
- LLM output is a hypothesis source, not protocol ground truth.
- Accepted semantic claims must retain evidence and verification records.

## 6. Working protocol

For each task:

1. identify Track / Issue / owned paths;
2. start from current `main`;
3. use a task-sized branch;
4. implement the smallest coherent change;
5. add/update relevant tests and fixtures;
6. open a PR linked to the Issue;
7. record important limitations, contract changes and dependency changes.

Do not use one long-lived personal branch for unrelated work.

## 7. Review governance — three gates only

A PR can merge only when all three gates are green:

### Gate 1 — one valid human approval

Exactly one approving human review is the minimum merge approval.

Who should approve:
- ordinary Track-internal PR: any other team member;
- shared-interface or cross-Track PR: Track A (`@dddd2024`);
- Track A-authored shared/cross-Track PR: one affected Track owner, because the author cannot self-approve.

Extra affected-owner review may be requested when useful, but it is advisory unless the PR explicitly changes that owner's contract surface.

Automated Codex/GitHub review is advisory. It can discover real defects, but it is not an additional approval layer. Valid blocking findings must still be fixed or explicitly resolved before merge.

### Gate 2 — current PR version has full green CI

After the last code change, the current PR version must pass all blocking CI jobs:

- `test (3.10)`;
- `test (3.11)`;
- `windows-integration`;
- `merge-gate`.

If new commits are pushed, previous CI evidence no longer counts. Authors do not need to manually record SHAs or copy check results into the PR; the merge actor/agent must verify the current PR state immediately before merge.

### Gate 3 — no unresolved blocking review issue

Before merge:
- no active `CHANGES_REQUESTED` review may remain;
- blocking review threads must be resolved;
- the PR must have no merge conflict.

That is the complete governance model: **right reviewer + green CI + no unresolved blocker**.

Do not add extra approval layers unless a specific PR documents why they are needed.

## 8. Merge behavior

Preferred merge method: **squash merge**.

Immediately before merging, the human or AI merge actor should fresh-read the PR and verify the three gates above. This exact-head/base synchronization checking is an implementation detail of the merge actor; PR authors should not manage it manually.

If `main` changed and the PR needs synchronization to obtain valid CI or remove a conflict, update the branch and rerun CI. Do not merge using an older green run.

## 9. Definition of done

A task is done when:

- its Issue acceptance criterion is met;
- relevant tests/fixtures cover the changed behavior;
- shared contracts remain compatible or are explicitly migrated;
- dependency/docs records are updated when applicable;
- the three merge gates pass.

## 10. Track entrypoints

- Track A: `docs/tracks/track-a.md`
- Track B: `docs/tracks/track-b.md`
- Track C: `docs/tracks/track-c.md`
- Track D: `docs/tracks/track-d.md`

`AGENTS.md` is the single source of truth for coding agents. Compatibility files (`.github/copilot-instructions.md`, `CLAUDE.md`, `GEMINI.md`) should route agents here rather than duplicate governance.