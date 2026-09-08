# Generated Sidecar Binaries

Run `python scripts/build_sidecar.py --smoke` from the repository root. The script writes
`course-project-sidecar-$TARGET_TRIPLE.exe` here for Tauri's `externalBin` bundler.

The smoke exercises file registration, bounded reads, analysis and result lookup with Python removed
from the child process environment. Generated executables are ignored by Git. They must be rebuilt
from the current source before a Windows package is produced.
