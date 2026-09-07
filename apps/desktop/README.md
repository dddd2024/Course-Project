# Desktop D1: read-only binary workbench

The desktop app is a Tauri 2 + React + TypeScript workbench for controlled binary inspection.

## Run locally

From this directory:

    npm install
    npm run tauri dev

The browser fallback keeps the D0 task lifecycle available, but file selection and bounded byte reads require the Tauri desktop runtime.

## D1 flow

1. Select an authorized .dat, .bin, .pcap or .pcapng file in the Rust-owned dialog.
2. The Rust shell forwards the canonical register_input JSONL request to the Python Sidecar.
3. The Hex view requests at most 256 bytes per page through read_range.
4. Use Prev/Next to move through ranges without loading the whole file.
5. Start the contract task to inspect task progress and failure states. In the Tauri runtime, a registered input runs the canonical Sidecar `analyze` request; the completed task exposes a controlled `resultRef` and loads the result back into React through `get_analysis_result`.

The WebView receives only controlled metadata and validated result JSON. Rust owns the dialog and Sidecar process, while the Python Sidecar remains the authority for input identity, hashing, range reads and analysis result references. Result files are resolved only beneath the configured Sidecar state directory.

## D2 result views

Use **Load synthetic fixture** to exercise the result presentation before the full analyzer is connected. The preview is explicitly marked synthetic and renders the frozen AnalysisResult shape:

- Findings keep status, score sources, evidenceIds and byte locations.
- Evidence cards show provenance, parent evidence and observations.
- Artifact cards expose controlled result-relative refs without inlining large tables.
- Packet, alignment, statistics and behavior tabs remain artifact-backed until their producers are connected.
- Artifact metadata is summarized in the UI for boundary, alignment, statistics and behavior previews without loading large files.
- Export review JSON records local reviewer decisions and the source result reference; it contains no raw bytes.
- A finding location moves the Hex range to the referenced offset; it does not turn an uncertain claim into a fact.


### D2 local candidate review

Each finding exposes a local review control for `ACCEPTED`, `REJECTED` or `UNCERTAIN`, plus a correction draft. These controls are presentation-layer state only: they do not mutate the analyzer result, claim verification, or protocol contract. The summary makes the distinction visible so a reviewer can prepare a correction without presenting it as an accepted protocol fact.
