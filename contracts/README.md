# Cross-Language Contracts

Owner: Track A (`@dddd2024`), reviewed by affected producers/consumers.

These schemas are the contract boundary between the Python analyzer, Tauri/Rust core and React/TypeScript UI.

Current schemas:
- `sidecar-message.schema.json` — versioned request/progress/result/error envelopes and the canonical v1 command vocabulary;
- `analysis-result.schema.json` — task-level analysis result, findings, evidence records and artifact manifest;
- `agent-response.schema.json` — human-readable answer plus structured evidence-linked findings.

Golden fixtures in `contracts/fixtures/`:
- `sidecar-register-input.json`;
- `sidecar-request.json` (`analyze`);
- `sidecar-read-range.json`;
- `sidecar-progress.json`;
- `sidecar-result.json`;
- `sidecar-error.json`;
- `analysis-result.json`;
- `agent-response.json`.

These fixtures are synthetic contract examples, not teacher-supplied evaluation data. They exist so Track A/B/C/D and CI can agree on message shape before the real analyzer and desktop application are complete.

## Sidecar v1 method vocabulary

Do not invent method aliases. Protocol version 1 reserves:

- `register_input`;
- `inspect_file`;
- `analyze`;
- `cancel_task`;
- `get_result`;
- `read_range`.

The canonical `analyze` configuration uses:

- `inputRef`;
- `mode: baseline | evidencegraph`;
- optional `stages[]`;
- `llmEnabled`;
- `verificationEnabled`;
- `behaviorEnabled`;
- `timeoutSeconds`;
- `optionalDependencyPolicy: degrade | fail`.

## Decision status

Conceptually the project has exactly three semantic decisions:

```text
ACCEPTED / REJECTED / UNCERTAIN
```

JSON/TypeScript/Rust use the uppercase values. Python internal models use `accepted / rejected / uncertain`. `ACCEPT / REJECT / UNSURE` are legacy wording and must not be introduced as enum values.

## Result artifact model

Small findings and evidence records can live in `analysis-result.json`. Large tables/binary-derived views are referenced through `artifacts[]` instead of being embedded in sidecar JSON.

Supported artifact types:
- `evidence`;
- `packets`;
- `messages`;
- `alignment`;
- `statistics`;
- `behavior`;
- `restored`;
- `schema`;
- `report`.

Every artifact includes `artifactId`, `type`, `format`, and a controlled result `ref`; optional `count`/`metadata` may be included.

## Contract rules

1. increment `protocolVersion` intentionally when compatibility changes;
2. update/add schemas and fixtures before changing producers and consumers;
3. every golden fixture must validate against its schema in CI;
4. large binary/table payloads are referenced, not embedded;
5. findings use evidence IDs and byte locations;
6. unknown/uncertain results remain representable;
7. no provider-specific, Netzob-, NFStream-, Scapy-, Tauri- or UI-internal object may cross this boundary;
8. a contract-changing PR describes old/new shape and affected Tracks;
9. sidecar methods are task-level operations, never unrestricted shell commands;
10. result/artifact refs are controlled references, not arbitrary WebView-provided filesystem paths.
