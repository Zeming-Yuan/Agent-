# T09 / issue 10 execution ledger

Single-ticket offline implementation authorized by user despite #9/#24 OPEN. Public seams confirmed: admit/released, real HTTP/auth/SQLite/serial-worker lifecycle, deployment configuration fail-closed. Fixed source base da2acfb62b8abd478f18b4cc84b448e87003ed66. Source checkout /home/clusteradmin/.codex/workspaces/agent-mm-issue-8-20261115; branch feat/issue-10-safe-admission. Original product directory non-Git. All tracked code/test/deploy/script preimages matched it at start; no initialization/upload of product directory.

Actual commands from README, T09 plan and issue: supported product .venv/bin/python -m pytest, narrowed to affected files/selectors per user's override of full-suite skill defaults. No package.json/Makefile/CI/type/lint/build gate configured. N/A: configured type checker, static lint, build, CI, Compose/seed, security/mutation scanner. Production/hardware/desktop/platform/recovery 未验证. No real backend, guard, model, service or database operations.

Baseline selector tb07 or unknown_submit_outcome or unavailable_backend_rejects: 30 passed. Existing AnyIO deprecation retained.

01 low-memory policy RED missing module -> GREEN 1. 02 invalid/missing/stale/future/container/budget/nonfinite evidence RED 18 -> GREEN20. 03 release continuity and identity RED13 -> GREEN33. 04 HTTP queued wait/recover same task RED missing injected seam -> GREEN34. First implementation exposed a read-order defect (clock captured before sampler, yielding a future sample); moved now capture after sample, preserving strict future-sample refusal. 05 default deployment health RED200 -> GREEN35.

Ruling: always request cold release until calibration supports a proven hot-residency budget. A conservative cold increment avoids reusing unproven previous-profile assumptions; cost is extra release/cold-load latency. No performance claim. T11 owns real profile calibration/enablement.

Ruling: pending release requests keep tasks queued/waiting_resources; explicit queued cancellation may become cancelled before release ACK, but worker control stays held until that request settles. This follows T09 queued-wait/cancel semantics while retaining T07's no-overlap control boundary. Two T07 expectations updated; running inference still remains cancelling until backend cleanup completes.

Slice A: policy, correlated continuous release proof, queued waits, same-task recovery and final pre-prompt recheck. Explicit synthetic resources are injected by existing integration fixtures, never production defaults. Slice B will add full envelope/config loading and fault/recovery matrix. No claim of full ticket acceptance at slice A.

Slice A fresh affected selection65passed; no full gates run. Test capture Bearer values redacted and trailing whitespace normalized before commit. ADR0004 used to avoid confusing existing ADR0002 task lifecycle.
