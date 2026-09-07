# Research Roadmap

> Status: **V2 Research Work Breakdown**

This roadmap converts the research direction into implementation and experiment work that can be assigned to team members.

## R0 — Preserve V1 delivery path

V2 research work must not block the minimal `.dat -> analysis -> verified schema -> structured restoration` course demo.

## R1 — Evidence model and provenance graph

Deliverables:

- `Evidence` model with source, parents, feature family, coverage, and independence group;
- evidence registry;
- dependency/provenance graph;
- visualization/export for debugging and report figures.

Acceptance:

- at least three evidence producers can emit provenance-tagged evidence;
- a derived LLM interpretation can be traced back to the raw evidence that caused it;
- duplicated dependent evidence can be demonstrated in a test fixture.

## R2 — Competing protocol hypotheses

Deliverables:

- `ProtocolHypothesis` model;
- support for multiple interpretations of the same byte region;
- explicit competing-hypothesis relationships;
- structured LLM output that proposes candidates rather than one forced answer.

Acceptance:

- one field region can hold multiple endian/semantic interpretations;
- invalid LLM output fails closed;
- hypotheses remain `UNCERTAIN` until verified.

## R3 — Executable verification library

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

## R4 — Schema execution loop

Deliverables:

- provisional JSON/Kaitai schema generation;
- parser generation or schema-driven parser;
- corpus-wide parse execution;
- `ParseCoverage` and parse-failure evidence.

Acceptance:

- an inferred schema is executed against held-out messages;
- parse failures feed back into verification evidence;
- accepted fields are not exported when global execution contradicts them.

## R5 — Provenance-aware fusion and abstention

Deliverables:

- naive vote baseline;
- provenance-aware discount/collapse rule;
- `ACCEPTED / REJECTED / UNCERTAIN` decision policy;
- risk-coverage reporting.

Acceptance:

- a test demonstrates that dependent evidence does not count as multiple independent confirmations;
- full system is compared with naive multi-source voting;
- thresholds can trade coverage for error rate.

## R6 — Experiments

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

## R7 — Optional extensions

Only start after R1–R6 are stable:

- Syntax–Semantic–State cross-layer feedback;
- counterfactual validation on controlled data;
- cross-session/cross-day shortcut-resistant behavior classification;
- learned confidence calibration.

## Research gate

Do not promote an idea to a claimed project innovation unless all three are true:

1. the recent literature review does not already make it routine;
2. the project has a measurable implementation of the idea;
3. the experiment includes a baseline/ablation capable of testing the claimed effect.
