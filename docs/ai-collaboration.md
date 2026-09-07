# AI Collaboration Protocol

This document explains how human members should hand work to their AI coding tools without requiring the AI to rediscover team ownership from scratch.

## Single source of truth

`AGENTS.md` is the authoritative cross-tool AI collaboration policy. Tool-specific files such as `CLAUDE.md`, `GEMINI.md`, and `.github/copilot-instructions.md` are intentionally thin adapters that redirect the tool to `AGENTS.md`; they must not become independent copies of the task mapping.

## Recommended handoff prompt

A team member can begin a session with a short instruction such as:

> Read the repository AI instructions, identify me as `<GitHub username>`, read my Track entrypoint and current tracking Issue, then summarize my scope, current acceptance criteria, dependencies, and the first implementation step before editing.

Examples of identity values are the four GitHub accounts listed in `AGENTS.md`.

## Expected AI startup behavior

Before editing, an agent should be able to answer five questions:

1. Which Track is the current operator on?
2. Which GitHub Issue is the current execution anchor?
3. Which paths are owned by this Track?
4. Which shared interfaces could be affected?
5. What objective evidence will show the task is complete?

If any of these cannot be resolved from the repository/current Issue, the agent should ask instead of guessing.

## Why both Issues and Track files exist

Track files define durable ownership and interfaces. GitHub Issues define changing execution priorities and acceptance criteria. Therefore an AI should not treat a Track file as a static backlog and should not treat an Issue as permission to rewrite unrelated modules.

## Cross-track escalation

When one Track is blocked by another:

- create or link a dependency Issue/comment;
- specify the required contract/output rather than prescribing another Track's internal implementation;
- if a shared contract must change, follow the migration/tests in `AGENTS.md` and `docs/architecture.md`;
- keep the requesting Track's PR narrow until the dependency is resolved.

Cross-Track coordination does not create a human approval gate. Merge eligibility is determined only by current-version CI according to `AGENTS.md`.

## Workload evidence

For course workload accounting, AI-assisted work should still leave attributable engineering evidence: owned Issue, human-owned branch/PR, tests, experiment/result artifacts, documentation, and demo contribution. Optional discussion/comments may be retained as context, but approval is not required for merge.
