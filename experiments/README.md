# Experiments

Owner: Track C (`@sunny1ce`), with deterministic/PRE/behavior baseline inputs from Track D (`@zhaohongjun20-creator`) and reproducibility support from Track A (`@dddd2024`). Track B consumes experiment outputs for desktop/demo presentation but is not the baseline producer.

Use this directory for experiment manifests, scripts/configuration notes and result-table generation. Do not commit large raw datasets, teacher-provided raw `.dat` files without redistribution permission, or private captures.

Required V2 comparisons when the available ground truth supports them:
- heuristic baseline;
- Netzob/BinaryInferno-style baseline;
- LLM-only;
- LLM + deterministic verification;
- naive multi-source vote;
- full EvidenceGraph-PRE.

Required ablations when evaluable:
- w/o executable verification;
- w/o provenance;
- w/o LLM;
- w/o alignment.

Every formal experiment should record dataset identifier/hash/version, code commit SHA, configuration, random seed where applicable, model/provider version, dependency versions, metrics, unavailable-ground-truth notes, and output artifact references. Synthetic mechanism fixtures must be explicitly labeled as synthetic and must not be presented as teacher-data benchmark results.

Experiment ownership/support does not create a human merge-approval requirement; merge eligibility follows the current-version CI-only rule in `AGENTS.md`.

## Implemented evaluation harness

The offline harness has three layers:

- `metrics.py` computes deterministic boundary, semantic, false-hypothesis,
  count-ratio, and risk-coverage metrics;
- `runner.py` validates reproducibility metadata and builds deterministic JSON
  reports without serializing evaluation labels into result artifacts;
- `comparison.py` runs the canonical comparison/ablation matrix through a
  caller-supplied `ComparisonExecutor` before ground truth is used for scoring.

Canonical method names are `heuristic`, `netzob_binaryinferno`, `llm_only`,
`llm_verification`, `naive_vote`, and `evidencegraph_pre`. Canonical ablations
are `without_verification`, `without_provenance`, `without_llm`, and
`without_alignment`.

An executor receives only an `ExperimentVariant` and returns a `RunObservation`.
Pass those outputs and a separate `GroundTruth` object to
`build_comparison_report`. Missing labels are emitted as
`not evaluable from provided ground truth`; they are never replaced with a
fabricated zero or accuracy value. Per-variant failures are retained in
`execution_failures` unless fail-fast execution is explicitly selected.
