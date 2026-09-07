# Cross-Language Contracts

Owner: Track A (`@dddd2024`), reviewed by affected producers/consumers.

These schemas are the contract boundary between the Python analyzer, Tauri/Rust core and React/TypeScript UI.

Current skeleton:
- `sidecar-message.schema.json` — request/progress/result/error envelopes;
- `analysis-result.schema.json` — task-level analysis result reference and findings;
- `agent-response.schema.json` — human-readable answer plus structured evidence-linked findings.

Rules:
1. increment `protocolVersion` intentionally when compatibility changes;
2. add/update fixtures before changing producers and consumers;
3. large binary/table payloads are referenced, not embedded;
4. findings use evidence IDs and byte locations;
5. unknown/uncertain results remain representable.
