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
5. Start the contract task to inspect task progress and failure states.

The WebView receives only controlled metadata. Rust owns the dialog and Sidecar process, while the Python Sidecar remains the authority for input identity, hashing and range reads.
