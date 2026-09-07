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
  - `windows-integration`;
  - `merge-gate`;
- require branches to be up to date with `main` before merging when GitHub settings permit;
- block force pushes;
- block branch deletion;
- apply the rule to administrators as well during normal development, unless an emergency recovery procedure is explicitly documented.

`merge-gate` is the final aggregate CI job. It depends on every blocking CI job and succeeds only when all of them report `success`. Whenever a new blocking CI job is introduced, it must also be added to `merge-gate.needs` in `.github/workflows/ci.yml` before that CI change may merge.

Do not enable a required check name that has never been emitted successfully by Actions, because that can make the branch impossible to merge. When CI job names change, update the ruleset, `merge-gate`, and this document together.

## CI platform baseline

The CI workflow intentionally has three layers:

1. Ubuntu Python matrix (`test (3.10)`, `test (3.11)`) for fast lint/unit/contract regression coverage.
2. `windows-integration` on Python 3.11 / Node 22 / Rust stable for the target desktop environment. It validates the Sidecar CLI and full Python suite, performs `npm ci` + frontend build, and runs `cargo check --locked` for the Tauri shell.
3. `merge-gate`, which has no independent product test responsibility; it aggregates the blocking jobs and fails closed unless every dependency succeeded.

A full signed/packaged Tauri installer build is a release/demo gate, not a requirement for every small PR unless the team later decides otherwise.

## Merge policy

Preferred merge method for task-sized branches: **squash merge**.

### Hard precondition: latest-head CI must be completely green

A PR must **not** be merged while any blocking CI job for the PR's current head commit is queued, in progress, failed, cancelled, timed out, action-required, stale, or otherwise non-successful.

Before any human or AI agent performs a merge, it must fresh-read the PR head SHA and the CI/check state for that exact head. Merge is allowed only when:

1. all currently defined blocking CI jobs for that exact head have completed with `success`;
2. `merge-gate` has completed with `success` for that exact head;
3. no newer commit has been pushed after the verified CI run;
4. any separately required review/conversation/ownership conditions are also satisfied.

A previous green run for an older head SHA is not merge evidence. A partially green workflow is not merge evidence. `mergeable=true` alone is not merge evidence.

If CI is red because a check is invalid, fix or intentionally change the check through a reviewed PR; never bypass or ignore it merely to merge. Demo deadlines do not waive this rule.

Reasons for squash merge:
- keeps `main` readable during a short course schedule;
- makes each PR a reversible unit;
- preserves detailed work history in the PR discussion while avoiding dozens of AI-generated fixup commits on `main`.

## Permissions

All four collaborators should be able to create branches and PRs. Shared/high-risk paths remain governed by `CODEOWNERS` and `AGENTS.md`; write access does not imply ownership of every module.

## Secrets

- no repository secret is required for baseline CI;
- CI must use the mock/offline LLM path;
- real model credentials stay in local `.env` or an approved secret store;
- never expose credentials through fixtures, logs, screenshots, Actions output or the final demo recording.

## Manual verification record

Repository files cannot by themselves prevent an administrator from pressing Merge. After this CI PR lands, enable branch protection or a repository ruleset in GitHub so `main` requires the emitted `test (3.10)`, `test (3.11)`, `windows-integration`, and `merge-gate` checks. Then verify from the GitHub UI/API that `main` reports protection/ruleset enforcement and record that verification in Track A Issue `#12`.
