# Repository Settings Baseline

This document defines the repository-level merge policy for `main`.

## 1. Single merge rule

> **Current-version CI fully green = mergeable.**

There is no required human approval, Code Owner approval, review-thread resolution, or `CHANGES_REQUESTED` gate.

The only governance gate is CI validity for the version that would actually merge into current `main`.

## 2. Blocking CI checks

The blocking checks are:

- `test (3.10)`;
- `test (3.11)`;
- `windows-integration`;
- `merge-gate`.

`merge-gate` is the final aggregate job and must depend on every blocking CI job. Whenever a new blocking job is introduced, it must also be added to `merge-gate.needs` in the same change.

A PR may merge only when:

1. it has no merge conflict;
2. its current head is the version being evaluated;
3. GitHub has evaluated that head against the current `main`;
4. all four blocking checks above have completed with `success` for that current merge result;
5. no blocking job is queued, in progress, failed, cancelled, timed out, action-required, stale, or otherwise non-successful.

A green run for an older head or an older `main` is not merge evidence. If the PR head or `main` changes after the valid run, retrigger CI before merging.

A literal merge/rebase of `main` into every feature branch is **not** required solely for governance. A GitHub pull-request CI run on the current head is sufficient when its synthetic merge result is built from the current `main`. If GitHub metadata is ambiguous or stale, the merge actor should verify the synthetic merge commit parents before treating the run as current.

## 3. Server enforcement state

Project-owner decision on 2026-09-07: repository ruleset `main-protection` is intentionally **disabled**.

This is an explicit project setting, not a pending configuration task. Agents must not re-enable, replace, or strengthen the ruleset unless the project owner explicitly changes this decision.

Consequences:

- GitHub does not server-enforce human approvals;
- GitHub does not server-enforce the four CI checks;
- GitHub may technically allow an unchecked merge or direct update that the project process forbids;
- therefore the human or AI merge actor must fail closed and enforce the CI-only rule before every merge.

The repository workflow still uses task-sized branches and pull requests so CI has a reproducible merge candidate, changes remain attributable, and squash merges remain reversible. Ruleset-disabled does **not** mean CI-optional and does not authorize bypassing the PR workflow for ordinary development.

`.github/CODEOWNERS` is intentionally absent because ownership lives in `AGENTS.md` and is not an approval mechanism.

## 4. CI platform baseline

CI has three layers:

1. Ubuntu Python matrix: `test (3.10)` and `test (3.11)`;
2. `windows-integration`: Python 3.11 + Node 22 + Rust/Tauri validation on the target desktop OS;
3. `merge-gate`: final aggregate result.

The workflow runs both on PRs targeting `main` and on pushes to `main`. PR CI is the pre-merge authorization evidence. `main` push CI is a post-merge safety net that detects an integration regression if a manual/concurrent merge slips past process discipline; a post-merge green run does not retroactively make a stale pre-merge decision correct.

The Windows job may include additional integration checks, such as the Tauri -> Python Sidecar round-trip. Such checks are part of `windows-integration`; they do not create a separate human gate.

A signed/package installer build is a release/demo gate, not a requirement for every PR.

## 5. Merge behavior

Preferred method: **squash merge**.

Immediately before merge, the human or AI merge actor must fresh-read:

- the PR state and current head;
- the current `main` head;
- the current pull-request CI run / tested merge result;
- all blocking CI job conclusions.

No manual review-state check is required.

Merges must be serialized by process: do not authorize two PRs for merge against the same `main` snapshot and then merge them concurrently. After one PR changes `main`, every other previously green PR must be re-evaluated against the new `main` before it merges. If `main` changes between the final validation and the merge action, abort that authorization and retrigger CI.

PR authors do not need to copy SHAs or job results into PR descriptions. Exact head/base validity is handled by the merge actor/agent.

When the CI-only conditions are satisfied, merge promptly. A green PR must not remain open merely waiting for a reviewer, owner acknowledgement, or discussion resolution.

## 6. Permissions and secrets

All four collaborators may create branches and PRs. Ownership boundaries in `AGENTS.md` define responsibility but do not add merge approvals.

Baseline CI requires no repository secret. Real model credentials remain local or in an approved secret store. Never expose credentials through fixtures, logs, screenshots, Actions output or demo recordings.

## 7. Server-truth checkpoint

Fresh server truth on 2026-09-07:

- ruleset ID: `22429560`;
- name: `main-protection`;
- target: branch/default-branch scope;
- enforcement: **disabled**.

This disabled state matches the current project-owner decision. It should be treated as intentional until the owner explicitly changes it.

Because server enforcement is disabled, repository governance tests and `AGENTS.md` exist to keep agents consistent, but they are not substitutes for checking CI immediately before merge. Never infer permission to merge from `mergeable=true` alone.