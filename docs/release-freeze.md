# Pre-teacher-data release freeze

> Freeze date: 2026-09-09
> Scope: all repository work that does not require authoritative teacher data
> Application version: `0.1.0`

## Release decision

The project is feature complete for the pre-teacher-data scope. The repository
owner explicitly waived the separate non-author clean-Windows/VM reproduction on
2026-09-09 after reviewing the existing Windows CI and owner-host package rehearsal.
The same decision excludes a PowerPoint deck from this delivery.

Neither decision changes the scientific boundary. The project has not received or
tested authoritative teacher data and makes no formal benchmark claim.

The exact source snapshot is the `v0.1.0-pre-teacher` Git tag created after the
delivery PR passes the exact-current-base CI gate and is squash-merged. GitHub Issue
#99 records the tag target SHA and final CI runs. Executable evidence in
`deliverables/pre-teacher/` was regenerated from baseline
`347f2ff21819dfbff992074db2b67b51b4599efc`; the delivery PR adds only documentation
and frozen evidence assets.

## Frozen environment

| Component | Frozen contract or observed version |
|---|---|
| Python project | `>=3.10`; blocking CI uses 3.10 and 3.11 |
| Local Python rehearsal | 3.11.15 |
| Packaged Sidecar | PyInstaller 6.22.2 |
| Frontend | Node 22; `npm ci` against `apps/desktop/package-lock.json` |
| Local Node rehearsal | 22.23.2 |
| Desktop | React 18.3.1 family, Vite 8.2.2 family, TypeScript 5.6.3 family |
| Rust | stable toolchain; `Cargo.lock` and `--locked` |
| Local Rust rehearsal | 1.98.1 `stable-x86_64-pc-windows-msvc` |
| Package | bundled Python Sidecar inside Tauri 2 NSIS installer |

## Verification evidence

| Gate | Result |
|---|---|
| Current-main CI | success, run `34344822527` |
| Synthetic mechanism workflow | success, run `34344822469` |
| Python | Ruff and compileall passed; Pytest `486 passed, 3 skipped` |
| Frontend | Node 22 lockfile install/build passed; npm audit reported 0 vulnerabilities |
| Rust | `cargo check --locked` and Sidecar bridge round trip passed |
| Windows package | NSIS build, silent install, Sidecar start without external Python, desktop launch and uninstall passed |
| Offline analysis | 76-byte same-interface synthetic `.dat`, status `COMPLETED`, 3 findings, 12 evidence records, 1 verified field and 6 artifact types |
| Edge presentation | all 8 result views, evidence-to-offset navigation, local review and JSON export passed |

Package identities from the rehearsal:

- installer SHA-256:
  `1052924F49D0230F396A93D1141C54B682E97A2A9ECD7B5E92A73F23A354AB75`;
- installed desktop SHA-256:
  `0169473DD0DFBDC8C0B17601B4C78353059C7B501123165628480517B317F274`;
- installed Sidecar SHA-256:
  `6984AF8BD336366994DBC7CC5399190401DBEA9175C62AC04F0D261733351394`.

The checked-in evidence bundle and per-file hashes are documented in
[`deliverables/pre-teacher/README.md`](../deliverables/pre-teacher/README.md).
That bundle is the offline demo backup and contains the screenshot, UI review
export, inspectable analysis artifacts and regenerated mechanism results.

## Architecture and innovation summary

The finalized architecture diagram and contract boundaries remain authoritative in
[`docs/architecture.md`](architecture.md). In summary:

```text
registered bytes
  -> deterministic features / boundaries / PRE candidates
  -> provenance-linked evidence and competing hypotheses
  -> executable verification
  -> provenance-aware fusion and global abstention
  -> verified fields / JSON or Kaitai export
  -> Sidecar / Tauri / React evidence workbench
```

| Method | Executable verification | Provenance-aware fusion | Global conflict handling | Claim boundary |
|---|---:|---:|---:|---|
| Heuristic / external PRE | optional downstream | no | adapter-dependent | structural candidates |
| LLM-only | no | no | confidence ranking | hypotheses only |
| LLM + verification | yes | no | fail-closed abstention | verified hypotheses without dependency discounting |
| EvidenceGraph-PRE | yes | yes | conflict-aware global selection | evidence-linked verified fields |

The synthetic mechanism evidence shows why these layers matter. A deliberately
higher-confidence wrong-endian LLM hypothesis survives the LLM-only control, while
the executable verifier rejects it. The full method then emits an executable schema
with ParseCoverage 1.0 on this controlled corpus. This is a mechanism demonstration,
not a teacher-data accuracy result.

## Contribution evidence

GitHub's merged-PR ledger at the freeze audit provides an auditable contribution
record: `dddd2024` 42 merged PRs, `hinaLove1` 11, and
`zhaohongjun20-creator` 1. Those PRs report 284, 134 and 35 changed-file instances,
respectively. Issue ownership, experiment records, tests and documents provide the
qualitative context in [`docs/team-division.md`](team-division.md).

These counts are evidence, not a fair measure of effort. The project does not turn
line or PR counts into invented workload percentages. Any grading percentage must
be agreed by the team using this ledger and the linked Issue/PR history.

## Deferred until teacher data exists

Only the following work remains outside this freeze:

- execute the authoritative teacher `.dat` through the unchanged ingress;
- record its permitted identity/hash and supplied ground-truth capabilities;
- run only the baseline/proposed, behavior or restoration metrics supported by that
  ground truth;
- produce the teacher-data experiment report/table and update formal conclusions;
- run a real-model semantic-quality/cost comparison only if the final report elects
  to make that claim.

The arrival procedure and leakage controls are frozen in
[`docs/teacher-data-ingress.md`](teacher-data-ingress.md).

## 2026-09-10 public-data completion addendum

The owner subsequently replaced teacher-data execution with a pinned public-data
benchmark for the current delivery. This does not rewrite the historical
`v0.1.0-pre-teacher` evidence above. The new runner verifies 12 NFStream
capture/result pairs at commit
`1426d78597bbb8dcf556d65e9b413208c898444f`, exports 102 public Modbus/TCP
payloads to a 1,173-byte `.dat`, and runs the unchanged Sidecar analysis path.

The executed behavior comparison is rule accuracy/macro-F1 `0.000/0.000` versus
RandomForest `0.600/0.375` on a capture-disjoint 8-flow train / 5-flow test split.
The protocol-specific structural recognizer validates 102/102 Modbus messages and
restores 51 register values. The blind generic boundary F1 is
`0.409448818898`; field-boundary, semantic and independent restoration metrics
remain not evaluable because the public fixture does not provide that ground
truth. Full identities and claim boundaries are in
[`docs/public-data-benchmark.md`](public-data-benchmark.md) and
`deliverables/public-benchmark/`.
