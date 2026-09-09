# No-verification EvidenceGraph-PRE ablation

This experiment is a **mechanism-only** one-factor ablation for EvidenceGraph-PRE.

## Question

What changes when executable hypothesis verification is removed while the rest of the
mechanism remains fixed?

The ablation holds constant:

- `synthetic-mechanism-v1`;
- the deterministic network-free provider and its exact hypotheses;
- candidate, alignment and provider provenance evidence;
- provenance/dependency collapse;
- fusion thresholds;
- global field selection;
- exact provisional-schema execution.

Only executable verification is removed.

## Open-source decision

MLflow and BenchOpt remain useful generic experiment infrastructure, but neither defines this
repository's one-factor scientific semantics or its teacher-vs-synthetic claim discipline. The
repository already has `ExperimentRecord`, canonical variant names, metric evaluability rules and
deterministic mechanism runners.

Therefore this ablation adds **no new dependency**. It reuses the project-native full-method
fixture and the production provenance-aware fusion implementation.

## Implementation rule

The experiment first runs the full production mechanism to materialize the exact candidate,
provider, alignment and verifier evidence used by the paired control.

For the ablation replay:

1. executable-verifier evidence is excluded;
2. production provenance collapse and support/conflict aggregation are reused;
3. the verifier veto/acceptance gate is intentionally bypassed;
4. global selection receives a neutral verification score of `0.0` for every candidate;
5. the exact selected field set is executed by the provisional parser without pruning or rewriting.

The deterministic provider intentionally gives the wrong endian length hypothesis higher model
confidence (`0.97`) than the correct interpretation (`0.61`). The paired full-method control must
reject at least one such wrong hypothesis through executable verification. The no-verification
replay must show that removing that gate changes the treatment of at least one control-rejected
wrong hypothesis.

## Metrics and claim boundary

`ParseCoverage` is derived from the exact schema emitted by the ablation.

`Constraint Satisfaction Rate` is explicitly **not evaluable** for this ablation because the
executable verifier is the factor being removed. The experiment does not reuse control-verifier
results to manufacture that metric.

Metrics that require field/packet/semantic/restoration ground truth remain explicit
not-evaluable records because `synthetic-mechanism-v1` declares no such external ground truth.

This experiment does **not** claim:

- teacher-data accuracy;
- real-LLM semantic quality;
- formal benchmark performance;
- that an unverified hypothesis is safe for production export.

Normal production behavior remains verification-gated.

## Run

```bash
python scripts/run_no_verification_ablation.py \
  --outdir experiment-results \
  --code-sha "$(git rev-parse HEAD)"
```

The command writes:

- `ablation_no_verification.json`;
- `ablation_no_verification.audit.json`;
- `ablation-no-verification-manifest.json`.
