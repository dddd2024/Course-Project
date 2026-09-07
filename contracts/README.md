# Cross-Language Contracts

Owner: Track A (`@dddd2024`), reviewed by affected producers/consumers.

These schemas are the contract boundary between the Python analyzer, Tauri/Rust core and React/TypeScript UI.

Current schemas:
- `sidecar-message.schema.json` — request/progress/result/error envelopes;
- `analysis-result.schema.json` — task-level analysis result and evidence-linked findings;
- `agent-response.schema.json` — human-readable answer plus structured evidence-linked findings.

Golden fixtures in `contracts/fixtures/`:
- `sidecar-request.json`;
- `sidecar-progress.json`;
- `sidecar-result.json`;
- `sidecar-error.json`;
- `analysis-result.json`;
- `agent-response.json`.

These fixtures are synthetic contract examples, not teacher-supplied evaluation data. They exist so Track A/B/C/D and CI can agree on message shape before the real analyzer and desktop application are complete.

Rules:
1. increment `protocolVersion` intentionally when compatibility changes;
2. update/add fixtures before changing producers and consumers;
3. every fixture must validate against its schema in CI;
4. large binary/table payloads are referenced, not embedded;
5. findings use evidence IDs and byte locations;
6. unknown/uncertain results remain representable;
7. no provider-specific, Netzob-, NFStream-, Scapy-, Tauri- or UI-internal object may cross this boundary;
8. a contract-changing PR describes old/new shape and affected Tracks.
