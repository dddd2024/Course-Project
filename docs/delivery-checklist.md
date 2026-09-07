# Course Delivery Checklist

> Target course assessment: 2026-09-12. This file is the release/deliverable checklist, not a substitute for Track Issues.

## Product / demo

- [ ] Teacher-provided `.dat` file can be imported without modifying source code.
- [ ] V1 deterministic analysis path produces inspectable results even when LLM/network is unavailable.
- [ ] EvidenceGraph-PRE path clearly distinguishes `ACCEPTED`, `REJECTED`, and `UNCERTAIN`.
- [ ] At least one executable verifier demonstrates why a plausible hypothesis is accepted/rejected.
- [ ] Desktop app shows file overview, hex/offset navigation, progress/error state, findings and evidence linkage.
- [ ] Exported structured result can be reopened/reproduced.
- [ ] Clean Windows machine/VM rehearsal completed.
- [ ] Demo has an offline/fallback path and does not depend on live internet availability.

Owners: Track A + B for integration/demo, Track C/D for analysis correctness.

## Technical documents

- [ ] task division and contribution evidence — `docs/team-division.md` plus actual PR/Issue evidence;
- [ ] technical principle / method description;
- [ ] overall architecture / overview design — `docs/architecture.md`;
- [ ] detailed design of each Track;
- [ ] V1 design baseline — `docs/design-v1.md`;
- [ ] V2 innovation design — `docs/design-v2.md`;
- [ ] research landscape / related work — `docs/research-landscape.md`;
- [ ] testing and experiment report based on teacher-provided data;
- [ ] installation / build / usage instructions;
- [ ] open-source dependency/version/license register;
- [ ] known limitations and scientific claim boundaries.

## Experiment evidence

- [ ] exact git commit SHA recorded;
- [ ] teacher dataset identifier/hash recorded locally or in sanitized metadata;
- [ ] preprocessing/config recorded;
- [ ] model/provider/version recorded when LLM is used;
- [ ] baseline results saved;
- [ ] proposed-method results saved;
- [ ] required ablations saved;
- [ ] failures/uncertainty are retained, not silently deleted;
- [ ] figures/tables can be regenerated from recorded results.

Track C owns the research experiment table; Track D owns deterministic/PRE baseline evidence; Track A owns reproducibility/integration evidence.

## Submission / presentation assets

- [ ] final source snapshot/tag identified;
- [ ] PPT completed and reviewed for the 15-minute presentation/demo window;
- [ ] architecture diagram finalized;
- [ ] innovation comparison slide finalized;
- [ ] experiment result table/figure finalized;
- [ ] screenshots prepared;
- [ ] screen recording / demo backup prepared;
- [ ] installation/use guide checked by a teammate who did not write it;
- [ ] final task-division percentages supported by Issues/PRs/commits/tests/docs rather than estimated from memory.

Track B owns presentation/demo media coordination; all Tracks provide their technical content.

## Freeze policy

Once the demo candidate is declared:

- no new feature is added unless it fixes a blocking acceptance failure;
- every change still goes through CI/PR;
- research novelty claims are frozen to what is implemented and measured;
- teacher-provided evaluation files remain external unless redistribution is explicitly allowed;
- final tag/commit and environment versions are recorded before presentation.
