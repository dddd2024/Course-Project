# Tauri / Rust Shell

Owner: `@zhaohongjun20-creator`

Future Tauri 2 application code lives here.

Responsibilities:
- controlled file grants and range reads;
- task lifecycle (create/cancel/recover/fail);
- Python sidecar lifecycle;
- typed commands/events to the React UI;
- local SQLite/result metadata;
- no arbitrary program names or unrestricted shell parameters from the WebView.

The first implementation should consume `contracts/sidecar-message.schema.json` and use fixed-data contract tests before real analyzer integration.
