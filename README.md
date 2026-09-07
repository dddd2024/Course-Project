# Course Project

> **Unknown Binary Protocol Inference and Encrypted Traffic Behavior Analysis**

This repository is a four-person cybersecurity course project for unknown binary network-stream analysis. The current design combines deterministic byte/flow analysis, protocol reverse engineering, LLM-assisted semantic reasoning, EvidenceGraph-PRE verification, and a local desktop workbench.

## Scope

The system is for coursework, controlled datasets, and authorized laboratory traffic only. It does not claim to break correctly implemented modern cryptography without keys. Encrypted-flow analysis focuses on observable structure, metadata, timing, packet sizes, direction, and controlled test data.

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
├── apps/
│   └── desktop/                 # React + TypeScript UI and Tauri/Rust shell
├── contracts/                   # cross-language JSON schemas / protocol contracts
├── docs/                        # V1/V2 design, research, desktop, team and testing docs
├── experiments/                 # baselines, ablations and reproducibility notes
├── prompts/                     # versioned Agent prompts when introduced
├── src/course_project/
│   ├── io/                      # input normalization
│   ├── features/                # byte/statistical features
│   ├── boundary/                # packet-boundary inference
│   ├── inference/               # clustering/alignment/field inference
│   ├── evidence/                # evidence registry + provenance graph
│   ├── llm/                     # semantic hypothesis generation
│   ├── verification/            # executable/deterministic checks
│   ├── behavior/                # encrypted-flow behavior features/classifier
│   ├── exporters/               # JSON/Kaitai/parser export
│   ├── sidecar/                 # stable desktop-facing analyzer protocol
│   └── models.py                # shared Python contracts
├── tests/                       # unit/integration/evaluation tests
├── data/                        # sanitized/controlled dataset conventions
├── examples/                    # reproducible demos
└── .github/                     # CI, CODEOWNERS, PR/issue templates
```

## Four-Person Ownership

| Track | Owner | Primary responsibility |
|---|---|---|
| A | `@dddd2024` | integration, contracts, sidecar, CI, export, end-to-end |
| B | `@hinaLove1` | React/Tauri desktop, visualization, packaging and demo |
| C | `@sunny1ce` | EvidenceGraph-PRE, LLM reasoning, executable verification, experiments |
| D | `@zhaohongjun20-creator` | binary analysis, boundaries, protocol inference, behavior features |

Track B and Track D responsibilities were swapped on 2026-09-07; account ownership remains unchanged.

At the time this skeleton was updated, `@sunny1ce` and `@zhaohongjun20-creator` still had pending collaborator invitations, so automatic GitHub assignment/review requests may not activate until they accept.

## Design Documents

- [`docs/design-v1.md`](docs/design-v1.md) — minimum runnable analysis baseline.
- [`docs/design-v2.md`](docs/design-v2.md) — EvidenceGraph-PRE research design.
- [`docs/research-landscape.md`](docs/research-landscape.md) — 2023–2026 research screening and novelty discipline.
- [`docs/research-roadmap.md`](docs/research-roadmap.md) — V2 implementation/experiment roadmap.
- [`docs/architecture.md`](docs/architecture.md) — current package, contract and dependency boundaries.
- [`docs/desktop-app-guide.md`](docs/desktop-app-guide.md) — Tauri/React desktop workbench design.
- [`docs/team-division.md`](docs/team-division.md) — four-person ownership and collaboration rules.
- [`docs/open-source-stack.md`](docs/open-source-stack.md) — third-party baselines/adapters.
- [`docs/testing-plan.md`](docs/testing-plan.md) — evaluation datasets, metrics and ablations.

## Collaboration Rules

1. Work from an Issue and a dedicated branch; non-trivial changes go through a PR.
2. Treat `contracts/`, `models.py`, `docs/architecture.md`, and sidecar protocol versions as shared interfaces.
3. Cross-language work is contract-first: schema/example first, then producer/consumer implementations.
4. Every accepted protocol-semantic claim must retain evidence and verification records.
5. Do not commit raw private traffic, credentials, test keys, restored sensitive plaintext, or unrestricted shell hooks.
6. Keep `main` green; integrate reviewed work frequently instead of doing a final-day merge.

## Current Status

**Phase: four-person V2 + desktop skeleton established; implementation work can proceed in parallel.**
