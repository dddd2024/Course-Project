# Track C — EvidenceGraph-PRE / LLM / Verification / Experiments

Owner: `@sunny1ce`  
Primary tracking Issue: `#14`  
Research umbrella: `#9`

## Mission

Implement the V2 research contribution: provenance-aware evidence handling and executable verification of protocol-semantic hypotheses. Track C must improve reliability without turning LLM output into protocol ground truth.

## Read first

1. `AGENTS.md`
2. Issue `#14` and research umbrella `#9`
3. `docs/design-v2.md`
4. `docs/research-roadmap.md`
5. `docs/research-landscape.md`
6. `docs/architecture.md`
7. `docs/testing-plan.md`
8. Track D output contracts/fixtures relevant to the task

## Primary owned paths

- `src/course_project/evidence/`
- `src/course_project/llm/`
- `src/course_project/verification/`
- `experiments/`
- research fixtures/tests for EvidenceGraph-PRE

## Primary responsibilities

- evidence registry and provenance/dependency graph;
- competing `ProtocolHypothesis` objects;
- structured LLM hypothesis generation;
- executable checks for length, sequence, magic/constant, enum/type, timestamp, and limited practical checksum families;
- provenance-aware evidence fusion;
- `ACCEPTED / REJECTED / UNCERTAIN` decisions;
- naive-vote and LLM-only baselines;
- ablations and metrics including false-hypothesis rate, ParseCoverage, calibration/risk-coverage when implemented.

## Inputs

Track D supplies project-native deterministic observations, packet/message candidates, alignment/field candidates, and behavior/statistical evidence. Do not depend directly on Track D's third-party adapter objects.

## Outputs

- `Evidence` records with provenance;
- competing protocol hypotheses;
- executable check records;
- `VerificationResult` and accepted `VerifiedField` objects;
- experiment tables/figures/reproducibility notes consumed by Track A and presented by Track B.

## Non-negotiable research rules

- LLM confidence is not verification score.
- Derived evidence must not be counted as independent support merely because another tool/LLM restates it.
- Plausible but unsupported hypotheses remain `UNCERTAIN` or become `REJECTED`.
- Ground truth is evaluation-only and must not leak into inference.
- Every claimed innovation must have a measurable implementation plus baseline/ablation capable of testing the claim.

## Do not own by default

- deterministic packet/PRE producer internals in Track D;
- desktop UI/Tauri code in Track B;
- shared contracts/sidecar/CI without Track A review.

## First implementation sequence

1. evidence/provenance model and registry;
2. competing hypothesis representation;
3. length + sequence executable verification;
4. dependency-aware fusion and abstention;
5. provisional schema/parser feedback with Track A;
6. LLM-only / verifier / naive-vote / full-system experiments.

## Completion standard

A research feature is complete only when it has deterministic tests or controlled evaluation data, preserves provenance, reports failures/uncertainty explicitly, and contributes evidence to a baseline or ablation rather than existing only as an architectural claim.