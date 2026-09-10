# Course Delivery Checklist

> Target course assessment: 2026-09-12. This file is the release/deliverable
> checklist, not a substitute for Track Issues.

## Scope decision

The repository owner fixed the pre-teacher-data closure scope on 2026-09-09:

- the separate non-author clean-Windows/VM rehearsal is waived; existing exact-main
  Windows CI plus the owner-host package/install/UI rehearsal is accepted;
- authoritative teacher-data execution and teacher-ground-truth metrics remain
  deferred until the files are supplied;
- a PowerPoint deck is not part of this delivery.

These are explicit scope decisions, not evidence that omitted work occurred.

On 2026-09-10 the owner superseded the data part of that decision: teacher `.dat`
is not used for this delivery; a hash-pinned public corpus and a derived plaintext
`.dat` complete the experiment path. The PPT exclusion remains unchanged.

## Product / demo

- [x] V1 deterministic analysis produces inspectable results with LLM/network off.
- [x] EvidenceGraph-PRE distinguishes `ACCEPTED`, `REJECTED`, and `UNCERTAIN`.
- [x] The executable verifier rejects a deliberately plausible, higher-confidence
  wrong-endian hypothesis in the frozen mechanism record.
- [x] Desktop shows file overview, Hex/offset navigation, progress/error state,
  findings and evidence linkage.
- [x] Structured result/schema/export artifacts can be reopened and inspected.
- [x] Demo has an offline path without mandatory live internet, credentials or an
  external Python installation.
- [x] Windows package build, install, launch, bundled Sidecar and uninstall passed
  in exact-main CI and in the documented owner-host rehearsal.

The additional non-author clean-Windows/VM run is waived for this delivery. The
teacher `.dat` import/execution test appears under the deferred section below.

## Technical documents

- [x] Task division and contribution evidence: `docs/team-division.md`, GitHub
  Issues/PRs and `docs/release-freeze.md`.
- [x] Technical principle and method description.
- [x] Overall architecture and editable text diagram: `docs/architecture.md`.
- [x] Detailed Track designs: `docs/tracks/`.
- [x] V1 design baseline: `docs/design-v1.md`.
- [x] V2 innovation design: `docs/design-v2.md`.
- [x] Research landscape and related work: `docs/research-landscape.md`.
- [x] Installation, build and usage instructions.
- [x] Open-source dependency/version/license register.
- [x] Known limitations and scientific claim boundaries.

- [x] Public-data testing/experiment report: `docs/public-data-benchmark.md`.

## Experiment evidence

- [x] Exact executable baseline SHA recorded.
- [x] Synthetic dataset identity/hash and result scope recorded.
- [x] Preprocessing/configuration recorded in canonical experiment records.
- [x] Model/provider/version recorded where the deterministic provider is used.
- [x] Mechanism baselines saved.
- [x] Full proposed-method mechanism result saved.
- [x] Required mechanism ablations saved.
- [x] Failures, abstention and uncertainty retained rather than deleted.
- [x] Result table is regenerated from and linked to canonical records.

Frozen mechanism records remain under `deliverables/pre-teacher/`; public formal
behavior and `.dat` E2E records are under `deliverables/public-benchmark/`.

## Submission / presentation assets

- [x] Final source tag name fixed as `v0.1.0-pre-teacher`; the exact tag target is
  recorded in Issue #99 after the delivery PR merges.
- [x] Architecture diagram finalized in `docs/architecture.md`.
- [x] Innovation comparison material finalized in `docs/release-freeze.md`.
- [x] Mechanism result table finalized in
  `deliverables/pre-teacher/README.md`.
- [x] Edge screenshot and bounded review export prepared.
- [x] Offline demo backup prepared as the frozen result/artifact/evidence bundle.
- [x] Installation/use guide checked against the successful owner-host rehearsal.
- [x] Contribution reporting points to actual Issues, PRs, tests, experiments and
  documents; it does not invent percentages from memory.

The user explicitly excluded a PPT from this delivery.

## Public-data replacement completion

- [x] Download and verify public upstream captures and expected-result labels.
- [x] Export public Modbus/TCP application payloads to the required `.dat` path.
- [x] Execute inference, evidence, verification and structured artifact generation.
- [x] Run rule versus RandomForest behavior evaluation with a capture/session split.
- [x] Record supported metrics and mark unsupported field/restoration metrics as not
  evaluable.
- [x] Preserve the teacher-data ingress for compatibility without using teacher
  data in this delivery.

A real-model cost/quality comparison is intentionally out of scope because this
delivery makes no real-provider claim and baseline CI remains credential-free.

## Freeze policy

Once `v0.1.0-pre-teacher` is created:

- no new feature is added unless it fixes a blocking acceptance failure;
- every change still goes through CI/PR;
- research novelty claims stay limited to implemented and measured evidence;
- teacher-provided evaluation files remain external unless redistribution is
  explicitly allowed;
- formal conclusions are updated only after teacher-data results are available.
