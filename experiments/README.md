# Experiments

Owner: Track C (`@sunny1ce`), with baseline inputs from Track B and reproducibility review from Track A.

Use this directory for experiment manifests, scripts/configuration notes and result-table generation. Do not commit large raw datasets or private captures.

Required V2 comparisons:
- heuristic baseline;
- Netzob/BinaryInferno-style baseline;
- LLM-only;
- LLM + deterministic verification;
- naive multi-source vote;
- full EvidenceGraph-PRE.

Required ablations:
- w/o executable verification;
- w/o provenance;
- w/o LLM;
- w/o alignment.

Every experiment should record dataset/version, code commit SHA, configuration, random seed where applicable, model/provider version, metrics and output artifact references.
