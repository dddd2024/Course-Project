# DARPA Transparent Computing E3 behavior fixtures

This directory is an **auxiliary behavior-analysis fixture set** for the course requirement covering data-access behavior and behavior-type analysis.

It is deliberately separate from `test-data/dat/`:

- `test-data/dat/` contains byte streams intended for binary protocol, boundary, alignment, entropy and encrypted-payload analysis.
- this directory contains structured provenance/network-flow events intended for behavior/context analysis.

Do **not** rename these CSVs to `.dat` or claim that they contain encrypted packet payloads.

## Canonical processed dataset requested for this project

- Zenodo record: `https://zenodo.org/records/18450779`
- Concept DOI used by the Theseus release: `10.5281/zenodo.18450778`
- Archive: `DARPA-TC-E3-CSV.zip`
- Upstream raw dataset: DARPA Transparent Computing Engagement 3.

The Theseus release describes the archive as processed **CSV node and event tables derived from the raw E3 JSON logs**. Its preprocessing code emits the following four table families for each E3 dataset:

| Table | Relevant columns | Course use |
| --- | --- | --- |
| `netflow_node_table.csv` | `src_addr`, `src_port`, `dst_addr`, `dst_port` | network endpoint/flow identification and access-target analysis |
| `event_table.csv` | source/destination node, operation, event UUID, timestamp | access sequence, temporal behavior, behavior-type statistics |
| `process_node_table.csv` | process path/command and node identity | resolve which process initiated/received an access |
| `file_node_table.csv` | file path and node identity | resolve file/resource access targets |

For a compact local fixture, THEIA E3 is preferred first because it contains complete network-flow attributes in the audited E3 analysis and is a commonly used E3 behavior benchmark. The complete archive is intentionally **not vendored** into Git because the processed E3 corpus contains hundreds of millions of events and is far larger than a normal source repository fixture set.

## Files committed here

### `theia-e3-event-sample.csv`

A small real event-table excerpt compatible with the processed E3 schema. It is suitable for deterministic tests of:

- event ordering by `timestamp_rec`;
- repeated access detection;
- grouping by source/destination node;
- operation-frequency statistics;
- coarse access type classification (`EVENT_OPEN`, `EVENT_READ`, etc.).

The rows are cross-checkable through the public THEIA E3 mirror at `alafage/darpa_tc_e3_theia`, which publishes the processed tables under CC0-1.0 and references the DARPA E3/REAPr sources. The mirror is used only as a small-row retrieval surface; the requested Zenodo archive remains the canonical processed-dataset reference for this project.

### `theia-e3-attack-windows.csv`

Two public THEIA E3 attack-analysis windows retained as evaluation context. They are useful for testing time-window selection and behavior grouping; they are **not labels for the small event excerpt above**.

### `selection.json`

Records which tables from the full Zenodo CSV archive are useful to this project and why. This prevents future collaborators from importing the multi-hundred-million-event archive indiscriminately.

## Behavior vocabulary

The processed E3 tooling uses network/data-access operations including:

`EVENT_CONNECT`, `EVENT_EXECUTE`, `EVENT_OPEN`, `EVENT_READ`, `EVENT_RECVFROM`, `EVENT_RECVMSG`, `EVENT_SENDMSG`, `EVENT_SENDTO`, `EVENT_WRITE`, and `EVENT_CLONE`.

For course-level behavior analysis these can be grouped conservatively as:

- connection establishment: `EVENT_CONNECT`;
- receive: `EVENT_RECVFROM`, `EVENT_RECVMSG`;
- send/exfiltration candidate: `EVENT_SENDMSG`, `EVENT_SENDTO`;
- file/resource access: `EVENT_OPEN`, `EVENT_READ`, `EVENT_WRITE`;
- execution/process behavior: `EVENT_EXECUTE`, `EVENT_CLONE`.

A behavior type is a feature/interpretation, not proof of malicious intent. The same operation can appear in benign and attack activity.

## Scope limitation

DARPA TC E3 is host/provenance telemetry. It helps answer **who accessed what, when, and by which operation**. It does not contain the original encrypted packet ciphertext in these processed CSV tables. Therefore:

- use DTLS/QUIC `.dat` fixtures for binary protocol analysis and ciphertext statistics;
- use E3 CSV fixtures for behavior and access-pattern analysis;
- use teacher-provided `.dat` as the authoritative final evaluation data when supplied.
