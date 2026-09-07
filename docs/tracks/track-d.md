# Track D — Binary Analysis / Protocol Inference / Behavior Features

Owner: `@zhaohongjun20-creator`  
Primary tracking Issue: `#15`

## Mission

Produce deterministic, reproducible evidence from `.dat`/packet data for the rest of the system. Track D owns byte/packet/flow analysis and protocol-inference baselines, but does not decide final LLM-assisted protocol truth.

## Read first

1. `AGENTS.md`
2. Issue `#15`
3. `docs/design-v1.md`
4. `docs/design-v2.md` sections on evidence producers and shared models
5. `docs/architecture.md`
6. `src/course_project/models.py`
7. `docs/open-source-stack.md`
8. `docs/testing-plan.md`
9. `docs/team-division.md`

## Primary owned paths

- `src/course_project/io/`
- `src/course_project/features/`
- `src/course_project/boundary/`
- `src/course_project/inference/`
- `src/course_project/behavior/`
- Track-D-specific unit/fixture tests

## Primary responsibilities

- `.dat` / binary / packet input normalization;
- entropy, local entropy, byte frequency, n-gram, repeated-pattern and related deterministic features;
- packet/message boundary candidate generation;
- clustering and message alignment;
- stable/variable region and field candidate generation;
- adapters for Netzob/BinaryInferno-style baselines behind project-native interfaces;
- flow/behavior features such as size, direction, timing, burst and up/down ratio;
- reproducible baseline outputs consumed by Track C experiments.

## Inputs

- teacher-provided `.dat` when available, plus authorized `.bin`, PCAP/PCAPNG or tiny engineering fixtures;
- shared models/contracts from Track A.

Teacher raw data remains external unless redistribution is explicitly allowed. Track D must not read teacher ground truth as inference input.

## Canonical outputs

Use the project-native types in `src/course_project/models.py` rather than ad-hoc dicts or third-party objects:

- `InputMetadata` for registered input metadata;
- `PacketCandidate` for lightweight boundary candidates;
- `MessageCandidate` for normalized byte-range messages;
- `MessageFamily` for clusters;
- `AlignmentRegion` and `AlignmentResult` for stable/variable alignment output;
- `FieldCandidate` for normalized PRE/deterministic field candidates;
- `BehaviorFeatures` before behavior classification;
- deterministic/statistical observations or `Evidence` records with explicit source/method/provenance information;
- reproducible baseline artifacts for Track C.

If a new output cannot be represented by these DTOs, propose a shared contract change through Track A rather than leaking a Netzob/BinaryInferno/NFStream/Scapy object.

## Integration rule with Track C

Track D proposes deterministic candidates and observations. Track C owns provenance fusion, LLM hypotheses, executable verification and final `ACCEPTED / REJECTED / UNCERTAIN` research decisions.

Do not make Track C depend on raw Netzob, BinaryInferno, NFStream, Scapy, or other third-party objects. Convert them at the adapter boundary.

## Do not own by default

- `src/course_project/evidence/`, `llm/`, `verification/` (Track C);
- `apps/desktop/` (Track B);
- shared schema/sidecar/CI changes without Track A review.

## First implementation sequence

1. deterministic `.dat -> InputMetadata + normalized MessageCandidate/PacketCandidate` path;
2. statistical features and boundary candidate scoring;
3. `MessageFamily` + `AlignmentResult` + `FieldCandidate` production;
4. one reproducible PRE baseline adapter behind those DTOs;
5. `BehaviorFeatures` extraction baseline;
6. fixtures/artifacts consumed by Track C experiments.

## Completion standard

A Track D feature is complete only when the same controlled input produces deterministic project-native output, tests cover edge cases, third-party dependencies are isolated behind adapters, and downstream Track C can consume the result without importing Track D implementation internals.
