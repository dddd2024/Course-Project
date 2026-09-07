# React / TypeScript UI

Owner: `@zhaohongjun20-creator`

Future implementation lives here after the D0 contract spike. The UI should provide import, task status, Overview, Hex/Alignment, Statistics/Behavior, Restoration and Agent/Evidence views.

Rules:
- do not execute arbitrary shell commands;
- do not infer protocol semantics in the UI;
- use virtualized/range-based rendering for large binary data;
- all findings must retain links to evidence IDs and byte offsets;
- generated/hand-maintained TypeScript types must stay compatible with `contracts/`.
