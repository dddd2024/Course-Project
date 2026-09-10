# Course Project

> **Unknown Binary Protocol Inference and Encrypted Traffic Behavior Analysis**

This repository is a four-person cybersecurity course project for unknown binary network-stream analysis. The current design combines deterministic byte/flow analysis, protocol reverse engineering, LLM-assisted semantic reasoning, EvidenceGraph-PRE verification, and a local desktop workbench.

## Scope

The system is for coursework, pinned public datasets, controlled datasets,
teacher-provided evaluation files, and authorized laboratory traffic only. It does
not claim to break correctly implemented modern cryptography without keys.
Encrypted-flow analysis focuses on observable structure, metadata, timing, packet
sizes, direction, and controlled/test data.

## Current Architecture

```text
.dat / .bin / pcap / pcapng
          |
          v
Python Analysis Engine
  io -> features -> boundary -> inference
                |          |
                v          v
             evidence -> LLM hypotheses
                |          |
                +----> executable verification
                           |
                           v
                    verified schema
                      /          \
             JSON/Kaitai      behavior model
                      \          /
                       v        v
                    sidecar contracts
                           |
                           v
             Tauri 2 + React Desktop
```

The V1 delivery path remains the minimum runnable course demo. V2 adds **EvidenceGraph-PRE: Provenance-Aware Executable Verification for LLM-Assisted Unknown Binary Protocol Inference**. The desktop design adds a local Tauri/React workbench that consumes the Python analyzer through stable sidecar contracts.

## Repository Layout

```text
.
├── AGENTS.md                     # first entrypoint for AI coding agents
├── .env.example                  # safe local configuration template; mock LLM by default
├── apps/
│   └── desktop/                  # React + TypeScript UI and Tauri/Rust shell
├── contracts/
│   └── fixtures/                 # synthetic golden cross-language contract examples
├── docs/
│   ├── tracks/                   # per-person AI/human task entrypoints
│   └── ...                       # V1/V2 design, research, startup and delivery docs
├── experiments/                  # baselines, ablations and reproducibility notes
├── prompts/                      # versioned Agent prompts when introduced
├── src/course_project/
│   ├── io/                       # input normalization
│   ├── features/                 # byte/statistical features
│   ├── boundary/                 # packet-boundary inference
│   ├── inference/                # clustering/alignment/field inference
│   ├── evidence/                 # evidence registry + provenance graph
│   ├── llm/                      # semantic hypothesis generation
│   ├── verification/             # executable/deterministic checks
│   ├── behavior/                 # encrypted-flow behavior features/classifier
│   ├── exporters/                # JSON/Kaitai/parser export
│   ├── sidecar/                  # stable desktop-facing analyzer protocol
│   └── models.py                 # shared Python contracts
├── tests/                        # unit/integration/contract/evaluation tests
├── data/                         # policy only; teacher data stays external unless allowed
├── examples/                     # reproducible demos
└── .github/                      # CI and PR/issue templates
```

## Four-Person Ownership

| Track | Owner | Primary responsibility |
|---|---|---|
| A | `@dddd2024` | integration, contracts, sidecar, CI, export, end-to-end |
| B | `@hinaLove1` | React/Tauri desktop, visualization, packaging and demo |
| C | `@sunny1ce` | EvidenceGraph-PRE, LLM reasoning, executable verification, experiments |
| D | `@zhaohongjun20-creator` | binary analysis, boundaries, protocol inference, behavior features |

Track B and Track D responsibilities were swapped on 2026-09-07; account ownership remains unchanged. All four collaborators have accepted repository access; Track Issues are the current execution anchors.

## AI Agent Entry Point

AI coding agents must start with [`AGENTS.md`](AGENTS.md), identify the human operator's GitHub account/Track, then read the matching Track file and current tracking Issue before editing code.

- Track A / `@dddd2024`: [`docs/tracks/track-a.md`](docs/tracks/track-a.md), Issue `#12`
- Track B / `@hinaLove1`: [`docs/tracks/track-b.md`](docs/tracks/track-b.md), Issue `#13`
- Track C / `@sunny1ce`: [`docs/tracks/track-c.md`](docs/tracks/track-c.md), Issue `#14` + research `#9`
- Track D / `@zhaohongjun20-creator`: [`docs/tracks/track-d.md`](docs/tracks/track-d.md), Issue `#15`

An AI agent may inspect the whole repository, but should not silently take over another Track or change shared contracts merely for convenience. Shared-interface changes follow the contract migration/test rules in `AGENTS.md` and `docs/architecture.md`.

## Start Here

Before parallel implementation:

- [`docs/pre-implementation-readiness.md`](docs/pre-implementation-readiness.md) — readiness gate and first implementation slices;
- [`docs/day0-contract-freeze.md`](docs/day0-contract-freeze.md) — exact shared names/DTOs/sidecar/result contracts all Tracks and AI agents must use at implementation start;
- [`docs/development-environment.md`](docs/development-environment.md) — canonical Python/Node/Rust setup;
- [`contracts/README.md`](contracts/README.md) — cross-language schemas and golden fixtures;
- [`docs/repository-settings.md`](docs/repository-settings.md) — required `main` protection settings;
- [`docs/dependency-register.md`](docs/dependency-register.md) — dependency/version/license acceptance gate;
- [`docs/delivery-checklist.md`](docs/delivery-checklist.md) — final course delivery and freeze checklist.
- [`docs/public-data-benchmark.md`](docs/public-data-benchmark.md) — pinned public
  PCAP sources, `.dat` conversion, behavior benchmark and measured limitations.

The current delivery uses fixed, hash-verified public data instead of teacher data.
Raw public PCAPs and the generated `.dat` remain ignored; only sanitized identities
and results are committed. The teacher-compatible ingress remains available.

## Day-0 Contract Baseline

Before writing cross-Track integration code, use the frozen contracts rather than inventing local aliases:

- semantic decisions: `ACCEPTED / REJECTED / UNCERTAIN` externally, lowercase equivalents in Python;
- sidecar v1 methods: `register_input`, `inspect_file`, `analyze`, `cancel_task`, `get_result`, `read_range`;
- Track D → C DTOs: `InputMetadata`, `MessageCandidate`, `MessageFamily`, `AlignmentResult`, `FieldCandidate`, `BehaviorFeatures` and related project-native models;
- desktop-facing result linkage: `findings[].evidenceIds` → `evidence[]`, with larger outputs exposed through `artifacts[]` controlled references.

Any incompatible or semantic change follows the shared-contract migration/testing process in `docs/architecture.md` and `AGENTS.md`.

## Design Documents

- [`docs/design-v1.md`](docs/design-v1.md) — minimum runnable analysis baseline.
- [`docs/design-v2.md`](docs/design-v2.md) — EvidenceGraph-PRE research design.
- [`docs/research-landscape.md`](docs/research-landscape.md) — 2023–2026 research screening and novelty discipline.
- [`docs/research-roadmap.md`](docs/research-roadmap.md) — V2 implementation/experiment roadmap.
- [`docs/architecture.md`](docs/architecture.md) — current package, contract and dependency boundaries.
- [`docs/desktop-app-guide.md`](docs/desktop-app-guide.md) — Tauri/React desktop workbench design.
- [`docs/team-division.md`](docs/team-division.md) — four-person ownership and collaboration rules.
- [`docs/open-source-stack.md`](docs/open-source-stack.md) — third-party baselines/adapters.
- [`docs/testing-plan.md`](docs/testing-plan.md) — evaluation metrics, baselines and ablations.

## Collaboration Rules

1. Work from an Issue and a task-sized branch; non-trivial changes go through a PR.
2. Treat `contracts/`, `models.py`, `docs/architecture.md`, `docs/day0-contract-freeze.md`, and sidecar protocol versions as shared interfaces.
3. Cross-language work is contract-first: schema + golden fixture first, then producer/consumer implementations.
4. Every accepted protocol-semantic claim must retain evidence and verification records.
5. Do not commit raw private traffic, credentials, test keys, restored sensitive plaintext, teacher files without permission, or unrestricted shell hooks.
6. Keep `main` green; merge task-sized PRs as soon as their current-version CI is fully green.
7. New third-party dependencies must pass the version/license/adapter gate before merge.
8. Human/Codex review is optional feedback only and is never a merge requirement.

## Merge Policy

The only merge governance gate is current-version CI:

- `test (3.10)` success;
- `test (3.11)` success;
- `windows-integration` success;
- `merge-gate` success;
- no merge conflict.

If the PR head or `main` changes after the valid CI evaluation, synchronize and rerun CI before merge. See `AGENTS.md` and `docs/repository-settings.md`.

## Current Status

**Phase: implementation, desktop packaging, mechanism evidence and the pinned
public-data `.dat`/behavior benchmark are complete for the owner-approved delivery
scope. PPT and teacher-data execution are excluded by that scope.**
