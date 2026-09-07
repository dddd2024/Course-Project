# Research Landscape and Innovation Screening (2023–2026)

> Status: **Research Baseline — 2026-09-07**  
> Scope: unknown binary protocol reverse engineering (PRE), LLM-assisted protocol inference, encrypted traffic analysis, open-set classification, and evidence verification.

## 1. Purpose

This document records the current research landscape used to decide what this course project should and should not claim as innovation. The goal is not to maximize the number of techniques in the system, but to identify a contribution that is:

1. technically meaningful;
2. experimentally measurable;
3. feasible within a course-project schedule;
4. compatible with the existing V1 architecture;
5. differentiated from recent PRE and encrypted-traffic literature.

The course project targets controlled/authorized binary network data and `.dat` protocol-analysis tasks. It does **not** claim to break modern cryptography without keys.

---

## 2. Research landscape

### 2.1 Protocol-format and field inference

Recent PRE research already covers many ideas that should therefore be treated as baselines rather than primary novelty:

| Work | Venue / Year | Relevant capability | Implication for this project |
|---|---|---|---|
| BinaryInferno | NDSS 2023 | semantic-driven binary field inference; combines multiple field detectors | multi-detector field inference alone is not novel |
| DynPRE | NDSS 2024 | dynamic interaction with protocol implementations to improve inference | active probing itself is not novel |
| Automated Field Semantics Inference | IEEE TIFS 2024 | automated field-semantic inference | field semantic classification alone is not novel |
| FLINT | Computer Networks 2026 | entropy/association/alignment-oriented field inference, including variable-length fields | entropy + alignment should be baseline techniques |
| ExMOP | Computers & Security 2026 | multi-objective optimization for protocol inference | generic multi-feature fusion is not enough for novelty |
| EBPFI | The Computer Journal 2026 | self-supervised field-boundary inference | self-supervised boundary detection alone is not novel |
| ProField R-CNN | Computer Networks 2026 | joint field-boundary and semantic-label inference | joint boundary + semantic prediction is already occupied |

### 2.2 LLM-assisted PRE

By 2026, using an LLM in PRE is no longer sufficient as a standalone innovation claim:

| Work | Year | Relevant capability | Implication |
|---|---:|---|---|
| ChatPRE | 2026 | program analysis + LLM for segmentation / semantic inference | “LLM for PRE” is not novel by itself |
| FieldWeaver | 2026 | visual/texture boundary cues + LLM semantic inference + conflict resolution | statistical/visual features + LLM fusion is crowded |
| ICPPRAG | 2026 | multi-source protocol knowledge + RAG + LLM reasoning | RAG-based protocol knowledge augmentation is not novel by itself |

### 2.3 Protocol state inference

Protocol state machine inference is a mature PRE subproblem. Recent work also uses clustering/session similarity to infer state behavior. Therefore “infer a protocol state machine” should be an optional extension or cross-layer signal, not the only claimed novelty.

### 2.4 Encrypted-traffic classification

Encrypted-traffic classification already includes:

- packet- and flow-level representation learning;
- Transformer-based models such as ET-BERT / YaTC;
- multi-level interaction modeling such as MIETT;
- open-set / OOD traffic recognition;
- strong evidence that naive dataset splitting may produce spurious correlations and shortcut learning.

Therefore “use Transformer/deep learning for encrypted traffic classification” is not a sufficient project innovation.

---

## 3. Ideas explicitly rejected as primary novelty

The following may still be implemented as components or baselines, but should not be presented as the primary contribution:

- LLM analyzes an unknown protocol;
- protocol RAG / CVE-style knowledge retrieval;
- entropy for header/payload separation;
- sequence alignment;
- multi-algorithm voting;
- generic multi-feature fusion;
- self-supervised field-boundary detection;
- one model jointly predicts boundary and semantics;
- binary-to-image / visual texture modeling;
- LLM + visual/statistical feature fusion;
- standalone protocol state-machine inference;
- Transformer encrypted-traffic classification;
- packet + flow multi-scale modeling;
- open-set encrypted traffic classification as a standalone contribution.

---

## 4. Candidate innovation directions

### A. Executable Evidence Verification — **Primary recommendation**

**Research question:** Can protocol-semantic hypotheses produced by an LLM or PRE tool be converted into executable specifications and empirically verified over the full message corpus before being accepted as protocol facts?

Core loop:

```text
candidate evidence
      -> LLM / algorithm hypothesis
      -> executable schema / parser
      -> corpus-wide execution
      -> constraint checks
      -> ACCEPT / REJECT / UNCERTAIN
      -> feedback / alternative interpretation
```

Example for a candidate two-byte length field:

- H1: big-endian full-packet length;
- H2: little-endian full-packet length;
- H3: big-endian payload length;
- H4: big-endian value + constant header size = packet length;
- H5: length of a following nested field.

All hypotheses are executed across all eligible samples. Acceptance depends on measurable support and violation counts, not on LLM confidence alone.

Key metrics:

- parse coverage;
- constraint satisfaction rate;
- false-hypothesis rate;
- correction/rejection rate;
- semantic accuracy;
- calibration.

### B. Provenance-Aware Evidence Graph — **Primary recommendation**

**Research question:** How should a protocol inference system avoid double-counting dependent evidence when multiple tools or the LLM derive conclusions from the same upstream signal?

A naive system may count:

```text
Netzob alignment + LLM agreement = 2 votes
```

when the LLM was itself given Netzob's alignment output. These are not independent observations.

Proposed evidence record:

```text
Evidence {
  id,
  source,
  method,
  feature_family,
  parent_evidence_ids,
  target_hypothesis,
  score,
  independence_group
}
```

The Evidence Graph distinguishes:

- direct evidence from raw messages;
- derived evidence;
- correlated evidence;
- independent support;
- semantic interpretation generated from prior evidence.

Confidence fusion should operate on provenance groups rather than simple vote counts.

### C. Syntax–Semantic–State cross-layer consistency

Rather than treating format, semantics, and protocol state as a strict pipeline, use inferred state-transition regularities to feed back into field-semantic confidence.

Example: a low-cardinality field that strongly predicts valid state transitions receives additional evidence for `message_type` semantics.

Possible score:

```text
Score(H) = alpha * syntax_consistency
         + beta  * semantic_consistency
         + gamma * state_consistency
```

This has strong research value but is a larger implementation commitment than A+B, so it is a V2/V3 extension rather than the minimum course deliverable.

### D. Uncertainty / abstention for PRE

The system should be able to return `UNKNOWN` / `UNCERTAIN` instead of forcing every region into a semantic label.

Evaluation should include a risk-coverage curve:

- as acceptance threshold increases, how much of the protocol remains automatically covered?
- how quickly does the false-semantic rate decrease?

This aligns naturally with the existing `ACCEPT / REJECT / UNSURE` verifier design.

### E. Counterfactual field validation

On self-generated controlled protocols, create counterfactual message variants and check whether a candidate field responds as predicted.

Example: if a field is believed to encode payload length, increase payload size while keeping other semantics constant and verify the expected field change.

This must be positioned as controlled/offline consistency validation, not as a claim that active protocol probing itself is novel.

### F. Shortcut-resistant encrypted-traffic behavior analysis

Treat traffic classification as an evaluation-quality contribution rather than simply adding a deeper model.

Recommended tests:

- flow-level rather than packet-random split;
- cross-session split;
- cross-day split where data permits;
- remove IP/port or obvious header shortcuts;
- compare full features vs size/direction/timing-only features.

The goal is to measure whether the classifier learns behavior rather than capture artifacts.

---

## 5. Recommended research direction

The preferred V2 direction is:

# EvidenceGraph-PRE

**Provenance-Aware Executable Verification for LLM-Assisted Unknown Binary Protocol Inference**

Chinese working title:

> 基于证据溯源与可执行验证的大模型辅助未知二进制协议推断方法

### Primary contribution 1 — Executable Hypothesis Verification

LLM/tool hypotheses are transformed into executable protocol specifications or constraints, run against the corpus, and accepted only if measurable consistency criteria pass.

### Primary contribution 2 — Provenance-Aware Evidence Fusion

Evidence is tracked as a dependency graph so correlated/derived evidence is not counted as multiple independent confirmations.

Optional extensions:

- uncertainty-aware abstention;
- syntax–semantic–state feedback;
- shortcut-resistant behavior-classification benchmark.

---

## 6. Experimental matrix

Recommended protocol-inference comparison:

| Method | Statistics | PRE Tools | LLM | Executable Verification | Provenance |
|---|:---:|:---:|:---:|:---:|:---:|
| Heuristic baseline | ✓ |  |  |  |  |
| Netzob / BinaryInferno baseline | ✓ | ✓ |  |  |  |
| LLM-only | ✓ |  | ✓ |  |  |
| LLM + simple rules | ✓ |  | ✓ | ✓ |  |
| Multi-source vote | ✓ | ✓ | ✓ | ✓ |  |
| **EvidenceGraph-PRE** | ✓ | ✓ | ✓ | ✓ | **✓** |

Primary metrics:

- Packet Boundary Precision / Recall / F1;
- Field Boundary F1;
- Field Semantic Accuracy;
- False Hypothesis Rate;
- Parse Coverage;
- Constraint Satisfaction Rate;
- Restoration Accuracy;
- Calibration Error / Brier-style score where applicable;
- abstention risk-coverage;
- processing time;
- LLM token/cost statistics.

Critical ablations:

- full system;
- w/o executable verification;
- w/o provenance;
- w/o LLM;
- w/o alignment.

---

## 7. Research-claim discipline

The project must avoid claims such as “first LLM protocol reverse-engineering system” or “first evidence-based PRE system” unless a later systematic review can substantiate them.

Preferred wording:

> Existing PRE research increasingly combines learned representations, field-semantic inference, LLM reasoning, and multi-source information. This project focuses specifically on the reliability problem that arises when heterogeneous inference components produce correlated and potentially incorrect hypotheses. We study whether executable corpus-wide validation and provenance-aware evidence fusion can reduce unsupported protocol-semantic conclusions while retaining useful inference coverage.

---

## 8. References / papers to track

The implementation/report should cite and re-check the final bibliographic metadata for at least these research families before submission:

- BinaryInferno — NDSS 2023;
- DynPRE — NDSS 2024;
- automated field-semantics inference — IEEE TIFS 2024;
- FLINT — Computer Networks 2026;
- ExMOP — Computers & Security 2026;
- EBPFI — The Computer Journal 2026;
- ProField R-CNN — Computer Networks 2026;
- ChatPRE — JNCA 2026;
- FieldWeaver — Computer Networks 2026;
- ICPPRAG — Information Fusion 2026;
- recent protocol state-machine inference work;
- ET-BERT / YaTC / MIETT and later encrypted-traffic representation work;
- open-set encrypted-traffic classification work;
- SIGCOMM 2025 work on shortcut/spurious-correlation risks in encrypted-traffic representation;
- IEEE S&P 2025 SoK on encrypted-traffic classification methodology.

This document is a research-decision record, not the final bibliography. Exact title/author/DOI metadata must be verified again when writing the final report.
