# Third-Party Notices

This file records third-party source code, model assets, datasets, examples or other materials that are copied, vendored or redistributed by this repository.

## Current status

At the pre-implementation readiness baseline, **no third-party source code or model asset is intentionally vendored in this repository**. Candidate libraries are referenced in `docs/open-source-stack.md` and controlled through `docs/dependency-register.md`.

When third-party material is added, record:

- project/material name;
- upstream URL;
- exact version/commit;
- license;
- files or directories affected;
- required copyright/notice text;
- modifications made by this project.

Normal package-manager dependencies should still have their version/license recorded in `docs/dependency-register.md`, even when their source is not redistributed here.

## PyInstaller 6.22.2 bootloader and run-time hooks

Windows packages built by `scripts/build_sidecar.py` embed the PyInstaller bootloader and run-time
hooks. PyInstaller is Copyright (c) 2010-2023, PyInstaller Development Team; Copyright (c)
2005-2009, Giovanni Bajo; based on previous work Copyright (c) 2002 McMillan Enterprises, Inc.

- Upstream: https://github.com/pyinstaller/pyinstaller/tree/v6.22.2
- License: GPL-2.0-or-later WITH Bootloader-exception
- Embedded run-time hooks: Apache-2.0
- Project modification: none; the released build tool packages this repository's Python entrypoint.

The upstream licensing terms grant permission to embed and distribute the compiled bootloader with
other programs. See https://github.com/pyinstaller/pyinstaller/blob/v6.22.2/COPYING.txt.
