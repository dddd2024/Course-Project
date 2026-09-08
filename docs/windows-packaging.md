# Windows Desktop Packaging

Track B packages the Python analyzer as a single-file executable and embeds it in the Tauri NSIS
installer. An installed Evidence Workbench therefore does not require a separate Python runtime.

## Build prerequisites

- Windows 10/11 x64;
- Python 3.11.x;
- Node.js 22.x and npm;
- current stable Rust with the `x86_64-pc-windows-msvc` host toolchain;
- Visual Studio C++ build tools and WebView2 prerequisites required by Tauri.

Install the project and packaging dependencies from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,package]"
cd apps\desktop
npm ci
```

`PyInstaller==6.22.2` is intentionally exact. The build fails with an actionable message when it is
missing or a different version is active.

## Build and verify

From `apps/desktop`:

```powershell
npm run sidecar:smoke
npm run bundle:windows
```

The first command creates
`src-tauri/binaries/course-project-sidecar-x86_64-pc-windows-msvc.exe` and exercises canonical
`register_input`, `read_range`, `analyze`, and `get_result` JSONL requests against that executable
with Python removed from its child-process environment. The second command rebuilds the same
Sidecar, repeats the smoke, and creates the NSIS installer under:

```text
src-tauri/target/release/bundle/nsis/*-setup.exe
```

Both outputs are generated artifacts and are excluded from Git. Always build them from the PR or
commit being rehearsed.

## Runtime selection

The release executable first looks for the bundled `course-project-sidecar.exe` beside the Tauri
application. Development and Rust tests fall back to `python -m course_project.sidecar` when the
bundled binary is absent.

The following environment variables are diagnostic overrides:

- `COURSE_PROJECT_SIDECAR_EXECUTABLE`: exact path to a packaged Sidecar executable;
- `COURSE_PROJECT_SIDECAR_COMMAND`: Python interpreter used by the development fallback;
- `COURSE_PROJECT_STATE_DIR`: exact controlled state directory.

Release builds default the state directory to `%LOCALAPPDATA%\Evidence Workbench\state`, which is
writable for a per-user NSIS installation. Debug builds retain `.course-project-state` under the
current working directory.

## Clean-machine rehearsal gate

On a clean Windows 10/11 x64 machine or VM:

1. copy only the generated `*-setup.exe` and an authorized test `.dat` file;
2. install and launch Evidence Workbench;
3. select the `.dat` file, inspect a Hex range, start analysis, and open the returned evidence and
   artifact views;
4. confirm no Python installation is present or used by the installed application;
5. retain the installer SHA-256, git SHA, Windows version, screenshots, and observed result status
   in the release/demo evidence directory agreed by the team.

This repository-side packaging work does not by itself complete the clean-machine acceptance item in
Issue #13. That item closes only after the separate machine/VM rehearsal evidence is retained.
