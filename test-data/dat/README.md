# `.dat` test fixtures

This directory contains small `.dat` files for manual desktop-app and pipeline testing. It now has two fixture classes:

- **synthetic / known-protocol fixtures** for deterministic regression tests;
- **public captured encrypted-traffic derivatives** for protocol-recognition and ciphertext-analysis smoke tests.

None of these files are teacher-supplied data.

| File | Kind | Purpose | Size | SHA-256 |
| --- | --- | --- | ---: | --- |
| `controlled-syn1.dat` | synthetic | Known framing for boundary/alignment/field-inference checks; mixed message sizes deliberately disambiguate the 16-bit total-length field | 861 B | `97a116611b2eb40f3b57be8ebeb95bb761efb3fe4ee771b031be0659b5911dde` |
| `modbus-tcp-sample.dat` | known plaintext protocol | Modbus/TCP request/response structure for protocol/restoration smoke tests | 92 B | `64d9ce6e78072f38f8df6363bccc4e749c0c524b09468214f70a9fe0dd7801a4` |
| `high-entropy-fixture.dat` | synthetic | Deterministic high-entropy bytes for entropy/statistical-analysis smoke tests | 512 B | `1065097d31a45d444a9118cef517cf312ff67eb8c0a36ade5561887b8631181e` |
| `public-dtls-snakeoil-session.dat` | public captured encrypted traffic | DTLS UDP payload stream containing handshake/control records followed by encrypted application records; useful for protocol recognition, alignment, statistics and field inference | 1781 B | `f4310e24705fa487f24685222c2c324344c7f9db1014295bb1ad20df150859c9` |
| `public-dtls-snakeoil-application-data.dat` | public captured encrypted traffic | Ciphertext-focused stream containing the three post-handshake DTLS Application Data records from the same capture | 199 B | `42e9e5d08051785827a7c869cd5638bc7a327be1d330cf4e79de00de502acb8e` |

## Public DTLS fixture provenance

The two `public-dtls-snakeoil-*.dat` files are derived from Wireshark's public `snakeoil-dtls.pcap` test capture, which the Wireshark sample catalog describes as **DTLS handshake and encrypted payload**.

Derivation is deterministic:

1. parse the classic PCAP in capture order;
2. retain the 9 IPv4/UDP datagrams;
3. strip PCAP-record, Ethernet, IPv4 and UDP headers;
4. concatenate the UDP payloads without inserting synthetic delimiters;
5. for the application-only file, retain only the three DTLS ContentType `23` records with epoch `1`.

`public-dtls-snakeoil.source.json` records the original capture hash, exact source URLs, derived byte ranges, packet indices, endpoints and output hashes. The application-only file preserves the DTLS record headers; the record bodies remain encrypted bytes.

These are public test-capture derivatives, not claims of in-the-wild user traffic. Do not infer encryption from entropy alone: their encrypted-traffic label comes from the source capture's documented DTLS semantics and the post-handshake Application Data records.

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

1. Open `controlled-syn1.dat` to verify the basic `.dat -> analysis` path and the `9:11` big-endian total-length field.
2. Open `modbus-tcp-sample.dat` to exercise recognizable plaintext protocol structure.
3. Open `public-dtls-snakeoil-session.dat` to exercise recognizable encrypted-transport structure and mixed handshake/ciphertext analysis.
4. Open `public-dtls-snakeoil-application-data.dat` to exercise ciphertext-heavy statistical analysis and conservative semantic abstention.
5. Open `high-entropy-fixture.dat` as a negative/control case showing that high entropy by itself is not proof of encryption.

Teacher-provided `.dat` remains the authoritative final evaluation input when it becomes available.
