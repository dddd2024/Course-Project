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

MLflow/Sacred/Aim are not runtime dependencies. They remain optional future presentation/storage layers: normalized project records may be exported to a generic experiment tracker later, but external tracking must not weaken these invariants.

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

A metric requiring unavailable labels must be recorded as `not evaluable from declared ground truth`, not omitted and not populated with a guessed value. Cross-variant result tables must use identical dataset identity and result scope.

Experiment ownership/support does not create a human merge-approval requirement; merge eligibility follows the current-version CI-only rule in `AGENTS.md`.
