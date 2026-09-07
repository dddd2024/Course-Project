# Dependency and Third-Party Register

> No third-party source code should be copied into the repository before its row is completed.

This register separates **candidate technology choices** from **accepted project dependencies**. Exact version and license must be verified against the upstream project at integration time; do not rely on memory or a blog post.

| Component | Intended role | Required for V1? | Track | Version/commit | License verified | Adapter/smoke status |
|---|---|---:|---|---|---|---|
| Python stdlib | core runtime | yes | A/C/D | Python 3.11.x | PSF | active |
| jsonschema | contract fixture validation | dev/CI | A | pinned by installer resolution until lock introduced | upstream verification required | active in CI |
| Scapy | PCAP normalization | optional until integrated | D | TBD | TBD | not integrated |
| NFStream | flow feature baseline | optional | D | TBD | TBD | not integrated |
| Netzob | PRE/alignment baseline | optional | D | TBD | TBD | not integrated |
| BinaryInferno | field-inference research baseline/reference | optional | D/C | TBD | TBD | not integrated |
| Kaitai Struct | `.ksy` schema/parser export backend | optional V1/V2 backend | A | emitted `ks-version: 0.10`; compiler version not pinned until compiler invocation lands | compiler license verification required before invocation | project-native `.ksy` exporter active; external compiler invocation not yet integrated |
| scikit-learn | behavior baseline | optional | D/C | TBD | TBD | not integrated |
| React | desktop UI | required when desktop scaffold lands | B | lockfile | upstream verification required | not scaffolded |
| Tauri 2 | desktop shell | required when desktop scaffold lands | B | Cargo/package lockfiles | upstream verification required | not scaffolded |

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
