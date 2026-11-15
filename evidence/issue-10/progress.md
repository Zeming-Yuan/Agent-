# T09 / issue 10 execution ledger

Single-ticket offline implementation authorized by user despite #9/#24 OPEN. Public seams confirmed: admit/released, real HTTP/auth/SQLite/serial-worker lifecycle, deployment configuration fail-closed. Fixed source base da2acfb62b8abd478f18b4cc84b448e87003ed66. Source checkout /home/clusteradmin/.codex/workspaces/agent-mm-issue-8-20261115; branch feat/issue-10-safe-admission. Original product directory non-Git. All tracked code/test/deploy/script preimages matched it at start; no initialization/upload of product directory.

Actual commands from README, T09 plan and issue: supported product .venv/bin/python -m pytest, narrowed to affected files/selectors per user's override of full-suite skill defaults. No package.json/Makefile/CI/type/lint/build gate configured. N/A: configured type checker, static lint, build, CI, Compose/seed, security/mutation scanner. Production/hardware/desktop/platform/recovery 未验证. No real backend, guard, model, service or database operations.

Baseline selector tb07 or unknown_submit_outcome or unavailable_backend_rejects: 30 passed. Existing AnyIO deprecation retained.

01 low-memory policy RED missing module -> GREEN 1. 02 invalid/missing/stale/future/container/budget/nonfinite evidence RED 18 -> GREEN20. 03 release continuity and identity RED13 -> GREEN33. 04 HTTP queued wait/recover same task RED missing injected seam -> GREEN34. First implementation exposed a read-order defect (clock captured before sampler, yielding a future sample); moved now capture after sample, preserving strict future-sample refusal. 05 default deployment health RED200 -> GREEN35.

Ruling: always request cold release until calibration supports a proven hot-residency budget. A conservative cold increment avoids reusing unproven previous-profile assumptions; cost is extra release/cold-load latency. No performance claim. T11 owns real profile calibration/enablement.

Ruling: pending release requests keep tasks queued/waiting_resources; explicit queued cancellation may become cancelled before release ACK, but worker control stays held until that request settles. This follows T09 queued-wait/cancel semantics while retaining T07's no-overlap control boundary. Two T07 expectations updated; running inference still remains cancelling until backend cleanup completes.

Slice A: policy, correlated continuous release proof, queued waits, same-task recovery and final pre-prompt recheck. Explicit synthetic resources are injected by existing integration fixtures, never production defaults. Slice B will add full envelope/config loading and fault/recovery matrix. No claim of full ticket acceptance at slice A.

Slice A fresh affected selection65passed; no full gates run. Test capture Bearer values redacted and trailing whitespace normalized before commit. ADR0004 used to avoid confusing existing ADR0002 task lifecycle.

A independent review: Standards1P1 / Spec2P2 (review-a.md). All three findings reproduced separately06/07/08 RED→GREEN. No rulings/deferred findings. Slow external setup now precedes admission; no internal state collaborator mocks used. Re-review required by user after fixed repair commit.

A repair affected selector68passed, one existing warning; observer-open regression also repaired before commit. No full gates/hardware.

A re-review: Spec0 (independently3focused passed); Standards found one new P2: static reserve guard moved ahead of wait. 10RED→GREEN routes this through admission and preserves the existing fallback guard only for calls without an admission object. Included in slice B review, not dismissed.

B cycles:09invalid budget/envelope RED8→GREEN9;11reference pixel envelope RED→GREEN;12pinned private safe-start config RED12→GREEN12;13missing sampler errors RED→GREEN7;14factory config load RED→GREEN;15startup cleanup infinite retry RED→one-attempt stop GREEN;16cached reads RED→GREEN;17brief headroom spike RED→GREEN;18additional external-fault/permission/idem/profile/CLI regression matrix83passed;19queued shutdown RED→safe restart GREEN;20malformed baseline session RED→GREEN. These are offline synthetic controls, not physical proof.

Expanded affected run found6failures/407passes: four T08 expectations still used old running/unloading rather than queued resource release; one actual telemetry stage_seq defect (submit marker before first committed stage); one old warm-reuse expectation deliberately superseded by conservative cold fallback. Submit marker moved immediately before actual prompt, raw release request/ACK/proof events added, and exact stage/cold contract expectations updated. Focused6passed; final affected run is fresh after the repair. No blanket test weakening or production default injection. Added GLOSSARY for the release-proof/approval/safe-start distinction.

Ruling: loader accepts only explicitly operator-approved controlled safe-start configs. It does not implement T11 production profile certification or infer that schema/digest implies hardware truth. Human review and an externally pinned digest are required, and current live release proof remains mandatory. Risk if deployment approval is false: evidence boundary is not trustworthy; keep profiles disabled and do not publish test values. No such configuration is delivered or enabled this round.

Full B fixed review0b8ae71: Standards0 (reviewer16focused passed), Spec1P2 (reviewer27focused passed). Pending/free ACK exceeded configured visible wait limit.22RED→GREEN adds immediate terminal failure/health latch/new503 while retaining owned in-flight settlement. No known ruling/deferred minor; final re-review required. Exact reproducible affected command is in verification-commands.md. Reliable actual proof producer remains absent/#26; #10 not closed.

Fresh repaired source: ticket86collected/86passed; explicit16affected415passed, one existing AnyIO warning. Bash syntax0. Scoped88payload path/private-key-marker inspection found0suspicious items (not a configured scanner). repair-source-hashes.json freezes tested source; no code changed during final tests. Independent fixed-commit re-review follows.

11ebbefe re-review: Spec0/reviewer3passed, Standards1P2 cancellation+free503 discarded eventual response.23RED1/old disconnect pass1 → GREEN2: settlement validates HTTP status internally, latches release failure and stops admission while preserving cancelled task. No new public state/endpoint or production activity. Fresh final affected and fixed re-review pending.

Final cancelled-release repair source: ticket88collected/88passed (final-collect/final-focused), explicit16affected417passed (cancel-repair-affected), one existing AnyIO warning. Bash syntax0. Final-source-hashes.json freezes all modified product/test/launcher files; code unchanged during runs. Preimage inspection94paths/0conflicts; actual delivery awaits independent final review.

Final independent re-review of code07a3d9db291c00ea517a06c90a2c6c9465eebc12: Standards0 / Spec0, all prior actionable findings repaired with RED→GREEN. Reviewers independently3/3focused passed; no full gates or edits. Root88ticket/417affected and final source hashes rechecked unchanged after return. Physical producer#26/real acceptance remains open, #10OPEN. Later metadata commits do not change reviewed source.

Original-product delivery verified:95reviewed payload paths,0preimage conflicts, exclusive private rollback preimages preserved; every delivered postimageSHA256 matched source7ab3b97/reviewed code07a3d9d. Actual cwd /home/clusteradmin/Desktop/Agent多模态服务, supported.venv: same explicit16affected command417passed/one existing AnyIO warning (product-final.txt). Both directories'23modified source/test/launcher hashes still match final-source-hashes.json after tests/review. No live service/model/guard/config/key/database actions, no push/PR or full gates. Delivery metadata alone follows in a final commit/sync; original stays non-Git. #10OPEN and #26/#24/#12/#15 remain the declared incomplete boundaries.
