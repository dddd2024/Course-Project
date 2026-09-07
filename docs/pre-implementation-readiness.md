# Pre-Implementation Readiness Gate

> Purpose: define the last checks before four Tracks start parallel implementation.

## Gate status

### Ready in repository

- [x] four-person Track ownership defined;
- [x] collaborators can be assigned to their Track Issues;
- [x] AI entrypoints (`AGENTS.md` + per-Track docs) defined;
- [x] V1/V2 architecture and research direction fixed;
- [x] teacher-provided `.dat` is the authoritative course evaluation input; optional synthetic data is engineering/mechanism-only;
- [x] semantic decision terminology is canonicalized as `ACCEPTED / REJECTED / UNCERTAIN` externally and lowercase equivalents internally;
- [x] shared JSON schemas exist;
- [x] synthetic golden contract fixtures exist and are CI-validated;
- [x] D→C normalized intermediate DTOs are defined in `models.py`;
- [x] sidecar v1 command/config vocabulary is frozen in schema/docs;
- [x] `AnalysisResult` includes evidence records and an artifact manifest for desktop integration;
- [x] safe `.env.example` exists with mock/offline LLM default;
- [x] Python/Node/Rust development baseline is documented;
- [x] dependency/license acceptance register exists;
- [x] course delivery checklist exists;
- [x] Python CI is green on supported versions before this repair; this repair must also pass PR/main CI before being considered complete.

### Repository-setting gate

- [ ] `main` branch protection/ruleset enabled according to `docs/repository-settings.md`.

This item must be verified in GitHub repository settings. Repository files alone cannot prevent a collaborator with write access from pushing directly to an unprotected branch.

### Deferred to the owning implementation PR

These are intentionally **not blockers for starting parallel work**:

- Track A implements the sidecar runtime skeleton against the already-frozen v1 schemas/fixtures;
- Track B creates the actual React/Tauri scaffold, lockfiles and desktop CI in its first implementation slice;
- Track D integrates the first optional PRE dependency only after version/license/environment verification;
- Track C implements the mock/real LLM provider boundary behind project-native interfaces;
- teacher-provided `.dat` evaluation data is profiled after receipt and is not required to fabricate a pre-start dataset;
- Python dependency locking/constraints are added when the first real runtime/optional dependency set is accepted;
- Windows/desktop CI expands when a runnable desktop scaffold exists.

## Start protocol

Each member starts by reading `AGENTS.md`, their Track entrypoint and current Issue, then creates a task-sized branch from current `main`.

Recommended first slices:

- Track A: sidecar runtime skeleton implementing the frozen command vocabulary + contract fixture consumption;
- Track B: fixed-fixture React/Tauri contract spike + scaffold/desktop CI;
- Track C: evidence/provenance model + length/sequence executable verifier skeleton;
- Track D: `.dat` loader + deterministic byte statistics/boundary candidate interface using the normalized DTOs.

## No-go conditions

Stop and resolve before merging if:

- a PR changes a shared contract without migration/fixture/test updates;
- a Track invents a new sidecar method/config name instead of updating the shared contract first;
- a Track passes third-party adapter objects across Track boundaries instead of project-native DTOs;
- a result references evidence/artifacts that cannot be resolved;
- CI becomes red;
- a Track silently takes ownership of another Track's module;
- teacher ground truth leaks into inference logic;
- real credentials/private traffic are committed;
- an open-source dependency is copied or vendored without version/license/notice review;
- an innovation claim cannot be tied to implemented, measurable behavior.
