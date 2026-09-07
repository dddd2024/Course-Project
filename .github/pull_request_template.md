## Summary

<!-- What does this PR change and why? -->

## Owner / Track / Issue

- Owner:
- Track: A / B / C / D
- Linked Issue:

## Scope

- [ ] Track-internal change
- [ ] Shared interface / cross-Track change

If shared/cross-Track, briefly describe the affected contract or consumer/producer:

## Test Evidence

```bash
# relevant local commands, if any
```

CI is the authoritative merge evidence.

## Risks / Limitations

<!-- What is intentionally not solved? What could still fail? -->

## Review and Merge — Three Gates

- [ ] **Gate 1 — Review:** one valid human approval from the correct reviewer
  - ordinary Track PR: any other team member
  - shared/cross-Track PR: Track A
  - Track A-authored shared/cross-Track PR: one affected Track owner
- [ ] **Gate 2 — CI:** current PR version has `test (3.10)`, `test (3.11)`, `windows-integration`, and `merge-gate` all green
- [ ] **Gate 3 — Blockers:** no active `CHANGES_REQUESTED`, no unresolved blocking thread, and no merge conflict

Automated Codex/GitHub review is advisory rather than a separate approval gate. If code changes after review/CI, re-check the three gates before merge.

## Final Checklist

- [ ] Work stays within the intended Track or explicitly documents a cross-Track need
- [ ] Relevant tests/fixtures were added or updated
- [ ] Shared schemas/contracts are compatible or explicitly migrated
- [ ] Dependency/version/license records are updated when dependencies change
- [ ] No secrets, private captures, prohibited teacher data, or sensitive plaintext are committed
- [ ] LLM-derived protocol claims are not presented as accepted without verifier evidence
- [ ] User-facing or shared behavior changes are documented where needed
