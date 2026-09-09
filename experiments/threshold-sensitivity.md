# EvidenceGraph-PRE fusion-threshold sensitivity

This mechanism analysis measures how the current provenance-aware fusion decisions and final schema promotion respond to the two explicit production thresholds.

## Open-source / self-development decision

Generic tools were rechecked before implementation:

- Optuna `GridSampler` can enumerate parameter combinations;
- Hydra multirun can launch Cartesian sweeps;
- MLflow Tracking can log parameters, metrics, and artifacts.

The repository does not need an optimizer or experiment server for this slice. The required intervention is project-specific: materialize one fixed full EvidenceGraph-PRE evidence/verifier state, replay only the fusion thresholds, preserve executable-verifier vetoes, then run the existing global field selector and provisional schema executor. Adding a generic sweep framework would increase dependency and Windows/CI surface without replacing those semantics.

The implementation is therefore project-native and dependency-free.

## Fixed design

The analysis executes the deterministic full-method mechanism fixture **once** on `synthetic-mechanism-v1`. The resulting provider hypotheses, candidate/alignment/provider/verifier evidence, and executable-verification outcomes are reused unchanged for every sensitivity point.

Only two values vary:

- `acceptance_support_threshold`: `0.65`, `0.75`, `0.85`;
- `max_conflict_for_accept`: `0.15`, `0.25`, `0.35`.

This gives exactly nine predeclared points. `(0.75, 0.25)` is the current production default and must replay exactly to the production full-method fusion decisions and selected field ranges.

Held constant across all nine points:

- corpus bytes and dataset identity;
- deterministic provider/model and provider output;
- Track D field-candidate and alignment evidence;
- executable-verifier results and rejection vetoes;
- provenance dependency-collapse policy;
- global non-overlap field-selection policy;
- provisional schema execution semantics.

Every point records:

- accepted / rejected / uncertain fusion counts;
- globally selected field count and ranges;
- global conflict groups and abstained hypotheses;
- actual ParseCoverage from the selected schema;
- Constraint Satisfaction Rate from linked verifier evidence;
- whether fusion decisions or selected ranges changed from the production default.

A verifier-rejected hypothesis must remain rejected for every threshold point. If the default replay does not reproduce production behavior, the analysis fails closed instead of publishing a sensitivity artifact.

## No synthetic-data optimization claim

This is a **sensitivity analysis**, not hyperparameter tuning. The code does not search for, rank, or publish a "best" threshold pair. The summary reports stability/change regions only.

The artifact is mechanism evidence on a deterministic synthetic corpus. It does not establish:

- teacher-data accuracy;
- real-LLM semantic quality;
- field semantic accuracy;
- an optimal fusion threshold for deployment.

## Run

```bash
python scripts/run_threshold_sensitivity_analysis.py \
  --outdir experiment-results \
  --code-sha <40-character-git-sha>
```

Outputs under `experiment-results/records/`:

- `threshold_sensitivity.json`
- `threshold-sensitivity-manifest.json`
