# Pre-Implementation Readiness Gate

> Purpose: define the last checks before four Tracks start parallel implementation.

## Gate status

### Ready in repository

- [x] four-person Track ownership defined;
- [x] collaborators can be assigned to their Track Issues;
- [x] AI entrypoints (`AGENTS.md` + per-Track docs) defined;
- [x] V1/V2 architecture and research direction fixed;
- [x] shared JSON schemas exist;
- [x] synthetic golden contract fixtures exist and are CI-validated;
- [x] safe `.env.example` exists with mock/offline LLM default;
- [x] Python/Node/Rust development baseline is documented;
- [x] dependency/license acceptance register exists;
- [x] course delivery checklist exists;
- [x] Python CI is green on supported versions.

### Repository-setting gate

- [ ] `main` branch protection/ruleset enabled according to `docs/repository-settings.md`.

This item must be verified in GitHub repository settings. Repository files alone cannot prevent a collaborator with write access from pushing directly to an unprotected branch.

### Deferred to the owning implementation PR

These are intentionally **not blockers for starting parallel work**:

- Track B creates the actual React/Tauri scaffold, lockfiles and desktop CI in its first implementation slice;
- Track D integrates the first optional PRE dependency only after version/license/environment verification;
- Track C implements the mock/real LLM provider boundary behind project-native interfaces;
- teacher-provided `.dat` evaluation data is profiled after receipt and is not required to fabricate a pre-start dataset.

## Start protocol

Each member starts by reading `AGENTS.md`, their Track entrypoint and current Issue, then creates a task-sized branch from current `main`.

Recommended first slices:

- Track A: sidecar protocol skeleton + contract fixture consumption;
- Track B: fixed-fixture React/Tauri contract spike + scaffold/desktop CI;
- Track C: evidence/provenance model + length/sequence executable verifier skeleton;
- Track D: `.dat` loader + deterministic byte statistics/boundary candidate interface.

## No-go conditions

Stop and resolve before merging if:

- a PR changes a shared contract without migration/fixture/test updates;
- CI becomes red;
- a Track silently takes ownership of another Track's module;
- teacher ground truth leaks into inference logic;
- real credentials/private traffic are committed;
- an open-source dependency is copied or vendored without version/license/notice review;
- an innovation claim cannot be tied to implemented, measurable behavior.
