# DARPA Transparent Computing Engagement 3 auxiliary data

This directory records the DARPA TC E3 dataset as an **auxiliary behavior/provenance-analysis source**, not as a `.dat` encrypted-payload fixture.

## Requested source

- Zenodo record: `https://zenodo.org/records/18450779?preview_file=DARPA-TC-E3-CSV.zip`
- Requested archive: `DARPA-TC-E3-CSV.zip`
- Upstream program: DARPA Transparent Computing, Engagement 3 (E3)

## Why it is kept outside `test-data/dat`

DARPA TC E3 is primarily host/system provenance and CDM event data produced by TA1 instrumentation. The official release describes Avro/CDM records covering process, file, network-flow, and other component interactions. These records are valuable for the course project's **data-access behavior analysis / behavior-type analysis** track, but they are not equivalent to an unknown encrypted network binary bitstream and therefore must not be presented as protocol-recovery `.dat` ground truth.

Use this source for:

- event/behavior sequence analysis;
- process/file/netflow relationship analysis;
- behavior-type classification experiments;
- provenance-aware correlation and attack-chain evaluation.

Do not use it as evidence that the `.dat` protocol parser has decoded encrypted network payloads.

## Ingestion status

The Zenodo preview endpoint was rate-limited during repository preparation, so the large `DARPA-TC-E3-CSV.zip` archive itself is intentionally **not vendored blindly**. Only CSV subsets that are verified to contain useful E3 event/provenance records should be added here later, with exact internal archive path, checksum, row count, and source provenance. This fail-closed rule prevents unrelated/derived CSVs from being mislabeled as encrypted traffic.

## Authoritative background

The DARPA E3 release states that the data is public-domain research data and organizes the main data by TA1 performer (`cadets`, `clearscope`, `fivedirections`, `theia`, `trace`) under the CDM18 schema. The official manifest also identifies which E3 topics contain the most complete usable data.
