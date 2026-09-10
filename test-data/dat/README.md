# `.dat` test fixtures

This directory contains binary `.dat` files for manual desktop-app and pipeline testing.

The original three files are deterministic development fixtures. Public encrypted-traffic fixtures are kept separately in the same directory and are explicitly marked with provenance; they must not be confused with teacher-supplied data.

| File | Purpose | Provenance |
| --- | --- | --- |
| `controlled-syn1.dat` | Known synthetic framing for boundary/alignment/field-inference checks; mixed message sizes deliberately disambiguate the 16-bit total-length field | Project-generated synthetic fixture |
| `modbus-tcp-sample.dat` | Known Modbus/TCP request/response structure for protocol/restoration smoke tests | Project fixture; not encrypted traffic |
| `high-entropy-fixture.dat` | Deterministic high-entropy bytes for entropy/statistical-analysis smoke tests | Project-generated synthetic fixture; high entropy does not prove encryption |
| `public-dtls-snakeoil.dat` | Real packet-capture bytes containing DTLS encrypted traffic; useful for encrypted-traffic entropy/statistical/protocol-recognition smoke tests | Wireshark upstream `test/captures/snakeoil-dtls.pcap`; bytes retained, `.dat` extension used for this project's binary-input path |

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

## Public encrypted fixture provenance

`public-dtls-snakeoil.dat` is derived from the Wireshark project's public regression capture `test/captures/snakeoil-dtls.pcap`. The binary capture bytes are retained as-is and stored under a `.dat` extension so the desktop application's current `.dat` ingestion path can exercise a real encrypted-network-traffic sample. It is a regression/test sample, not teacher-supplied data and not a claim that every byte in the container is ciphertext: packet-capture headers, network headers, handshake material, and encrypted DTLS records are all present.

Upstream source:

- Repository: `wireshark/wireshark`
- Path: `test/captures/snakeoil-dtls.pcap`
- Upstream Git blob SHA: `ef5fd2110a0e0795e20c13c763e3d77d341b7b14`

## Recommended manual order

1. Open `controlled-syn1.dat` first to verify the basic `.dat -> analysis` path and confirm the accepted total-length field is `9:11` big-endian rather than `10:11`.
2. Open `modbus-tcp-sample.dat` to exercise recognizable plaintext protocol structure.
3. Open `high-entropy-fixture.dat` to exercise high-entropy/statistical behavior and abstention paths.
4. Open `public-dtls-snakeoil.dat` to exercise the same pipeline on public real encrypted network traffic.

For final course evaluation, teacher-provided `.dat` remains authoritative. Public encrypted fixtures are supplemental regression/evaluation inputs and must retain provenance in reports.
