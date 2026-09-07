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

Ownership defines implementation responsibility; it is not a merge-approval mechanism.

## 4. Shared interfaces

Shared/high-risk surfaces include:

- `contracts/` and golden fixtures;
- `src/course_project/models.py`;
- `docs/architecture.md`;
- `src/course_project/sidecar/` protocol surface;
- `.github/workflows/`;
- root dependency/build/environment configuration.

For a shared-interface change, document the old/new behavior, update schemas/fixtures and producer/consumer tests as needed, and make the migration explicit in the PR. Do not silently change a frozen contract.

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

## 7. Merge governance — CI only

There is **no required human review, approval, Code Owner approval, review-thread resolution, or `CHANGES_REQUESTED` gate**.

A PR may merge when all of the following CI-validity conditions hold:

- the PR is mechanically mergeable with the current `main` (no merge conflict);
- the current PR head is the version being evaluated;
- GitHub has evaluated that current head against the current `main`;
- every blocking CI job for that current merge result has completed with `success`:
  - `test (3.10)`;
  - `test (3.11)`;
  - `windows-integration`;
  - `merge-gate`;
- no blocking CI job is queued, in progress, failed, cancelled, timed out, action-required, stale, or otherwise non-successful.

If the PR head changes, or `main` changes after the valid CI run, previous CI evidence does not authorize merge. Retrigger CI and validate the new pull-request merge result.

A literal merge/rebase of `main` into every feature branch is not required solely for governance. GitHub pull-request CI on the current head is sufficient when its synthetic merge result uses the current `main`. If base metadata is stale or ambiguous, verify the synthetic merge commit parents before treating the run as current.

Merge authorization is serialized: do not merge multiple PRs concurrently against the same validated `main` snapshot. Once one PR changes `main`, all other previously green PRs must be re-evaluated before merge. If `main` changes between final validation and the merge action, abort that authorization and retrigger CI.

Automated or human comments may still be used as optional engineering feedback, but they never block merge. Do not request approval as a merge requirement.

`merge-gate` must depend on every blocking CI job. If a new blocking job is added, add it to `merge-gate.needs` in the same change.

The repository ruleset is intentionally disabled by current project-owner decision. Do not re-enable or replace it unless the owner explicitly changes that decision. Disabled server enforcement never makes CI optional.

## 8. Merge behavior

Preferred merge method: **squash merge**.

Immediately before merging, the merge actor/agent fresh-reads the current PR/head, current `main`, tested merge result, and blocking CI conclusions. PR authors do not need to copy SHAs or check results into the PR description.

**Once those CI-only conditions are satisfied, merge promptly. Do not leave a green PR waiting for review, approval, discussion, or owner acknowledgement.**

## 9. Definition of done

A task is done when:

- its Issue acceptance criterion is met;
- relevant tests/fixtures cover the changed behavior;
- shared contracts remain compatible or are explicitly migrated;
- dependency/docs records are updated when applicable;
- current-version CI is fully green.

## 10. Track entrypoints

- Track A: `docs/tracks/track-a.md`
- Track B: `docs/tracks/track-b.md`
- Track C: `docs/tracks/track-c.md`
- Track D: `docs/tracks/track-d.md`

`AGENTS.md` is the single source of truth for coding agents. Compatibility files (`.github/copilot-instructions.md`, `CLAUDE.md`, `GEMINI.md`) should route agents here rather than duplicate governance.
