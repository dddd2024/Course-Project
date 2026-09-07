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
- [x] blocking CI includes Python 3.10/3.11, Windows integration and aggregate `merge-gate`.

### Repository-setting gate

- [ ] `main` ruleset matches the CI-only target in `docs/repository-settings.md`.

This remains a server-setting task. The current ruleset still has obsolete review requirements and lacks required status checks; repository files cannot correct those administrator settings by themselves.

### Deferred to the owning implementation PR

These are intentionally **not blockers for starting parallel work**:

- Track A implements/integrates the sidecar runtime against the frozen schemas/fixtures;
- Track B completes React/Tauri runtime integration, packaging and demo flow;
- Track D integrates optional PRE dependencies only after version/license/environment verification;
- Track C implements the mock/real LLM provider boundary behind project-native interfaces;
- teacher-provided `.dat` evaluation data is profiled after receipt and is not required to fabricate a pre-start dataset;
- Python dependency locking/constraints are added when the first real runtime/optional dependency set is accepted.

## Start protocol

Each member starts by reading `AGENTS.md`, their Track entrypoint and current Issue, then creates a task-sized branch from current `main`.

## No-go conditions

These conditions must be fixed because they should make tests/CI fail or invalidate the implementation itself; they do not create a separate human approval gate:

- a PR changes a shared contract without migration/fixture/test updates;
- a Track invents a new sidecar method/config name instead of updating the shared contract first;
- a Track passes third-party adapter objects across Track boundaries instead of project-native DTOs;
- a result references evidence/artifacts that cannot be resolved;
- blocking CI is red or incomplete;
- teacher ground truth leaks into inference logic;
- real credentials/private traffic are committed;
- an open-source dependency is copied or vendored without version/license/notice verification;
- an innovation claim cannot be tied to implemented, measurable behavior.

Merge eligibility itself follows only the current-version CI rule in `AGENTS.md`.
