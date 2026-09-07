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
3. it is synchronized with current `main` whenever `main` changed after the last valid evaluation;
4. all four blocking checks above have completed with `success` for that current version;
5. no blocking job is queued, in progress, failed, cancelled, timed out, action-required, stale, or otherwise non-successful.

A green run for an older head or an outdated base is not merge evidence. If the head or relevant base changes, synchronize and rerun CI.

## 3. Required GitHub `main` ruleset

Target configuration:

- require a pull request before merging;
- **required approving reviews: 0**;
- **Code Owner review: disabled**;
- **review-thread resolution: disabled**;
- **extra approval for unattributed changes: disabled**;
- do not make `CHANGES_REQUESTED` a merge gate;
- require these status checks:
  - `test (3.10)`;
  - `test (3.11)`;
  - `windows-integration`;
  - `merge-gate`;
- require the tested branch/merge result to be up to date with `main` when GitHub exposes that option;
- block force pushes/non-fast-forward updates;
- block branch deletion;
- no bypass actors during normal development.

The pull-request requirement is retained so task-sized branches and CI remain visible and attributable; it does **not** imply a review requirement.

`.github/CODEOWNERS` is not needed under this policy because ownership lives in `AGENTS.md` and is not an approval mechanism.

## 4. CI platform baseline

CI has three layers:

1. Ubuntu Python matrix: `test (3.10)` and `test (3.11)`;
2. `windows-integration`: Python 3.11 + Node 22 + Rust/Tauri validation on the target desktop OS;
3. `merge-gate`: final aggregate result.

A signed/package installer build is a release/demo gate, not a requirement for every PR.

## 5. Merge behavior

Preferred method: **squash merge**.

Immediately before merge, the human or AI merge actor fresh-reads the PR head/base state and the blocking CI results. No manual review-state check is required.

PR authors do not need to copy SHAs or job results into PR descriptions. Exact-head/base validity is handled by the merge actor/agent.

When the CI-only conditions are satisfied, the merge actor should merge promptly. A green PR must not remain open merely waiting for a reviewer, owner acknowledgement, or discussion resolution.

## 6. Permissions and secrets

All four collaborators may create branches and PRs. Ownership boundaries in `AGENTS.md` define responsibility but do not add merge approvals.

Baseline CI requires no repository secret. Real model credentials remain local or in an approved secret store. Never expose credentials through fixtures, logs, screenshots, Actions output or demo recordings.

## 7. Current server-truth gap

Server truth checked on 2026-09-07: ruleset `main-protection` is active, targets the default branch, has no bypass actors, blocks deletion/non-fast-forward updates, but currently still requires **one approval** and **review-thread resolution**, and does **not** yet require the four CI status checks.

Therefore the server configuration is not yet aligned with this CI-only policy. Required manual ruleset correction:

1. set required approving reviews to `0`;
2. disable review-thread resolution;
3. keep Code Owner review disabled;
4. disable extra approval for unattributed changes if the UI exposes it;
5. add the four required status checks;
6. enable up-to-date/strict status checks if available;
7. keep deletion/non-fast-forward protection and no bypass actors.

Until that server change is made, GitHub itself may continue blocking merges for obsolete review reasons even when CI is green. This is the only remaining governance mismatch; repository files and CI policy must not reintroduce a human-review requirement to compensate for it.
