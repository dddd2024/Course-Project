# Cross-Language Contracts

Owner: Track A (`@dddd2024`), reviewed by affected producers/consumers.

These schemas are the contract boundary between the Python analyzer, Tauri/Rust core and React/TypeScript UI.

Current schemas:
- `sidecar-message.schema.json` — versioned request/progress/status/result/error envelopes and the canonical v1 command vocabulary;
- `analysis-result.schema.json` — task-level analysis result, findings, evidence records and artifact manifest;
- `agent-response.schema.json` — human-readable answer plus structured evidence-linked findings.
- `teacher-dataset-metadata.schema.json` — sanitized evaluation-corpus identity;
  `corpusKind` also permits a pinned `public` corpus under the migration in
  `docs/public-data-benchmark.md`.

Golden fixtures in `contracts/fixtures/` include request examples plus runtime response examples for registration, inspection, bounded byte-range reads, task status/progress, result refs and errors. `analysis-result.json` and `agent-response.json` remain the structured result examples.

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

## Sidecar v1 response vocabulary

Protocol messages are newline-delimited JSON. Every response keeps the request/task `id` and `protocolVersion=1`.

Immediate status responses use `event="status"`, a canonical `stage`, and a stage-specific `data` object:

- `registered` / `inspected` → `inputRef`, kind, size, SHA-256, source file name and capability flags;
- `range` → bounded Base64 bytes plus offset/length/EOF metadata;
- `task_status` → `taskId`, task status and optional `resultRef`.

Long-running work uses `event="progress"`, `stage`, and `progress` in `[0,1]`. Completed/partial task results are returned by controlled `resultRef` rather than embedding the entire result in stdout.

The task-status vocabulary is:

```text
QUEUED / RUNNING / COMPLETED / PARTIAL / FAILED / CANCELLED
```

`read_range` is capped at 1 MiB per request. The response payload is Base64 because stdout is JSON-only; large analysis tables/artifacts still use controlled result refs rather than Base64 embedding.

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

## Runtime implementation

The Python implementation lives in `src/course_project/sidecar/` and can be launched with either:

```text
python -m course_project.sidecar
course-project-sidecar
```

The default backend intentionally emits a `PARTIAL` result with no protocol claims until the real Track D/C analysis orchestrator is injected. This makes Track B integration testable without presenting mock protocol conclusions as actual analysis.

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
