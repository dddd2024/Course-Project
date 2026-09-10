# `.dat` test fixtures

This directory contains small deterministic `.dat` files for manual desktop-app and pipeline testing.

These files are **test fixtures**, not teacher-supplied data and not claims of real captured encrypted traffic.

| File | Purpose | Size | SHA-256 |
| --- | --- | ---: | --- |
| `controlled-syn1.dat` | Known synthetic framing for boundary/alignment/field-inference checks; mixed message sizes deliberately disambiguate the 16-bit total-length field | 861 B | `97a116611b2eb40f3b57be8ebeb95bb761efb3fe4ee771b031be0659b5911dde` |
| `modbus-tcp-sample.dat` | Known Modbus/TCP request/response structure for protocol/restoration smoke tests | 92 B | `64d9ce6e78072f38f8df6363bccc4e749c0c524b09468214f70a9fe0dd7801a4` |
| `high-entropy-fixture.dat` | Deterministic high-entropy bytes for entropy/statistical-analysis smoke tests | 512 B | `1065097d31a45d444a9118cef517cf312ff67eb8c0a36ade5561887b8631181e` |

## `controlled-syn1.dat` ground truth

Each message uses this synthetic framing:

```text
0:4   magic = "SYN1"
4:5   message type
5:8   reserved
8:9   sequence
9:11  total message length, unsigned 16-bit big-endian
11:   payload
```

The three message totals are **19, 311, and 531 bytes**. Crossing 255 bytes is intentional: the low byte at `10:11` is `19, 55, 19`, so an incorrect 1-byte total-length hypothesis can no longer pass executable verification merely because all samples are short. The payload bytes are deterministic high-variation fixture data to avoid introducing an artificial periodic boundary signal.

## Recommended manual order

1. Open `controlled-syn1.dat` first to verify the basic `.dat -> analysis` path and confirm the accepted total-length field is `9:11` big-endian rather than `10:11`.
2. Open `modbus-tcp-sample.dat` to exercise recognizable protocol structure.
3. Open `high-entropy-fixture.dat` to exercise high-entropy/statistical behavior and abstention paths.

For research/evaluation of actual encrypted traffic, continue using the pinned public PCAP corpus and teacher-provided data. Do not report these synthetic fixtures as real encrypted-traffic benchmark samples.
