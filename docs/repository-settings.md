# Repository Settings Baseline

This document defines the repository-level merge policy for `main`.

## 1. Governance model

Use one simple rule for every pull request:

> **Right reviewer + green CI + no unresolved blocker = mergeable.**

These are the only three merge gates.

### Gate 1 — one valid human approval

Require at least one approving human review.

Reviewer selection:
- ordinary Track-internal PR: any other team member;
- shared-interface or cross-Track PR: Track A (`@dddd2024`);
- Track A-authored shared/cross-Track PR: one affected Track owner.

Automated Codex/GitHub review is advisory. It may identify defects, but it does not create an additional approval requirement.

### Gate 2 — full green CI for the current PR version

Blocking checks are:
- `test (3.10)`;
- `test (3.11)`;
- `windows-integration`;
- `merge-gate`.

`merge-gate` is the aggregate check and must succeed only when all blocking jobs succeed.

If code changes after CI, rerun/recheck CI. PR authors do not need to copy SHAs or job results into the PR description; the merge actor/agent verifies the current state immediately before merging.

### Gate 3 — no unresolved blocker

Before merge:
- no active `CHANGES_REQUESTED` review remains;
- blocking review conversations are resolved;
- the PR has no merge conflict.

## 2. Recommended GitHub `main` ruleset

Configure `main` with the smallest settings needed to enforce the three gates:

- require a pull request before merging;
- require at least one approving review;
- dismiss stale approvals when new commits are pushed;
- require conversation resolution before merge;
- require these status checks:
  - `test (3.10)`;
  - `test (3.11)`;
  - `windows-integration`;
  - `merge-gate`;
- block force pushes;
- block branch deletion.

A separate Code Owner approval is **not** required by default. Reviewer ownership is selected according to Gate 1 above. This keeps ordinary PRs lightweight while still routing shared-interface changes through Track A.

Do not enable a required check name until that check has emitted successfully on `main`.

## 3. CI platform baseline

CI has three layers:

1. Ubuntu Python matrix: `test (3.10)` and `test (3.11)`;
2. `windows-integration`: Python 3.11 + Node 22 + Rust/Tauri validation on the target desktop OS;
3. `merge-gate`: final aggregate result.

A signed/package installer build is a release/demo gate, not a requirement for every PR.

## 4. Merge behavior

Preferred method: **squash merge**.

Immediately before merge, the merge actor/agent checks the three gates. Exact commit/head synchronization is an implementation detail of that check, not a manual task for each author.

If `main` changes and the PR must be synchronized to obtain valid CI or remove a conflict, update the branch and rerun CI. Never rely on a green run from a previous code version.

## 5. Permissions and secrets

All four collaborators may create branches and PRs, but ownership boundaries in `AGENTS.md` still apply.

Baseline CI requires no repository secret. Real model credentials remain local or in an approved secret store. Never expose credentials through fixtures, logs, screenshots, Actions output or demo recordings.

## 6. Current server-truth note

As of 2026-09-07, `main-protection` is active and already enforces a PR, one approval, stale-approval dismissal, review-thread resolution, deletion blocking and non-fast-forward blocking.

The remaining repository-settings task is to add the four required CI checks after they have emitted successfully on `main`. Code Owner review no longer needs to be enabled for the simplified governance model.
