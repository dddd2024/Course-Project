# LLM-only mechanism baseline

This baseline isolates the behavior of provider confidence without executable verification or provenance-aware fusion.

## Open-source / self-development decision

The project already has a provider-neutral `LLMHypothesisProvider`, an opt-in OpenAI-compatible live adapter, a deterministic network-free mechanism provider, and the canonical `ExperimentRecord` contract. Generic provider SDKs/gateways such as LiteLLM or the OpenAI SDK, and generic experiment frameworks such as MLflow/BenchOpt, do not define this repository's LLM-only scientific semantics. No new dependency is added for this baseline.

## Controlled design

The paired control first executes the same fixed `synthetic-mechanism-v1` corpus through the full EvidenceGraph-PRE production path using `deterministic-evidencegraph-mechanism` model version `1`. This materializes exactly the same provider hypotheses used by the full method.

The LLM-only projection then uses only provider hypothesis metadata for semantic selection:

- provider hypotheses are grouped by exact `(offset, size, semantic type)` region;
- the unique highest `modelConfidence` hypothesis wins each region; an exact confidence tie fails closed instead of being broken by ID or insertion order;
- executable-verifier evidence and verifier decisions are not used;
- provenance-aware fusion is not used;
- Track D candidate/alignment evidence does not contribute a selection score;
- the existing global non-overlap selector is reused after confidence-only per-region ranking;
- projected fields use `verification_score=0.0`, which explicitly means no executable verification was performed.

The deterministic fixture deliberately ranks a wrong-endian length interpretation at `0.97` and the correct interpretation at `0.61`. The paired full method must reject at least one such wrong hypothesis with executable verification, while the LLM-only baseline demonstrates whether confidence-only selection admits it.

## Metrics and claim boundary

`ParseCoverage` is derived by executing the actual confidence-selected provisional schema. `Constraint Satisfaction Rate` is explicitly not evaluable because the baseline performs no executable verification. Ground-truth-dependent semantic/boundary/restoration metrics remain not evaluable on this synthetic corpus.

This run is **mechanism evidence only**. It is not:

- a real-model LLM quality benchmark;
- a teacher-data benchmark;
- evidence of field semantic accuracy;
- a model-vendor comparison.

## Run

```bash
python scripts/run_llm_only_mechanism_baseline.py \
  --outdir experiment-results \
  --code-sha <40-character-git-sha>
```

Outputs under `experiment-results/records/`:

- `llm_only.json`
- `llm_only.audit.json`
- `llm-only-manifest.json`
