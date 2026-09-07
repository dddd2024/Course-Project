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
8. `src/course_project/models.py` and relevant Track D fixtures/contracts

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
- deterministic mock/offline and real-provider boundary behind project-native interfaces;
- naive-vote and LLM-only baselines;
- ablations and metrics including false-hypothesis rate, ParseCoverage, calibration/risk-coverage when implemented.

## Inputs

Track D supplies project-native deterministic/PRE outputs, specifically as appropriate:

- `InputMetadata` / `PacketCandidate` / `MessageCandidate`;
- `MessageFamily`;
- `AlignmentResult` / `AlignmentRegion`;
- `FieldCandidate`;
- `BehaviorFeatures`;
- deterministic `Evidence` records or observations that Track C converts into provenance-tagged evidence.

Do not depend directly on Track D's Netzob, BinaryInferno, NFStream, Scapy or other third-party adapter objects.

## Outputs

- `Evidence` records with provenance;
- competing `ProtocolHypothesis` objects;
- `ExecutableCheck` records;
- `VerificationResult` and accepted `VerifiedField` objects;
- experiment tables/figures/reproducibility notes consumed by Track A and presented by Track B.

## Non-negotiable research rules

- LLM confidence is not verification score.
- Derived evidence must not be counted as independent support merely because another tool/LLM restates it.
- Plausible but unsupported hypotheses remain `UNCERTAIN` or become `REJECTED`.
- Ground truth is evaluation-only and must not leak into inference.
- Teacher-provided `.dat` is the authoritative course evaluation input; synthetic controlled fixtures are mechanism/engineering evidence only unless explicitly reported as such.
- Every claimed innovation must have a measurable implementation plus baseline/ablation capable of testing the claim.

## Do not own by default

- deterministic packet/PRE producer internals in Track D;
- desktop UI/Tauri code in Track B;
- shared contracts/sidecar/CI without Track A review.

## First implementation sequence

1. evidence/provenance registry using shared models;
2. competing hypothesis representation;
3. length + sequence executable verification;
4. dependency-aware fusion and abstention;
5. provisional schema/parser feedback with Track A;
6. LLM-only / verifier / naive-vote / full-system experiments where ground truth supports comparison.

## Completion standard

A research feature is complete only when it has deterministic tests or explicitly identified controlled evaluation evidence, preserves provenance, reports failures/uncertainty explicitly, and contributes evidence to a baseline or ablation rather than existing only as an architectural claim.
