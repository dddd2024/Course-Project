# Dependency and Third-Party Register

> No third-party source code should be copied into the repository before its row is completed.

This register separates **candidate technology choices** from **accepted project dependencies**. Exact version and license must be verified against the upstream project at integration time; do not rely on memory or a blog post.

| Component | Intended role | Required for V1? | Track | Version/commit | License verified | Adapter/smoke status |
|---|---|---:|---|---|---|---|
| Python stdlib | core runtime | yes | A/C/D | Python 3.11.x | PSF | active |
| jsonschema | contract fixture validation | dev/CI | A | pinned by installer resolution until lock introduced | upstream verification required | active in CI |
| Scapy | PCAP normalization | optional until integrated | D | TBD | TBD | not integrated |
| NFStream | flow feature baseline | optional | D | TBD | TBD | not integrated |
| Netzob | PRE/alignment baseline | optional | D | 2.0.0 (PyPI sdist; not installable in current env) | GPLv3 (upstream COPYING) | adapter + `dependency_unavailable` fallback in repo; upstream smoke validation pending |
| BinaryInferno | field-inference research baseline/reference | optional | D/C | TBD | TBD | not integrated |
| Kaitai Struct | `.ksy` schema/parser export backend | optional V1/V2 backend | A | emitted `ks-version: 0.10`; compiler version not pinned until compiler invocation lands | compiler license verification required before invocation | project-native `.ksy` exporter active; external compiler invocation not yet integrated |
| scikit-learn | behavior baseline | optional | D/C | TBD | TBD | not integrated |
| React | desktop UI | required for desktop MVP | B | 18.3.1 (package-lock.json) | MIT | active; Vite build |
| Tauri 2 | desktop shell | required for desktop MVP | B | 2.11.5 (Cargo.lock) | Apache-2.0 OR MIT | active; cargo check |
| tauri-plugin-dialog | controlled file picker | required for desktop MVP | B | 2.7.3 (Cargo.lock) / Rust plugin | Apache-2.0 OR MIT | active; Rust-owned dialog smoke path |
| serde_json | Rust JSONL sidecar envelope | required for desktop MVP | B | 1.0.151 (Cargo.lock) | MIT OR Apache-2.0 | active; sidecar proxy serialization |
| [PyInstaller](https://github.com/pyinstaller/pyinstaller) | Windows Sidecar executable builder | build-only for desktop package | B | 6.22.2 (PyPI/GitHub tag) | GPL-2.0-or-later WITH Bootloader-exception; embedded run-time hooks Apache-2.0 | `python -m pip install -e ".[package]"`; Windows x64 + Python 3.11 packaging path; JSONL executable smoke; missing/wrong version fails the package build with an install instruction; no installed-app runtime dependency |

## Acceptance gate for a new dependency

A dependency is accepted only when its PR records:

- exact upstream repository/package;
- exact version, tag, release or commit;
- license identifier and any attribution/redistribution obligations;
- installation command;
- supported Python/Node/Rust/OS constraints;
- adapter boundary and project-native output type;
- smoke test or deterministic fixture;
- failure behavior when the dependency is missing;
- whether it is runtime, optional, dev-only or experiment-only.

## License discipline

Using an open-source library is not the same as copying its source. Prefer normal package/dependency use through adapters. If source, model weights, datasets, examples or substantial snippets are imported, preserve required notices and record them in `THIRD_PARTY_NOTICES.md` before merge.

Do not present third-party algorithms or code as self-developed project contributions.
