# `.dat` test fixtures

This directory contains small deterministic `.dat` files for manual desktop-app and pipeline testing.

These files are **test fixtures**, not teacher-supplied data and not claims of real captured encrypted traffic.

| File | Purpose | Size | SHA-256 |
| --- | --- | ---: | --- |
| `controlled-syn1.dat` | Known synthetic framing for boundary/alignment/field-inference checks | 57 B | `54aa75f705b615e7fa438efcaaac6842d75927c759aee14c5c1043c73db5f6dd` |
| `modbus-tcp-sample.dat` | Known Modbus/TCP request/response structure for protocol/restoration smoke tests | 92 B | `64d9ce6e78072f38f8df6363bccc4e749c0c524b09468214f70a9fe0dd7801a4` |
| `high-entropy-fixture.dat` | Deterministic high-entropy bytes for entropy/statistical-analysis smoke tests | 512 B | `1065097d31a45d444a9118cef517cf312ff67eb8c0a36ade5561887b8631181e` |

## Recommended manual order

1. Open `controlled-syn1.dat` first to verify the basic `.dat -> analysis` path.
2. Open `modbus-tcp-sample.dat` to exercise recognizable protocol structure.
3. Open `high-entropy-fixture.dat` to exercise high-entropy/statistical behavior and abstention paths.

For research/evaluation of actual encrypted traffic, continue using the pinned public PCAP corpus and teacher-provided data. Do not report these synthetic fixtures as real encrypted-traffic benchmark samples.
