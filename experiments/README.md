# Experiments

Owner: Track C (`@sunny1ce`), with deterministic/PRE/behavior baseline inputs from Track D (`@zhaohongjun20-creator`) and reproducibility review from Track A (`@dddd2024`). Track B consumes experiment outputs for desktop/demo presentation but is not the baseline producer.

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
