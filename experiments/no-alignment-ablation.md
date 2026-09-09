# Alignment-evidence ablation

This experiment records the repository's `ablation_no_alignment` mechanism variant with a deliberately narrow scientific definition.

## What is removed

The paired control and ablation both run the same deterministic `synthetic-mechanism-v1` corpus through Track D. That means message candidates, families, alignments and field candidates are materialized normally and deterministically. The ablation then changes exactly one Track C semantic input: the semantic backend receives `alignments=()`.

As a consequence, Track C emits no `track-d-alignment` evidence and alignment evidence cannot contribute to provenance-aware fusion. LLM hypotheses, executable verification, provenance collapse, fusion thresholds, global non-overlap selection and provisional schema execution remain enabled.

## What is not claimed

This is an **alignment-evidence contribution ablation**, not a claim that the entire PRE preprocessing pipeline ran without alignment. Track D still uses its normal alignment stage to keep downstream structural candidates frozen between control and ablation. The canonical record therefore states:

- `ablationScope = alignment_evidence_contribution`;
- `preprocessingAlignmentStillUsed = true`;
- `trackCAlignmentInputRemoved = true`;
- `alignmentEvidenceUsed = false`.

This distinction prevents a multi-factor experiment in which removing alignment would also change clustering/candidate generation and LLM context.

## Reproducibility and claims

The deterministic provider is network-free and deliberately emits a higher-confidence wrong-endian length hypothesis. Executable verification must still reject that wrong hypothesis in the ablation. Ground-truth-dependent metrics remain explicitly not evaluable on the synthetic mechanism corpus. The run is not a teacher-data benchmark and is not evidence of real-model semantic quality.

Run locally with:

```bash
python scripts/run_no_alignment_ablation.py --outdir experiment-results --code-sha <40-hex-commit>
```

Canonical outputs are:

- `ablation_no_alignment.json`;
- `ablation_no_alignment.audit.json`;
- `ablation-no-alignment-manifest.json`.
