# Wrong-hypothesis engineering demonstration

This repository includes a deterministic mechanism example for the Track C / WP3 acceptance requirement that an LLM-generated semantic guess must not become an accepted protocol fact merely because the model assigns it high confidence.

## What the example does

`course_project.experiments.run_wrong_hypothesis_engineering_demo()` builds five fixed synthetic messages. Each message stores its total length in a two-byte **big-endian** field at offset `0`.

The example then uses the normal project-native `DeterministicMockLLMProvider` / `LLMHypothesisProvider` boundary to materialize two competing structured hypotheses for exactly that byte range:

- correct: `big-endian total message length`, model confidence `0.62`;
- deliberately wrong: `little-endian total message length`, model confidence `0.93`.

The wrong interpretation therefore has the higher model confidence on purpose.

Both hypotheses reference the same allowed evidence record and are passed over the exact same five-message corpus to the production `verify_length` executable check. The resulting audit record preserves model confidence, verifier status/score, sample count, support count, violation count, provenance IDs, and competition links.

Expected mechanism result:

- lower-confidence big-endian hypothesis: `accepted`, 5/5 support, 0 violations;
- higher-confidence little-endian hypothesis: `rejected`, 0/5 support, 5 violations;
- the supported hypothesis set contains only the executable-evidence-backed big-endian interpretation.

This is the intended EvidenceGraph-PRE discipline: **model confidence proposes; executable evidence decides support.**

## Run locally

```bash
python -c "from course_project.experiments import run_wrong_hypothesis_engineering_demo; print(run_wrong_hypothesis_engineering_demo())"
```

The example is fully deterministic and network-free. It requires no API key and does not invoke a live provider.

## Open-source / dependency decision

The official OpenAI Python SDK and LiteLLM are valid open-source integration options for provider transport, structured output, or multi-provider routing. They are not required for this demonstration because the repository already owns the provider-neutral `LLMHypothesisProvider` boundary, strict structured materialization, and executable verifiers. Adding another provider SDK solely for this example would enlarge the normal runtime and Windows packaging surface without improving the scientific mechanism being tested.

Future multi-provider routing may sit behind the existing provider boundary. This example deliberately adds no runtime dependency.

## Claim boundary

This result is **engineering/mechanism evidence only**. It is not:

- a teacher-data benchmark;
- a live-LLM quality measurement;
- evidence of production LLM prompt quality;
- a Field Semantic Accuracy score;
- a comparison between model vendors.

Teacher-data and live-provider claims remain governed by the experiment-record ground-truth and result-scope rules.
