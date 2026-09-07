# Team Division — Four-Person V2 + Desktop

> Status: active collaboration baseline

The project is organized around four ownership tracks. The goal is to minimize overlapping edits while covering the V1 runnable path, EvidenceGraph-PRE research work, and the desktop application design.

## 1. Team

| Track | GitHub account | Current status | Approx. workload | Primary ownership |
|---|---|---|---:|---|
| A | `@dddd2024` | repository owner | 25% | integration, architecture, contracts, sidecar, CI, export, E2E |
| B | `@hinaLove1` | collaborator (write) | 25% | React/Tauri desktop, visualization, packaging, demo |
| C | `@sunny1ce` | invitation pending when recorded | 25% | EvidenceGraph-PRE, LLM, verification, experiments |
| D | `@zhaohongjun20-creator` | invitation pending when recorded | 25% | binary analysis, packet boundaries, PRE, behavior features |

Track B and Track D responsibilities were swapped on 2026-09-07. The GitHub accounts remain attached to their original Track letters; only the work packages changed.

The 25/25/25/25 split is an initial planning baseline, not a final grading claim. Final workload percentages should be based on actual Issues, PRs, commits, tests, experiments, documentation and demo ownership.

## 2. Track A — Integration / Contracts / Sidecar / CI

Owner: `@dddd2024`

Primary paths:
- `docs/architecture.md`
- `contracts/`
- `src/course_project/models.py`
- `src/course_project/sidecar/`
- `src/course_project/exporters/`
- `.github/workflows/`

Responsibilities:
- maintain V1/V2 architectural consistency;
- own shared Python and cross-language data contracts;
- define the Python sidecar task/progress/error/result protocol;
- integrate verified protocol fields into JSON/Kaitai export;
- maintain CI and end-to-end smoke tests;
- resolve cross-track interface conflicts and freeze the demo branch/version.

Tracking issue: `#12`.

## 3. Track B — Desktop App / Visualization / Packaging / Demo

Owner: `@hinaLove1`

Primary paths:
- `apps/desktop/src/`
- `apps/desktop/src-tauri/`
- desktop-facing portions of `contracts/`
- `examples/`

Responsibilities:
- React + TypeScript UI;
- Tauri 2 / Rust application shell;
- controlled file grants and task lifecycle;
- Python sidecar launch/progress/error/result integration;
- overview, hex, alignment, statistics, behavior and evidence views;
- finding-to-byte-offset navigation;
- packaging and reproducible final demo.

Tracking issue: `#13`.

## 4. Track C — EvidenceGraph-PRE / LLM / Verification / Experiments

Owner: `@sunny1ce`

Primary paths:
- `src/course_project/evidence/`
- `src/course_project/llm/`
- `src/course_project/verification/`
- `experiments/`

Responsibilities:
- evidence registry and dependency/provenance graph;
- competing protocol hypotheses;
- structured LLM hypothesis generation;
- executable verification for length, sequence, enum/type, timestamp and selected checksum cases;
- provenance-aware evidence fusion;
- ACCEPTED / REJECTED / UNCERTAIN decision policy;
- LLM-only, verifier, naive-vote and provenance-aware ablations;
- metrics such as false-hypothesis rate, parse coverage and risk/coverage.

Tracking issue: `#14` and research umbrella `#9`.

## 5. Track D — Binary Analysis / Protocol Inference / Behavior Features

Owner: `@zhaohongjun20-creator`

Primary paths:
- `src/course_project/io/`
- `src/course_project/features/`
- `src/course_project/boundary/`
- `src/course_project/inference/`
- `src/course_project/behavior/`

Responsibilities:
- `.dat` / PCAP normalization;
- entropy, local entropy, byte frequency, n-gram and repeated-pattern features;
- packet/message boundary candidates;
- clustering, alignment, stable/variable regions;
- Netzob/BinaryInferno adapters and normalized field candidates;
- flow/behavior features such as size, direction, timing, burst and up/down ratio;
- deterministic/baseline outputs consumed by Track C.

Tracking issue: `#15`.

## 6. Shared Areas and Review Rules

Shared/high-risk paths:
- `contracts/`
- `src/course_project/models.py`
- `docs/architecture.md`
- `.github/workflows/`
- root dependency/build configuration

Rules:
1. Shared contract changes require Track A review and at least one affected consumer owner review.
2. UI/Rust/Python integration is contract-first: update schema + fixture before changing both sides independently.
3. Third-party objects must remain behind adapters; do not leak Netzob/NFStream/LLM-provider-specific types across modules.
4. Every track owns tests for its primary paths.
5. A PR that changes an interface must state the old contract, new contract, affected tracks and migration/test plan.
6. `main` should receive reviewed integration at least daily during the short course schedule.

## 7. Branch Convention

Recommended branch prefixes:

```text
track-a/<topic>
track-b/<topic>
track-c/<topic>
track-d/<topic>
fix/<topic>
docs/<topic>
experiment/<topic>
```

Do not use one long-lived branch per member for all work. Use task-sized branches and PRs so code review and rollback remain practical.

## 8. Existing Issues Mapping

The original WP issues remain useful as task-level history:

- `#1` architecture/contracts -> Track A
- `#2` binary features/boundaries -> Track D
- `#3` clustering/alignment/field inference -> Track D
- `#4` LLM/verifier -> Track C
- `#5` behavior/ML -> Track D with experiment support from Track C
- `#6` schema/datasets/demo -> Track A + Track B
- `#7` V1 project tracking -> all tracks
- `#9` EvidenceGraph-PRE research tracking -> Track C, reviewed by Track A
- `#11` four-person skeleton migration -> Track A
- `#12`–`#15` current four ownership tracks

## 9. Invitation Status

At the time of this revision, GitHub reported `@hinaLove1` with write permission, while `@sunny1ce` and `@zhaohongjun20-creator` were still pending repository invitations. Their ownership is recorded now, but issue assignment, CODEOWNERS review requests, branch pushes and PR review automation may not fully activate until they accept.

## 10. Final Workload Evidence

For the course task-division report, collect per member:
- owned Issues and completed acceptance criteria;
- PRs/commits and changed modules;
- unit/integration/evaluation tests;
- experiment ownership and result tables;
- documentation sections;
- demo/packaging contributions;
- final workload percentage with evidence.
