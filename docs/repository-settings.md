# Repository Settings Baseline

This document records repository-level controls that cannot be enforced only by files in the repository.

## `main` protection — required before parallel implementation

Configure a branch protection rule or repository ruleset targeting `main` with these minimum settings:

- require a pull request before merging;
- require at least one approving review;
- require review from Code Owners when owned paths change;
- dismiss stale approvals when new commits are pushed;
- require conversation resolution before merge;
- require the current CI checks to pass:
  - `test (3.10)`;
  - `test (3.11)`;
  - `windows-integration` once that check has emitted successfully on `main`;
- block force pushes;
- block branch deletion;
- apply the rule to administrators as well during normal development, unless an emergency recovery procedure is explicitly documented.

Do not enable a required check name that has never been emitted successfully by Actions, because that can make the branch impossible to merge. When CI job names change, update the ruleset and this document together.

## CI platform baseline

The CI workflow intentionally has two layers:

1. Ubuntu Python matrix (`test (3.10)`, `test (3.11)`) for fast lint/unit/contract regression coverage.
2. `windows-integration` on Python 3.11 / Node 22 / Rust stable for the target desktop environment. It validates the Sidecar CLI and contract/runtime tests, performs `npm ci` + frontend build, and runs `cargo check --locked` for the Tauri shell.

A full signed/packaged Tauri installer build is a release/demo gate, not a requirement for every small PR unless the team later decides otherwise.

## Merge policy

Preferred merge method for task-sized branches: **squash merge**.

Reasons:
- keeps `main` readable during a short course schedule;
- makes each PR a reversible unit;
- preserves detailed work history in the PR discussion while avoiding dozens of AI-generated fixup commits on `main`.

Do not merge red CI merely because a demo deadline is close. If a check is invalid, fix or intentionally change the check through a reviewed PR.

## Permissions

All four collaborators should be able to create branches and PRs. Shared/high-risk paths remain governed by `CODEOWNERS` and `AGENTS.md`; write access does not imply ownership of every module.

## Secrets

- no repository secret is required for baseline CI;
- CI must use the mock/offline LLM path;
- real model credentials stay in local `.env` or an approved secret store;
- never expose credentials through fixtures, logs, screenshots, Actions output or the final demo recording.

## Manual verification record

After enabling protection, verify from the GitHub UI/API that `main` reports protection/ruleset enforcement. Track A should record the verification in the pre-implementation readiness Issue.
