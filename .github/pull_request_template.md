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

## Merge Gate — CI Only

A PR is mergeable only when the current PR version, synchronized with current `main` when needed, has all blocking checks green:

- [ ] `test (3.10)` = success
- [ ] `test (3.11)` = success
- [ ] `windows-integration` = success
- [ ] `merge-gate` = success
- [ ] no merge conflict

Human approval, Code Owner approval, review-thread resolution, and `CHANGES_REQUESTED` are not merge requirements.

If the PR head changes or `main` changes after the valid CI evaluation, synchronize/rerun CI before merging. Do not reuse an older green run.

## Final Checklist

- [ ] Work stays within the intended Track or explicitly documents a cross-Track need
- [ ] Relevant tests/fixtures were added or updated
- [ ] Shared schemas/contracts are compatible or explicitly migrated
- [ ] Dependency/version/license records are updated when dependencies change
- [ ] No secrets, private captures, prohibited teacher data, or sensitive plaintext are committed
- [ ] LLM-derived protocol claims are not presented as accepted without verifier evidence
- [ ] User-facing or shared behavior changes are documented where needed
