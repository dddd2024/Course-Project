# Full EvidenceGraph-PRE mechanism execution

This experiment exists to prove that the **complete production architecture** can execute and emit an auditable project-native `ExperimentRecord` before teacher evaluation data or live-model credentials are available.

It is intentionally narrower than a real LLM benchmark.

## What is executed

The runner `scripts/run_full_evidencegraph_mechanism_experiment.py` sends the exact redistributable `synthetic-mechanism-v1` corpus through:

`Track D deterministic preprocessing -> production LLM-aware Track C -> executable verification -> provenance-aware fusion -> global field selection -> verified schema -> provisional parser execution`.

The provider is `deterministic-evidencegraph-mechanism`, model version `1`. It is a network-free deterministic fixture injected through the same `LLMHypothesisProvider` boundary used by the opt-in live provider. It deliberately gives a wrong endian length interpretation confidence `0.97` and the correct interpretation confidence `0.61`. The run is invalid unless executable verification rejects at least one of those higher-confidence wrong hypotheses and at least one correct provider hypothesis survives verification and fusion.

## Scientific claim boundary

The emitted record uses:

- `variant="evidencegraph_pre"`;
- `result_scope="mechanism"`;
- explicit provider/model metadata;
- `formalBenchmark=false`;
- `realLLMBenchmark=false`.

Therefore this run supports the claim **“the full EvidenceGraph-PRE mechanism executes through the production path”**. It does **not** support claims about real-model semantic quality, teacher-data accuracy, or superiority over LLM-only / LLM+verification baselines.

The synthetic corpus declares no external field/semantic ground truth. Metrics requiring such ground truth remain explicit not-evaluable records. `ParseCoverage` is derived by executing the exact final verified-field schema on the corpus. `Constraint Satisfaction Rate` is derived from executable-verifier evidence linked to the finally selected fields. Neither value is hard-coded.

## Why no new experiment framework

MLflow and BenchOpt were re-evaluated before this slice. They provide mature general tracking / benchmark orchestration, but the repository already owns the project-specific scientific contract: dataset identity, result scope, canonical variants, ground-truth evaluability, model/provider metadata, stable fingerprints and fail-closed comparison semantics. Adding a framework would not replace that logic and would expand dependencies, so this experiment reuses `course_project.experiments` directly.

## Outputs

The runner writes into the requested records directory:

- `evidencegraph_pre.json` — canonical `ExperimentRecord`;
- `evidencegraph_pre.audit.json` — mechanism audit proving provider execution and wrong-hypothesis rejection;
- `full-method-manifest.json` — dataset/model/scope identity plus timing-independent scientific fingerprint.

The existing `heuristic`, `naive_vote`, and `ablation_no_llm` bundle remains unchanged for backward compatibility. The dedicated `Synthetic Mechanism Experiments` workflow executes both the legacy bundle and this full-method mechanism run and uploads them together.

## Remaining research work

This mechanism record does not complete the separate real live-LLM experiment gates. `llm_only`, `llm_verification`, live-model full-method comparison, no-verification/no-provenance/no-alignment ablations, threshold sensitivity, and teacher-data formal evaluation remain separate work items until their prerequisites are actually available.
