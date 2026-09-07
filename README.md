# Course Project

> **Unknown Binary Protocol Inference and Encrypted Traffic Behavior Analysis**

This repository is the collaborative workspace for a cybersecurity course project focused on **unknown binary network-stream analysis**. The project combines statistical analysis, protocol reverse-engineering techniques, machine learning, and LLM-assisted semantic reasoning to infer packet structure and traffic behavior from `.dat` binary data.

## Scope

The system is designed for **coursework, controlled datasets, and authorized laboratory traffic only**. It does not attempt to break modern cryptography without keys. For encrypted payloads, the project focuses on observable structure and metadata such as packet boundaries, headers, length/direction/timing patterns, and behavior types. Controlled decryption is only used for self-generated test data when the test key is available.

## V1 Pipeline

```text
unknown.dat / pcap
        |
        v
Binary Stream Loader
        |
        v
Statistical & Byte-Level Analysis
(entropy / frequency / n-gram / printable ratio / local entropy)
        |
        v
Packet Boundary Detection
        |
        v
Message Clustering & Alignment
        |
        v
Field Inference
(magic / version / type / length / sequence / timestamp / payload)
        |
        v
LLM Semantic Hypothesis
        |
        v
Deterministic Evidence Verification
        |
        +--------------------+
        |                    |
        v                    v
Protocol Schema       Traffic Behavior Model
        |                    |
        v                    v
Kaitai/Parser Export  QUERY / DOWNLOAD / UPLOAD /
                     HEARTBEAT / STREAM
```

## Repository Layout

```text
.
├── docs/                      # design, architecture, division of work, test plan
├── src/course_project/        # implementation packages
│   ├── io/                    # .dat / pcap input normalization
│   ├── features/              # entropy and statistical features
│   ├── boundary/              # packet-boundary inference
│   ├── inference/             # alignment and field inference
│   ├── llm/                   # LLM semantic reasoning
│   ├── verification/          # deterministic hypothesis verification
│   ├── behavior/              # flow/behavior analysis
│   └── exporters/             # schema and parser export
├── tests/                     # unit/integration/evaluation tests
├── data/                      # dataset conventions; no sensitive/raw private traffic
├── examples/                  # reproducible demo inputs and expected outputs
└── .github/                   # PR and issue templates
```

## Design Documents

- [`docs/design-v1.md`](docs/design-v1.md) — first complete design baseline.
- [`docs/architecture.md`](docs/architecture.md) — component boundaries and data contracts.
- [`docs/desktop-app-guide.md`](docs/desktop-app-guide.md) — Tauri-style desktop architecture, Agent UX, sidecar contract, and phased delivery guidance.
- [`docs/team-division.md`](docs/team-division.md) — multi-person work packages and collaboration rules.
- [`docs/open-source-stack.md`](docs/open-source-stack.md) — planned use of Netzob, BinaryInferno, Kaitai Struct, Scapy, NFStream, and ML baselines.
- [`docs/testing-plan.md`](docs/testing-plan.md) — evaluation datasets, baselines, metrics, and ablations.

## Collaboration Rules

1. Work is split by **work package**, not by editing the same files simultaneously.
2. Create a branch from `main` for each task: `feature/<topic>`, `fix/<topic>`, or `docs/<topic>`.
3. Every non-trivial change should go through a pull request.
4. PRs must state the owner, affected module, test evidence, and whether interfaces/data schemas changed.
5. Shared interfaces in `docs/architecture.md` are treated as contracts. Changes require review from the integration owner.
6. Raw private traffic, credentials, API keys, and real-world sensitive captures must never be committed.

## Current Status

**Phase: V1 design baseline / repository initialization.**

The V1 design intentionally prioritizes a reproducible end-to-end pipeline over training a new large model from scratch. Mature open-source tools are used as baselines or adapters, while the project-specific work focuses on packet-boundary inference, evidence-guided protocol semantics, deterministic verification, confidence scoring, orchestration, and evaluation.
