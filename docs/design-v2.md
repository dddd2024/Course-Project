# V2 Design: EvidenceGraph-PRE

> Status: **Research Design Candidate V2**  
> Relationship to V1: V2 does not replace the V1 delivery pipeline. It refines the research contribution and reliability model while preserving the existing modules and course-project scope.

## 1. Working title

**EvidenceGraph-PRE: Provenance-Aware Executable Verification for LLM-Assisted Unknown Binary Protocol Inference**

中文工作题目：

> **基于证据溯源与可执行验证的大模型辅助未知二进制协议推断方法**

## 2. Problem statement

The V1 pipeline already combines statistical analysis, protocol inference tools, an LLM reasoner, deterministic verification, schema export, and behavior analysis. However, two reliability problems remain:

1. **A plausible semantic hypothesis may still be wrong.** LLM confidence or a single heuristic match is not enough to promote a field interpretation to a protocol fact.
2. **Multiple supporting signals may be dependent.** If the LLM reasons from a Netzob alignment result and then agrees with it, naive vote counting can incorrectly treat one upstream observation as two independent confirmations.

V2 therefore focuses on the following research question:

> Can unknown-binary-protocol inference become more reliable by requiring hypotheses to pass executable corpus-wide checks and by explicitly tracking evidence provenance/dependencies before confidence fusion?

## 3. Research contributions

### C1. Executable Hypothesis Verification

Every protocol-semantic claim is represented as a testable hypothesis. Where possible, the system generates executable constraints or a parser/specification and evaluates the hypothesis over the full eligible sample set.

A hypothesis is not accepted because the LLM says it is likely. It is accepted because the hypothesis has measurable empirical support.

Example:

```text
Hypothesis: bytes [4:6] encode message length.

Candidate interpretations:
H1 = big-endian full-packet length
H2 = little-endian full-packet length
H3 = big-endian payload length
H4 = big-endian value + header_size = packet length
```

For every interpretation, the verifier records:

- eligible sample count;
- support count;
- violation count;
- satisfaction ratio;
- conflicting evidence;
- parser execution result where applicable.

### C2. Provenance-Aware Evidence Fusion

Every piece of evidence must include its source and dependency chain.

```text
raw bytes
  ├─ entropy transition --------> E1
  ├─ length correlation --------> E2
  └─ Netzob alignment ----------> E3
                                  |
                                  v
                            LLM interpretation
                                  |
                                  v
                                  E4
```

E4 is derived from E2/E3 and must not be counted as a fully independent vote.

The confidence layer groups evidence by provenance/independence rather than summing every tool output equally.

## 4. Architecture delta from V1

V1 remains:

```text
Input
 -> Statistical Analysis
 -> Boundary Detection
 -> Clustering / Alignment
 -> Field Inference
 -> LLM Reasoner
 -> Deterministic Verifier
 -> Schema / Behavior Output
```

V2 refines the middle of the pipeline:

```text
Input
  |
  v
Feature / PRE Evidence Producers
  |
  v
Evidence Registry
  |
  v
Evidence Dependency Graph
  |
  +----------------------+
  |                      |
  v                      v
LLM Reasoner       Non-LLM Inference
  |                      |
  +-----------+----------+
              v
      Competing Hypotheses
              |
              v
     Executable Verification
       |       |       |
       v       v       v
   parser   semantic  consistency
   checks    checks      checks
       \       |       /
        \      |      /
         v     v     v
     Provenance-Aware Fusion
              |
      +-------+-------+
      |       |       |
      v       v       v
   ACCEPT   UNSURE   REJECT
      |
      v
Verified Protocol Schema
```

## 5. New core data model

V2 should extend the existing shared models with the following concepts.

### Evidence

```text
Evidence
- evidence_id
- source_component
- method
- feature_family
- target_hypothesis_id (optional)
- value / observation
- score
- parent_evidence_ids
- independence_group
- sample_ids / coverage
```

### ProtocolHypothesis

```text
ProtocolHypothesis
- hypothesis_id
- field_region
- semantic_type
- interpretation
- parameters
- model_confidence
- supporting_evidence_ids
- competing_hypothesis_ids
```

### ExecutableCheck

```text
ExecutableCheck
- check_id
- hypothesis_id
- check_type
- sample_count
- support_count
- violation_count
- score
- result
- evidence_ids
```

### VerifiedField

Only accepted hypotheses may be converted into `VerifiedField` objects for schema export.

## 6. Verification library

V2 should prioritize deterministic checks that are cheap and explainable.

### 6.1 Length checks

Evaluate:

- BE / LE integer;
- full-message length;
- payload length;
- length excluding fixed header;
- nested region length;
- constant-offset relationships.

### 6.2 Sequence checks

Evaluate:

- strict monotonic increase;
- monotonic with wraparound;
- per-session sequence;
- approximate monotonicity with missing messages.

### 6.3 Timestamp checks

Evaluate:

- plausible timestamp range;
- monotonicity within a flow/session;
- common timestamp units/epochs;
- endian interpretations.

### 6.4 Enum / message-type checks

Evaluate:

- low cardinality;
- stability across message families;
- association with clusters;
- optional association with protocol-state transitions.

### 6.5 Magic / constant checks

Evaluate:

- stable occurrence near inferred packet boundaries;
- family-specific constants;
- false occurrence rate inside payloads.

### 6.6 Checksum checks

Only test known checksum families that are practical for V2. Do not claim arbitrary checksum recovery.

## 7. Executable schema verification

The existing Kaitai/JSON export path becomes part of the verifier rather than only a final presentation feature.

Proposed loop:

```text
accepted field candidates
    -> provisional schema
    -> generated parser
    -> execute parser on corpus
    -> collect parse failures / inconsistencies
    -> update evidence
    -> revise or downgrade hypotheses
```

New primary metric:

```text
ParseCoverage = successfully_parsed_messages / eligible_messages
```

A high field-semantic score with low parse coverage must not be considered a successful result.

## 8. Provenance-aware confidence

V2 must avoid a fixed formula that pretends all evidence is statistically independent unless experimentally justified.

Minimum implementation:

1. assign every evidence record an `independence_group`;
2. preserve `parent_evidence_ids`;
3. collapse or discount multiple derived observations from the same source chain;
4. expose direct support, derived support, and conflicts separately in the result.

Example output:

```json
{
  "hypothesis": "field_3_is_length",
  "direct_support_groups": 2,
  "derived_support": 3,
  "conflicts": 1,
  "verification_score": 0.992,
  "decision": "accepted"
}
```

V2 should initially prefer transparent heuristics/discounting over a complex learned fusion model. A learned calibration model can be future work.

## 9. Uncertainty and abstention

Decisions remain three-way:

- `ACCEPTED`
- `REJECTED`
- `UNCERTAIN`

The system must be allowed to leave a region unresolved.

Evaluation should include risk-coverage behavior rather than only raw accuracy.

## 10. Optional cross-layer state consistency

If time permits, protocol state/session regularities may produce an additional evidence family.

Example:

```text
candidate field has values {1,2,3}
    +
value predicts valid message-family transitions
    -> additional evidence for MESSAGE_TYPE
```

This should be implemented as an optional evidence producer, not as a hard dependency of V2.

## 11. Encrypted-traffic behavior analysis position

Behavior classification remains part of the complete course project but is not the primary protocol-inference novelty.

V2 requires stronger evaluation hygiene:

- split at flow level or stronger;
- prefer cross-session/cross-day tests when possible;
- report ablations with shortcut-prone identifiers removed;
- compare full metadata with size/direction/timing-only features.

The behavior module should explicitly distinguish “classification performance” from “protocol restoration performance.”

## 12. Experiment design

### 12.1 Protocol inference baselines

1. statistical/heuristic baseline;
2. Netzob / BinaryInferno-style baseline;
3. LLM-only semantic inference;
4. LLM + deterministic rules;
5. multi-source naive vote;
6. **EvidenceGraph-PRE**.

### 12.2 Critical ablations

- full V2;
- w/o executable verification;
- w/o provenance discounting;
- w/o LLM;
- w/o alignment;
- optional w/o state evidence.

### 12.3 Primary metrics

- Packet Boundary F1;
- Field Boundary F1;
- Field Semantic Accuracy;
- False Hypothesis Rate;
- Parse Coverage;
- Constraint Satisfaction Rate;
- Restoration Accuracy;
- accepted-field coverage;
- risk-coverage curve;
- processing time;
- LLM token/cost usage.

## 13. Ground-truth dataset requirements

The existing Dataset A/B/C plan remains valid, but V2 must record enough ground truth to evaluate evidence and executable checks.

Each generated sample should preserve outside the analysis input:

- true packet boundaries;
- true field boundaries;
- true field semantics;
- message type;
- protocol/session state if available;
- plaintext where appropriate;
- encryption key only in the evaluation harness for controlled encrypted datasets;
- behavior label.

The inference pipeline must not read ground truth.

## 14. Acceptance criteria for V2 research prototype

V2 research implementation is considered minimally complete when:

1. at least three evidence producers generate provenance-tagged evidence;
2. at least length and sequence hypotheses support competing executable interpretations;
3. every accepted semantic hypothesis has a verification record;
4. dependent evidence can be demonstrated and discounted/collapsed;
5. at least one provisional schema/parser is executed over a corpus;
6. `ParseCoverage` is reported;
7. `LLM-only`, `LLM+verification`, and full `EvidenceGraph-PRE` are compared;
8. one example shows an initially plausible but wrong hypothesis being rejected or downgraded;
9. uncertainty/abstention is preserved rather than forcing a label;
10. results can be reproduced from controlled datasets.

## 15. Implementation priority

Recommended order:

```text
P0  Keep V1 end-to-end path runnable
P1  Evidence + Hypothesis data model
P2  Length / sequence executable checks
P3  Evidence provenance/dependency graph
P4  Provisional schema -> parser -> corpus execution
P5  Provenance-aware confidence / abstention
P6  Experiments and ablations
P7  Optional state-consistency evidence
```

## 16. Claim discipline

V2 must not claim that LLM-assisted PRE, RAG, entropy-based segmentation, multi-feature fusion, or joint field inference are new in themselves.

The research claim should be framed around **reliability of heterogeneous inference**:

> The project investigates whether executable corpus-wide verification and provenance-aware evidence fusion can reduce unsupported protocol-semantic conclusions produced by heterogeneous PRE algorithms and LLM reasoning, while retaining useful inference coverage.

This wording is the current V2 research baseline and should be revised only when new literature or experimental evidence invalidates it.
