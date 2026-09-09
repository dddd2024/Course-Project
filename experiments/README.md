# Experiments

Owner: Track C (`@sunny1ce`), with deterministic/PRE/behavior baseline inputs from Track D (`@zhaohongjun20-creator`) and reproducibility support from Track A (`@dddd2024`). Track B consumes experiment outputs for desktop/demo presentation but is not the baseline producer.

Use this directory for experiment manifests, scripts/configuration notes and result-table generation. Do not commit large raw datasets, teacher-provided raw `.dat` files without redistribution permission, or private captures.

## Executable experiment contract

The project-native experiment record API lives in `course_project.experiments`.

It deliberately implements only the project-specific scientific contract:
- canonical V2 baseline and ablation names;
- dataset identity (`teacher / synthetic / other`, SHA-256, version and size);
- declared ground-truth capabilities;
- explicit `formal_benchmark` versus `mechanism` result scope;
- teacher-only formal benchmark claims;
- metric evaluability derived from declared ground truth;
- explicit not-evaluable metric records instead of fabricated numbers;
- exact code SHA, configuration, seed, model/provider/version, dependency versions and artifact references;
- deterministic canonical JSON/fingerprint;
- fail-closed same-dataset cross-variant metric comparison.

MLflow, Sacred, Hydra and BenchOpt were evaluated before adding the executable harness. They remain optional future orchestration/presentation layers rather than project dependencies: none encodes this repository's teacher-vs-synthetic claim discipline, canonical variants, ground-truth metric rules or Track D/Track C execution semantics. Project-native records remain authoritative and can be exported to a generic tracker later.

## Synthetic mechanism execution

`course_project.experiments.execution` and `scripts/run_synthetic_mechanism_experiments.py` execute a tiny redistributable `SYN1` corpus through real project components. The corpus is generated deterministically in code and its exact capture bytes determine the dataset SHA-256/version.

Current honest executable variants are:
- `heuristic`: real Track D boundary/inference candidates, with a fixed score-threshold control for executable `length`/`sequence` candidate types;
- `naive_vote`: the project `naive_multi_source_vote` control over real candidate/alignment/verifier evidence materialized by the production semantic path;
- `ablation_no_llm`: the current production Track D -> executable verification -> provenance-aware fusion -> global schema-promotion path with `llmEnabled=false`.

The current production `DeterministicTrackCSemanticBackend` does **not** call `LLMHypothesisProvider`. Therefore the harness deliberately does not emit an `evidencegraph_pre` record. Full EvidenceGraph-PRE remains unevaluated until a real LLM hypothesis source is connected to the evidence/fusion path. This prevents the no-LLM production path from being mislabeled as the complete proposed method.

Run locally from a Git checkout with a real 40-character commit SHA:

```bash
python scripts/run_synthetic_mechanism_experiments.py \
  --outdir experiment-results \
  --code-sha "$(git rev-parse HEAD)"
```

The command writes canonical per-variant JSON records, `comparison.json`, and `manifest.json` under `experiment-results/records/`. The dedicated `Synthetic Mechanism Experiments` workflow executes the same harness on GitHub Actions and uploads those files as a workflow artifact.

For this corpus no external ground truth is declared. Ground-truth-dependent metrics are therefore present as explicit `not evaluable from declared ground truth` records. `parse_coverage` is calculated by executing the **exact emitted field set** through the project provisional/Kaitai validation path. `constraint_satisfaction_rate` is calculated from linked executable-verifier evidence. Neither value is prefilled.

Schema execution is intentionally fail-closed. The experiment harness does not prune or rewrite a method's output merely to make it parseable. If a variant emits no fields, overlapping accepted fields, or another structurally invalid schema, its record sets `schemaExecutable=false`, retains the exact `schemaExecutionError`, and records `parse_coverage=0.0`. This preserves the distinction between per-hypothesis verification and globally executable schema validity.

PR #69 provided the historical evidence that motivated #70: the no-LLM production path could independently ACCEPT overlapping length hypotheses (for example bytes `9:11` and byte `10`) even though those ranges could not coexist in one executable schema. That historical artifact remains unchanged and correctly records `schemaExecutable=false` / zero ParseCoverage.

The #70 fix adds a separate project-native global promotion layer after per-hypothesis verification/fusion. Isolated accepted fields can be promoted directly. An overlapping conflict group gets a unique winner only when one candidate transparently dominates its peers on fusion margin, support, verification and conflict signals; scientifically tied or incomparable conflicts abstain rather than being resolved by ID, insertion order, randomness or a hidden scalar weight. Per-hypothesis fusion history remains auditable even when final schema promotion abstains. Fresh experiment runs after #70 must execute the exact resulting schema and therefore demonstrate the fix rather than rewriting the old #69 evidence.

`processing_time_seconds` is retained in exact run records as operational evidence. It is intentionally excluded from `scientific_record_fingerprint()` and from stable comparison identity, so wall-clock jitter cannot make otherwise identical scientific outcomes appear different. The stable comparison artifact currently compares `parse_coverage` and `constraint_satisfaction_rate` only.

## Live external PRE baseline record

The `netzob_pre` mechanism baseline deliberately **reuses upstream Netzob 2.0.0** through the existing Track D project-native adapter rather than implementing another PRE engine. Netzob remains a GPLv3 experiment/CI-only dependency and is not bundled into the Sidecar or desktop package. The dedicated `Netzob Baseline` workflow owns its isolated compatibility environment.

`course_project.experiments.external_pre` runs the exact existing `synthetic-mechanism-v1` corpus through real `run_netzob_baseline()` and preserves the resulting project-native `FieldCandidate` values as canonical, content-hashed evidence. The raw candidate artifact is `netzob-field-candidates.json`; its SHA-256 is stored both in the `netzob_pre` record and its artifact reference.

PRE field candidates are **pre-semantic**. Their `candidate_types`, scores and backend attributes are hypotheses/structure evidence, not Track C verification. To calculate structural ParseCoverage without changing the public model or pretending that PRE output was semantically accepted, the experiment layer creates an internal parser-only projection with `semantic_type="unknown"`, `verification_score=0.0`, no verification evidence, and `productionPromotion=false`. This projection is never emitted as a production `VerifiedField` result.

The external PRE record therefore follows these metric rules:
- `parse_coverage`: evaluable only by executing the exact structural ranges through the project provisional/Kaitai parser semantics; it is never hard-coded;
- `constraint_satisfaction_rate`: explicitly **not evaluable for raw PRE segmentation**, because no project semantic verifier was executed;
- field-boundary/semantic/restoration/risk metrics: explicit not-evaluable records on the synthetic corpus because the required ground truth is not declared;
- `processing_time_seconds`: real live upstream execution timing;
- `token_cost_usd`: zero for this non-LLM baseline.

The live command is intended for the isolated Netzob environment rather than the normal installed application:

```bash
python scripts/run_netzob_mechanism_experiment.py \
  --outdir netzob-experiment-results \
  --code-sha "$(git rev-parse HEAD)"
```

The `Netzob Baseline` GitHub Actions workflow installs the already documented compatible Netzob environment, runs the existing adapter smoke, runs the live experiment-record smoke, executes the command above, validates the scientific claim scope, and uploads `netzob_pre.json` plus `netzob-field-candidates.json` as canonical evidence. A successful mechanism record closes only the external-PRE execution gate; it does not establish teacher-data accuracy, LLM verification, or full EvidenceGraph-PRE performance.

## Required V2 research comparisons

Required comparisons when the available ground truth supports them:
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

The synthetic mechanism harness above proves execution/reproducibility only for the variants it actually runs. It must not be used to claim teacher-data accuracy or completion of unexecuted baselines/ablations.

Every formal experiment should record dataset identifier/hash/version, code commit SHA, configuration, random seed where applicable, model/provider version, dependency versions, metrics, unavailable-ground-truth notes, and output artifact references. Synthetic mechanism fixtures must be explicitly labeled as synthetic and must not be presented as teacher-data benchmark results.

A metric requiring unavailable labels must be recorded as `not evaluable from declared ground truth`, not omitted and not populated with a guessed value. Cross-variant result tables must use identical dataset identity and result scope.

Experiment ownership/support does not create a human merge-approval requirement; merge eligibility follows the current-version CI-only rule in `AGENTS.md`.
