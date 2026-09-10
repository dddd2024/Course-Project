# Public-data benchmark and `.dat` completion

> Scope decision: on 2026-09-10 the repository owner replaced the unavailable
> teacher-data run with a reproducible public-data run for this delivery. A PPT is
> still excluded.

## Why this corpus

The benchmark uses the official test fixtures in
[`nfstream/nfstream`](https://github.com/nfstream/nfstream), pinned to commit
`1426d78597bbb8dcf556d65e9b413208c898444f`. NFStream declares LGPL-3.0 and
publishes a result CSV beside each capture. The result rows contain observed flow
packet/byte totals and nDPI application/category labels, so behavior labels do not
come from capture filenames or manual guesswork.

Raw PCAP/PCAPNG and generated `.dat` bytes are not committed. The runner downloads
only an allowlisted set of fixed HTTPS URLs, enforces a 16 MiB object bound, and
checks the exact byte size and SHA-256 before persisting a file. The checked-in
manifest records all identities needed to reproduce the run.

## Dataset and split

The behavior label mapping is deliberately small and explicit:

| Upstream expected-result condition | Project label |
|---|---|
| application contains `DoH_DoT` | `QUERY` |
| category is `Download` | `DOWNLOAD` |
| application contains `Upload` | `UPLOAD` |
| category is `Media`, after the upload rule | `STREAM` |

Training and test data are split by source capture, which is the session group
available in this corpus. No packet from one capture is present on both sides.
The committed run contains 8 training flows and 5 test flows across four classes.
This is a small diagnostic benchmark, not evidence of broad real-world
generalization.

For the required decrypted `.dat` path, the runner takes the public
`modbus.pcap`, extracts each non-empty TCP application payload in capture order,
and concatenates the 102 payload messages into a 1,173-byte `.dat`. The resulting
SHA-256 is
`41ffbf8930edc17d3c5f64bc49fca897797759cf4869b632dd33d17bb289e9c4`.
The upstream PCAP container and expected label never enter Sidecar inference.

## Executed results

| Evaluation | Result |
|---|---:|
| Rule behavior baseline, test accuracy | 0.000 |
| Rule behavior baseline, macro-F1 | 0.000 |
| RandomForest, test accuracy | 0.600 |
| RandomForest, macro-F1 | 0.375 |
| Modbus structural recognition | 102 / 102 messages |
| Read-Holding-Register requests/responses | 51 / 51 |
| Restored register values | 51 |
| Blind generic boundary inference, exact boundary F1 | 0.409448818898 |

The low rule and generic-boundary scores are retained as actual results. The
RandomForest is the mature scikit-learn implementation with 200 trees,
`class_weight="balanced"`, a fixed seed, and one worker for deterministic output.
The Modbus recognizer checks the MBAP protocol identifier and length invariant,
then restores function-code-3 request/response structure. Ground truth is kept out
of both feature extraction and the Sidecar analysis configuration.

The public corpus does not include independent field-boundary, field-semantic, or
full restored-message answers for this derived `.dat`. Those formal metrics remain
explicitly not evaluable rather than being filled with invented values. The
generic EvidenceGraph-PRE path completed and emitted messages, alignments,
evidence, statistics, 154 field candidates, and 125 findings; it promoted no field
to a verified schema on this corpus. The protocol-specific structural path is
therefore the successful recognition/restoration result, while the blind result
documents the remaining generalization limit.

## Reproduction

Use Python 3.10 or 3.11:

```powershell
python -m pip install -e ".[dev,public-benchmark]"
python scripts/run_public_benchmark.py
python -m pytest -q tests/test_public_corpus.py
```

Defaults:

- downloads: `data/raw/nfstream-public/` (ignored);
- temporary `.dat` and Sidecar state: `outputs/public-benchmark/` (ignored);
- sanitized evidence: `deliverables/public-benchmark/`.

The canonical checked-in evidence was generated against the `codeSha` recorded in
each experiment record. Re-running from another code revision intentionally
changes that field while preserving the pinned corpus identity.

## Contract migration

The experiment contract now accepts `corpusKind="public"` as a formal benchmark
source when its identity and available ground truth are declared. Synthetic and
unidentified `other` corpora are still mechanism-only. The baseline vocabulary
adds `random_forest`, and the metric vocabulary adds `behavior_accuracy` and
`behavior_macro_f1`, both requiring `behavior_labels` ground truth. Existing
teacher and synthetic records are unchanged.
