## Summary

<!-- What does this PR change and why? -->

## Owner / Track / Issue

- Owner:
- Track: A / B / C / D
- Linked Issue:

## Affected Areas

- [ ] shared contracts / models / architecture
- [ ] io / features / boundary / inference
- [ ] evidence / llm / verification
- [ ] behavior / experiments
- [ ] sidecar / exporters / integration
- [ ] desktop React / Tauri
- [ ] CI / environment / dependency configuration
- [ ] docs / examples

## Shared Interface / Contract Changes

- [ ] No shared interface changes
- [ ] Shared interface changed

If changed, describe:
- old contract:
- new contract:
- affected producer/consumer Tracks:
- schema + golden fixture updated:
- migration/compatibility plan:

## New / Changed Third-Party Dependency

- [ ] No dependency change
- [ ] Dependency changed and `docs/dependency-register.md` is updated
- [ ] Vendored/redistributed material changed and `THIRD_PARTY_NOTICES.md` is updated

If applicable, record exact version/commit, license, environment constraints, adapter boundary and missing-dependency fallback.

## How to Test

```bash
# exact commands
```

Environment-sensitive PRs should also record the relevant versions (`python --version`, Node/npm, Rust/Cargo as applicable).

## Evidence / Results

<!-- Tests, metrics, screenshots, fixture output, or reproducible result. -->

For research/experiment PRs include git SHA, data identifier/hash, ground-truth availability, config/model/provider and failure cases. Do not commit teacher-provided raw `.dat` files unless redistribution is explicitly allowed.

## Risks / Limitations

<!-- What is not solved yet? What may break? Which outputs remain UNCERTAIN? -->

## Checklist

- [ ] Started from current `main` and follows `AGENTS.md` / owned Track scope
- [ ] Tests added/updated where appropriate
- [ ] Contract fixtures validate if shared schemas changed
- [ ] No secrets, private captures, prohibited teacher data, or sensitive plaintext committed
- [ ] LLM-derived protocol claims are not marked accepted without verifier evidence
- [ ] Optional dependencies fail clearly instead of crashing unrelated pipeline stages
- [ ] Documentation updated for user-visible behavior, environment, dependencies, or shared contracts
- [ ] CI is green
- [ ] Another team member can reproduce the main result when this PR claims integration/demo readiness
