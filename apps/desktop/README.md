# Desktop D1: read-only binary workbench

The desktop app is a Tauri 2 + React + TypeScript workbench for controlled binary inspection.

## Run locally

From this directory:

    npm install
    npm run tauri dev

The browser fallback keeps the D0 task lifecycle available, but file selection and bounded byte reads require the Tauri desktop runtime.

## D1 flow

1. Select an authorized .dat, .bin, .pcap or .pcapng file.
2. The Rust shell computes SHA-256 and returns controlled InputMetadata.
3. The Hex view requests at most 256 bytes per page through read_range.
4. Use Prev/Next to move through ranges without loading the whole file.
5. Start the contract task to inspect task progress and failure states.

Raw input paths remain inside the Rust shell. The UI receives the basename, format, size, hash and capability flags; it never receives arbitrary shell access or an unbounded binary payload.
