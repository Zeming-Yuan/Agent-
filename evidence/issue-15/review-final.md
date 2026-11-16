# T14 review (fixed point `b7cfc21`)

## Standards

Manual second-pass review against `AGENTS.md`, `docs/agents/domain.md`, `GLOSSARY.md`, the owner/lifecycle/admission ADRs, `OPERATIONS.md`, and `docs/IMAGE-SERVICE.md` found no documented-standard breach. The checker keeps owner and recovery evidence at the report boundary, uses stable diagnostic paths, and does not mutate service state or the parent issue. No actionable Fowler baseline smell was found in the changed modules. The requested reviewer subagent was attempted but unavailable because the selected model was at capacity; this manual audit is the recorded fallback.

## Spec

The first Spec review found three gaps: synthetic strings could pass, failure/identity/recovery drills were not required, and final-build runtime matching was optional. The implementation now requires SHA-256 file references, complete T11 profile reports matching `final_build.runtime_hash`, five failure drills with per-task execution counts, identity checks, recovery preservation checks, and nonzero CLI failure for missing evidence. A hash-backed complete fixture passes; synthetic and duplicate-execution fixtures fail.

Real Windows/macOS Harness use, same-service two-user execution, production backend recovery, key rotation/legacy takeover, and final hardware profile evidence remain unverified by design. The docs state these limits; the checker remains fail-closed until a private report supplies them.

## Verification

- T14 selector: 16 passed, 1 existing AnyIO deprecation warning.
- Affected T08/T09/T11 regression: 154 passed, 2 existing warnings.
- Full pytest: 514 passed, 1 existing AnyIO deprecation warning.
- `python -m compileall -q scripts services tests`: passed.
