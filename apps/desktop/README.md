# Desktop App Skeleton

Owner: `@hinaLove1` (Track B)

This directory will contain the local desktop workbench defined in `docs/desktop-app-guide.md`.

Planned structure:

```text
apps/desktop/
├── src/          # React + TypeScript UI
└── src-tauri/    # Tauri 2 + Rust shell
```

Implementation order:
1. D0 contract spike with fixed data;
2. D1 read-only import/overview/hex view;
3. D2 interactive inference/evidence views;
4. D3 behavior and controlled restoration;
5. D4 packaging and clean-machine demo.

The desktop must consume versioned contracts from `contracts/` and must not duplicate protocol-inference logic in the UI.
