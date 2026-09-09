# Dependency and Third-Party Register

> No third-party source code should be copied into the repository before its row is completed.

This register separates **candidate technology choices** from **accepted project dependencies**. Exact version and license must be verified against the upstream project at integration time; do not rely on memory or a blog post.

| Component | Intended role | Required for V1? | Track | Version/commit | License verified | Adapter/smoke status |
|---|---|---:|---|---|---|---|
| Python stdlib | core runtime | yes | A/C/D | Python 3.11.x | PSF | active |
| jsonschema | contract fixture validation | dev/CI | A | pinned by installer resolution until lock introduced | upstream verification required | active in CI |
| Scapy | PCAP normalization | optional until integrated | D | TBD | TBD | not integrated |
| NFStream | flow feature baseline | optional | D | TBD | TBD | not integrated |
| Netzob | PRE/alignment research baseline | experiment/CI only | D, delegated live-smoke slice A (#46) | 2.0.0 (PyPI sdist) | GPLv3 (upstream setup/COPYING) | **live upstream validated** through project-native adapter in `Netzob Baseline`; normal runtime retains `dependency_unavailable` fallback |
| BinaryInferno | semantic field-inference research baseline | experiment/CI only | D, delegated core integration A (#66) | upstream commit `cb42a63ada74737c10d01e2c22f4502ba3983976` | GPL-3.0-or-later (upstream `LICENSE` and source headers) | isolated subprocess adapter + pinned live-smoke workflow; normal runtime retains `dependency_unavailable` fallback |
| Kaitai Struct | `.ksy` schema/parser export backend | optional V1/V2 backend | A | emitted `ks-version: 0.10`; compiler version not pinned until compiler invocation lands | compiler license verification required before invocation | project-native `.ksy` exporter active; external compiler invocation not yet integrated |
| scikit-learn | behavior / BinaryInferno experiment dependency | optional, experiment-only for BinaryInferno | D/C | workflow-resolved until upstream compatibility pin is required | BSD-3-Clause upstream | installed only in isolated BinaryInferno research workflow, not runtime |
| React | desktop UI | required for desktop MVP | B | 18.3.1 (package-lock.json) | MIT | active; Vite build |
| Vite + `@vitejs/plugin-react` | desktop frontend build and development server | build-only for desktop MVP | B | 8.2.2 / 6.1.1 (package-lock.json) | MIT / MIT | active; Node 22 baseline; production build and `npm audit` pass |
| Tauri 2 | desktop shell | required for desktop MVP | B | 2.11.5 (Cargo.lock) | Apache-2.0 OR MIT | active; cargo check |
| tauri-plugin-dialog | controlled file picker | required for desktop MVP | B | 2.7.3 (Cargo.lock) / Rust plugin | Apache-2.0 OR MIT | active; Rust-owned dialog smoke path |
| serde_json | Rust JSONL sidecar envelope | required for desktop MVP | B | 1.0.151 (Cargo.lock) | MIT OR Apache-2.0 | active; sidecar proxy serialization |
| [PyInstaller](https://github.com/pyinstaller/pyinstaller) | Windows Sidecar executable builder | build-only for desktop package | B | 6.22.2 (PyPI/GitHub tag) | GPL-2.0-or-later WITH Bootloader-exception; embedded run-time hooks Apache-2.0 | `python -m pip install -e ".[package]"`; Windows x64 + Python 3.11 packaging path; JSONL executable smoke; missing/wrong version fails the package build with an install instruction; no installed-app runtime dependency |

## Netzob 2.0.0 baseline reproduction

Decision: **reuse upstream Netzob rather than self-developing a second PRE engine**. The baseline is deliberately experiment/CI-only and is not bundled into the desktop or Python Sidecar runtime. No Netzob source is copied into this repository; third-party objects stay behind `src/course_project/inference/netzob_adapter.py`, and only project-native `FieldCandidate` values cross the adapter boundary.

Verified environment/evidence (2026-09-08):

- workflow: `.github/workflows/netzob-baseline.yml`;
- successful GitHub Actions run: `34224989305` (`Netzob Baseline` run #3);
- runner: Ubuntu 22.04.5 LTS (`ubuntu-22.04`);
- isolated interpreter: CPython 3.10.21;
- upstream package: `Netzob==2.0.0` from the PyPI sdist;
- required upstream build pin: `Cython==0.29.32`;
- system prerequisites: `build-essential libpcap-dev libgraph-easy-perl libffi-dev`;
- compatibility dependency: `minepy==1.2.6` + `numpy==1.24.1` from conda-forge. The normal PyPI dependency path was observed to fail under modern isolated builds while constructing `minepy`; conda-forge supplies a Python 3.10 binary build, so the upstream Netzob package itself remains unmodified;
- build tooling bound used by the smoke: `pip<27`, `setuptools<81`, `wheel`;
- install check: `pip check` passed and `importlib.metadata.version("Netzob") == "2.0.0"`;
- live adapter check: `pytest -q tests/integration/test_netzob_live.py` -> `1 passed`; this invokes the real `Format.splitAligned` path and requires `PREBaselineResult(status="ok")`, deterministic output, non-empty project-native `FieldCandidate` values, and `attributes["backend"] == "netzob"`;
- normal Python 3.10/3.11 and Windows CI intentionally do **not** install Netzob; `tests/unit/test_netzob_adapter.py` continues to prove fail-closed `dependency_unavailable` behavior when the optional dependency is absent.

Because Netzob is GPLv3, this project treats it as an isolated research baseline rather than an installed-app runtime dependency. Any future decision to redistribute/bundle it must receive a fresh license/redistribution review.

## BinaryInferno pinned baseline reproduction

Decision: **reuse upstream BinaryInferno rather than reimplementing its semantic-driven field inference algorithms**. Upstream repository: `binaryinferno/binaryinferno`, pinned to commit `cb42a63ada74737c10d01e2c22f4502ba3983976` (the current upstream `main` head observed at integration time). The upstream repository and `blackboard.py` source headers identify GPL-3.0-or-later licensing.

Integration boundary:

- workflow: `.github/workflows/binaryinferno-baseline.yml`;
- project adapter: `src/course_project/inference/binaryinferno_adapter.py`;
- upstream source is checked out by GitHub Actions into `.upstream/binaryinferno`; **no BinaryInferno source is copied or vendored into this repository**;
- normal V1/Sidecar/desktop runtime does not install BinaryInferno, SciPy or scikit-learn;
- adapter input follows upstream's documented contract: one hexadecimal message per stdin line;
- invocation uses `subprocess.run([...], shell=False)` from the upstream `binaryinferno/` directory with an explicit timeout and output-size bound;
- minimal live smoke uses only `length` and `length2BE` detectors, so GNU `parallel` serialization-pattern search is not required by the smoke;
- isolated smoke environment: GitHub-hosted `ubuntu-24.04`, CPython 3.10, project dev dependencies plus workflow-installed `scipy` and `scikit-learn`;
- output boundary parses exactly one documented `SPECSTART ... SPECEND` block and creates only project-native `FieldCandidate` values;
- fixed-width tokens such as `2V_BE` produce exact relative offset/size/endian; a variable/repetition token may be represented only when terminal. A non-terminal variable field fails closed because later byte offsets are not knowable from the SPEC text;
- upstream semantic descriptions are stored as baseline hints only. Adapter candidates carry `verification_status="not_verified"`, and no BinaryInferno score or description is promoted to executable verification or an `ACCEPTED` decision;
- missing checkout -> `dependency_unavailable`; invalid packet slices -> `invalid_input`; non-zero process failures -> `execution_failed`; timeout -> `timeout`; missing/duplicate/malformed/ambiguous SPEC output -> `output_invalid`;
- unit tests inject a fake runner and do not require BinaryInferno, network access or scientific dependencies;
- live integration test `tests/integration/test_binaryinferno_live.py` is enabled only when `BINARYINFERNO_ROOT` points to the separately checked-out pinned upstream tree.

The upstream README lists `scikit-learn` and `scipy` as Python requirements and GNU `parallel` for serialization-pattern search. It also states that a standalone integration algorithm and refactored detector interface remain roadmap work; this is why the project integrates the documented CLI/SPEC boundary instead of depending on an unstable in-process API.

Because BinaryInferno is GPL-3.0-or-later, it remains an isolated research/CI baseline. Any future bundling, redistribution or source modification requires a fresh license review and appropriate notices.

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
