# Changelog

All notable course-project delivery changes are summarized here. The repository remains explicit about evidence scope: public/synthetic fixtures are development and reproducibility evidence, while authoritative teacher-data claims remain unavailable until that data is supplied.

## v0.1.0-pre-teacher.2 — 2026-09-10

### Added

- Chinese Tauri/React Evidence Workbench with session-only OpenAI-compatible LLM configuration.
- Reusable `.dat` fixtures for deterministic manual and regression testing.
- Content-based PCAP/PCAPNG detection, transport-payload extraction, and structural DTLS recognition.
- Public-data protocol/behavior benchmark evidence and auxiliary DARPA TC E3 classification notes.

### Changed

- Production Track D now preprocesses capture containers before unknown-protocol inference.
- Known DTLS input gates generic field inference instead of blind-scanning encrypted capture bytes.
- Windows Sidecar packaging uses `dpkt==1.9.8` as the packaged PCAP runtime parser while retaining Scapy as an optional adapter.
- Sidecar packaging now bootstraps the pinned PCAP runtime dependency as well as PyInstaller when the local packaging environment is incomplete.

### Fixed

- Native review JSON export and deterministic SYN1 length-width disambiguation.
- Windows packaging and live-LLM process opt-in.
- Stale desktop/Tauri scaffold READMEs were removed; the maintained desktop guide is `apps/desktop/README.md`.

### Release boundary

- This is a pre-teacher-data release. It does not claim teacher-data packet/field accuracy, semantic accuracy, or plaintext recovery performance.
- Correctly implemented modern encryption is not claimed to be broken without keys or other legitimate recovery material.
