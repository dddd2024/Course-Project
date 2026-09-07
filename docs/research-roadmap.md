# Research Roadmap

> Status: **V2 Research Work Breakdown — Four-Person Mapping**

This roadmap converts the EvidenceGraph-PRE direction into implementation and experiment work while preserving the V1 course-delivery path and the new desktop application work.

## Ownership Mapping

| Roadmap area | Primary owner | Support |
|---|---|---|
| R0 delivery/integration | `@dddd2024` | all |
| R1 evidence/provenance | `@sunny1ce` | `@dddd2024` |
| R2 competing hypotheses | `@sunny1ce` | `@zhaohongjun20-creator` |
| R3 executable verification | `@sunny1ce` | `@zhaohongjun20-creator` |
| R4 schema execution loop | `@dddd2024` | `@sunny1ce`, `@hinaLove1` |
| R5 provenance fusion/abstention | `@sunny1ce` | `@dddd2024` |
| R6 experiments | `@sunny1ce` | `@zhaohongjun20-creator`, `@dddd2024` |
| D0–D4 desktop workbench | `@hinaLove1` | `@dddd2024` |
| deterministic PRE/binary producers | `@zhaohongjun20-creator` | `@sunny1ce` |

Track B and Track D work packages were swapped on 2026-09-07. Account-to-track letters remain unchanged.

## R0 — Preserve V1 Delivery Path

Owner: `@dddd2024`.

V2 research work must not block the minimal `.dat -> analysis -> verified schema -> structured restoration` course demo. The desktop is a consumer of this path, not a replacement for it.

## R1 — Evidence Model and Provenance Graph

Owner: `@sunny1ce`.

Deliverables:
- `Evidence` model with source, parents, feature family, coverage, and independence group;
- evidence registry;
- dependency/provenance graph;
- visualization/export for debugging and report figures.

Acceptance:
- at least three evidence producers can emit provenance-tagged evidence;
- a derived LLM interpretation can be traced back to raw evidence;
- duplicated dependent evidence can be demonstrated in a fixture.

## R2 — Competing Protocol Hypotheses

Owner: `@sunny1ce`, with candidate inputs from `@zhaohongjun20-creator`.

Deliverables:
- `ProtocolHypothesis` model;
- multiple interpretations of the same byte region;
- competing-hypothesis relationships;
- structured LLM output that proposes candidates rather than one forced answer.

Acceptance:
- one field region can hold multiple endian/semantic interpretations;
- invalid LLM output fails closed;
- hypotheses remain `UNCERTAIN` until verified.

## R3 — Executable Verification Library

Owner: `@sunny1ce`, deterministic producer support from `@zhaohongjun20-creator`.

Priority checks:
1. length;
2. sequence;
3. magic/constant;
4. enum/message type;
5. timestamp;
6. limited known checksum families.

Acceptance:
- every check records sample/support/violation counts;
- length and sequence tests work on controlled ground-truth data;
- a plausible but false hypothesis can be rejected.

## R4 — Schema Execution Loop

Owner: `@dddd2024`.

Deliverables:
- provisional JSON/Kaitai schema generation;
- parser generation or schema-driven parser;
- corpus-wide parse execution;
- `ParseCoverage` and parse-failure evidence;
- desktop-readable result reference through the sidecar contract.

Acceptance:
- an inferred schema is executed against held-out messages;
- parse failures feed back into verification evidence;
- accepted fields are not exported when global execution contradicts them.

## R5 — Provenance-Aware Fusion and Abstention

Owner: `@sunny1ce`.

Deliverables:
- naive vote baseline;
- provenance-aware discount/collapse rule;
- `ACCEPTED / REJECTED / UNCERTAIN` policy;
- risk-coverage reporting.

Acceptance:
- dependent evidence does not count as multiple independent confirmations;
- full system is compared with naive multi-source voting;
- thresholds can trade coverage for error rate.

## R6 — Experiments

Owner: `@sunny1ce`; baseline data/outputs from `@zhaohongjun20-creator`; integration/reproducibility support from `@dddd2024`.

Required comparisons:
- heuristic baseline;
- Netzob/BinaryInferno-style baseline;
- LLM-only;
- LLM + deterministic verification;
- naive multi-source vote;
- full EvidenceGraph-PRE.

Required ablations:
- w/o executable verification;
- w/o provenance;
- w/o LLM;
- w/o alignment.

Required metrics:
- Packet Boundary F1;
- Field Boundary F1;
- Field Semantic Accuracy;
- False Hypothesis Rate;
- Parse Coverage;
- Constraint Satisfaction Rate;
- Restoration Accuracy;
- accepted-field coverage / risk-coverage;
- processing time;
- optional LLM token/cost metrics.

## D0–D4 — Desktop Workbench

Owner: `@hinaLove1`, contract/integration review by `@dddd2024`.

Follow `docs/desktop-app-guide.md`:
- D0 contract spike: fixed React -> Tauri -> Python -> React path;
- D1 read-only desktop: import, overview, hex/statistics;
- D2 interactive inference: boundaries, alignment, field/evidence views;
- D3 behavior and controlled restoration;
- D4 packaging/performance and clean-machine demo.

Desktop work must consume stable sidecar contracts and must not duplicate/reimplement protocol inference in TypeScript/Rust unless profiling later proves a specific hotspot needs migration.

## Deterministic PRE / Behavior Producers

Owner: `@zhaohongjun20-creator`.

This cross-cutting stream supplies R1–R6 with reproducible non-LLM evidence:
- input normalization;
- statistical/byte features;
- packet boundary candidates;
- clustering/alignment;
- field candidate baselines;
- flow/behavior features.

The output must use project-native contracts and avoid leaking third-party library objects.

## R7 — Optional Extensions

Only start after R1–R6 and the desktop contract spike are stable:
- Syntax–Semantic–State cross-layer feedback;
- counterfactual validation on controlled data;
- cross-session/cross-day shortcut-resistant behavior classification;
- learned confidence calibration.

## Research Gate

Do not promote an idea to a claimed project innovation unless all three are true:
1. recent literature review does not already make it routine;
2. the project has a measurable implementation;
3. the experiment includes a baseline/ablation capable of testing the claimed effect.
