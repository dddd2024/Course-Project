# Behavior evaluation claim discipline

This project separates **behavior prediction** from **behavior metric claims**.

`course_project.behavior.predict_behavior()` is a deterministic rule baseline over
observable flow features. Its output is a `BehaviorPrediction`; it is not evidence
that Accuracy, Precision, Recall or F1 are known.

## Unlabeled / descriptive path

When authoritative labels are unavailable, call:

```python
evaluate_behavior_predictions(predictions)
```

The result is intentionally:

- `metrics_evaluable = false`;
- `accuracy = null`;
- `macro_f1 = null`;
- an explicit `unavailable_reason`.

Synthetic fixtures may test code correctness, but must not be presented as
teacher/public behavior-classification benchmark results.

## Label-backed supervised evaluation

Supervised metrics are allowed only when:

1. labels cover **exactly** the predicted flow IDs;
2. every label uses the frozen vocabulary:
   `QUERY`, `DOWNLOAD`, `UPLOAD`, `HEARTBEAT`, `STREAM`, `UNKNOWN`;
3. the caller declares `split_unit="flow"` or `split_unit="session"`.

Packet-level splitting is rejected because packets from one flow/session can leak
across train/test boundaries and inflate reported performance.

The evaluation function is pure and does not train a model. It reports deterministic
accuracy and macro-F1 over the observed true/predicted label set.

## Open-source policy

Do not implement a custom RandomForest. When labeled teacher/public session data is
available and a supervised baseline is justified, prefer the mature open-source
`scikit-learn` implementation, with flow/session-level or stronger splitting.

NFStream may be used as an optional upstream flow-feature source when real traffic
format and environment make it appropriate, but third-party objects must still stop
at the adapter boundary and be normalized into project-native DTOs.

The runtime guard intentionally adds no installed-app dependency. The isolated
`public-benchmark` extra now pins scikit-learn 1.7.2 and dpkt 1.9.8. The completed
NFStream benchmark uses a capture/session-level 8/5 split and reports measured
test accuracy/macro-F1 of 0.600/0.375; see `docs/public-data-benchmark.md`.
