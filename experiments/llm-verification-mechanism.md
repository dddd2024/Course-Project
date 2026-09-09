# LLM + deterministic verification mechanism baseline

This baseline isolates the effect of executable verification on provider hypotheses while deliberately excluding provenance-aware evidence fusion.

## Open-source / self-development decision

The project already has a provider-neutral `LLMHypothesisProvider`, deterministic network-free mechanism provider, protocol-specific executable length/sequence verifiers, global field selection, schema execution, and canonical `ExperimentRecord` contract.

Mature OSS was rechecked before implementation:

- Z3 is an MIT-licensed cross-platform general theorem/constraint solver;
- LiteLLM is a mature multi-provider open-source gateway/SDK;
- MLflow is a mature open-source experiment/evaluation platform.

None replaces this repository's existing packet/field interpretation rules or the scientific definition of the `llm_verification` baseline. Adding Z3 for the already-implemented length/sequence checks would increase dependency and Windows packaging surface without replacing the project-specific corpus semantics. No new dependency is added.

## Controlled design

The paired control first executes the exact `synthetic-mechanism-v1` corpus through the full production EvidenceGraph-PRE path with `deterministic-evidencegraph-mechanism` model version `1`. This materializes the same provider hypotheses and real executable-verifier evidence used by the baseline.

The `llm_verification` projection then:

- considers only hypotheses emitted by `track-c-llm-provider`;
- requires exactly one matching `track-c-executable-verifier` record for every provider hypothesis;
- rejects `REJECTED` hypotheses and abstains from `UNCERTAIN` hypotheses;
- only verifier-`ACCEPTED` hypotheses can reach schema selection;
- uses model confidence only as a secondary ranking signal among verifier-accepted competing hypotheses;
- does not use provenance-aware fusion status, support/conflict scores, dependency collapse, alignment evidence, or Track D candidate evidence as acceptance evidence;
- reuses the existing global non-overlap selector and exact provisional-schema execution;
- keeps `VerifiedField.verification_score` equal to the real verifier score, never the model confidence.

The deterministic provider deliberately ranks a wrong-endian length interpretation at `0.97` and the correct interpretation at `0.61`. The verifier must reject the more confident wrong interpretation before any provenance-aware fusion is applied.

The first exact-head CI execution exposed an important second-stage behavior: correct lower-confidence provider hypotheses can pass executable verification yet still be **globally abstained** when overlapping verifier-accepted fields remain tied or incomparable without provenance-fusion signals. This is retained as experiment evidence rather than hidden. The baseline does not force-select a field simply to make a schema executable. That distinction is part of what separates this verifier-only baseline from full EvidenceGraph-PRE.

## Metrics and claim boundary

`ParseCoverage` is derived by executing the exact globally selected schema. If global selection abstains from all eligible fields, the experiment honestly records a non-executable/empty schema and zero coverage rather than rewriting output.

`Constraint Satisfaction Rate` is derived from the actual verifier evidence linked to the globally selected fields using the same project helper. Ground-truth-dependent boundary/semantic/restoration metrics remain explicit not-evaluable on the synthetic corpus.

This run is **mechanism evidence only**. It is not:

- a real-model LLM quality benchmark;
- a teacher-data benchmark;
- evidence of field semantic accuracy;
- a model-vendor comparison.

## Run

```bash
python scripts/run_llm_verification_mechanism_baseline.py \
  --outdir experiment-results \
  --code-sha <40-character-git-sha>
```

Outputs under `experiment-results/records/`:

- `llm_verification.json`
- `llm_verification.audit.json`
- `llm-verification-manifest.json`
