# No-Provenance Ablation

Owner transfer: Track C research experiment -> Track A (`@dddd2024`) under #86.

## Question

Does EvidenceGraph-PRE behave differently when correlated/derived evidence is counted as if every record were independent?

The normal production fusion policy first collapses hard dependencies from `parent_evidence_ids` and `independence_group`, then averages the resulting independent components. This ablation keeps every other mechanism fixed and deliberately removes only that collapse step.

## Open-source versus project-native work

MLflow and BenchOpt remain appropriate generic experiment orchestration/tracking tools, but neither defines this repository's one-factor EvidenceGraph-PRE ablation semantics, teacher-vs-synthetic claim discipline, canonical variants, or metric-evaluability rules. The project therefore reuses its existing experiment harness and adds no runtime or experiment-framework dependency for this slice.

## Controlled design

The ablation uses the exact same:
- deterministic `synthetic-mechanism-v1` corpus;
- Track D candidate generation;
- deterministic network-free provider fixture and model version;
- provider hypotheses, including the deliberately higher-confidence wrong-endian proposal;
- executable verification and verifier veto;
- support/conflict acceptance thresholds;
- global non-overlapping field selection;
- provisional schema execution and metric contract.

The only changed factor is fusion dependency handling. The production path is executed unchanged first to materialize exact evidence. The experiment layer then replays each hypothesis over the exact finding-linked evidence while treating every raw evidence record as one independent component. Normal production code and default fusion remain unchanged.

The replay is considered a meaningful provenance ablation only if the paired production control demonstrates at least one hypothesis with `rawEvidenceCount > effectiveComponentCount`. Otherwise the run fails closed instead of emitting a vacuous ablation record.

## Outputs

`run_no_provenance_ablation()` emits a canonical `ExperimentRecord` with:
- `variant="ablation_no_provenance"`;
- `result_scope="mechanism"`;
- deterministic provider/model identity;
- `provenanceAwareFusionEnabled=false`;
- `provenanceCollapseEnabled=false`;
- `rawEvidenceTreatedAsIndependent=true`;
- real ParseCoverage / Constraint Satisfaction Rate from the replay-selected schema;
- ground-truth-dependent metrics explicitly not evaluable on the synthetic corpus.

The writer produces:
- `ablation_no_provenance.json`;
- `ablation_no_provenance.audit.json`;
- `ablation-no-provenance-manifest.json`.

The audit also records how many paired control hypotheses actually collapsed dependencies, the maximum raw-to-effective reduction, whether every ablation record remained independent, decision changes, verifier rejection of the deliberately wrong hypothesis, and final schema execution results.

## Claim boundary

This experiment is mechanism evidence only. It does not establish teacher-data accuracy, real-LLM semantic quality, or statistical superiority of the full method. Those claims require the corresponding authoritative data/model experiment gates in #9/#14.
