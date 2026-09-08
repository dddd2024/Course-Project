# Development Environment Baseline

> Status: pre-implementation baseline for the four-person team.

The purpose of this document is to prevent environment drift while keeping optional research dependencies isolated.

## Canonical local environment

- OS for final desktop rehearsal: Windows 10/11 x64.
- Python: 3.11.x (`.python-version`). CI also checks 3.10 for compatibility.
- Node.js: 22.x LTS (`.nvmrc`).
- Rust: current stable toolchain through `rust-toolchain.toml`.
- Tauri: 2.x once Track B creates the desktop scaffold.
- Git: current stable Git with line-ending configuration that does not rewrite binary fixtures.

Exact Node package versions and Rust crate versions must be captured by the lockfiles created by the desktop scaffold (`package-lock.json`/`pnpm-lock.yaml` and `Cargo.lock`). Do not hand-edit lockfiles to resolve merge conflicts.

## Python setup

Recommended:

```bash
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

For Track B Windows installer work, install the separately pinned packaging extra:

```bash
python -m pip install -e ".[dev,package]"
```

The installed application does not require Python. PyInstaller is a build-time dependency used only
to produce its bundled Sidecar executable. See `docs/windows-packaging.md`.

Run before opening a PR:

```bash
python -m compileall -q src
ruff check src tests
pytest -q
```

## Environment doctor

After installing the project, run:

```bash
course-project-doctor
```

The doctor checks the repository's canonical environment markers and desktop lockfiles, verifies the active Python major/minor version, checks the required Node/npm/Rust/Cargo commands, and runs a Sidecar CLI smoke check. It exits non-zero when a required baseline check fails.

For machine-readable evidence:

```bash
course-project-doctor --json
```

The doctor reports the current OS as informational. Development may run on another OS, but the final desktop rehearsal remains a Windows 10/11 x64 gate.

## LLM configuration

Copy `.env.example` to `.env` locally. The default provider is `mock` so CI and offline development never require a secret or external model.

Real provider credentials must stay in `.env` or the user's secret store and must never be committed. Track C owns provider adapters; provider-specific SDK objects must not leak into shared project contracts.

## Heavy optional dependencies

Netzob, BinaryInferno-style tooling, NFStream and deep traffic models are optional adapters until a Track proves a reproducible environment. A missing optional dependency must surface as `dependency_unavailable` rather than crashing unrelated stages.

Before an optional dependency is accepted into the shared environment, record:

1. exact upstream project and version/commit;
2. license;
3. supported OS/Python constraints;
4. installation command;
5. adapter owner;
6. a smoke test;
7. fallback behavior when unavailable.

See `docs/dependency-register.md`.

## Environment evidence in PRs and experiments

For integration-sensitive work, `course-project-doctor --json` is the preferred baseline snapshot. Raw command output may still be included when a specific toolchain problem needs investigation:

```text
python --version
node --version
npm --version
rustc --version
cargo --version
```

Formal experiments additionally record git SHA, dataset identifier supplied by the course, random seed, model/provider configuration and dependency versions as required by `docs/testing-plan.md`.

## Clean-machine gate

Before the final course demo, Track B + Track A must reproduce install/start on a clean Windows machine or clean Windows VM using only repository instructions plus locally supplied course test data and secrets. Run `course-project-doctor --json` on that machine and retain the output with the final demo/release evidence.

Build the installer and follow the evidence checklist in `docs/windows-packaging.md` before this gate
is marked complete.
