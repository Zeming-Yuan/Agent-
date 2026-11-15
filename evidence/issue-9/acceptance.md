# Issue #9 / T08 evidence and remaining acceptance

Scope: single-ticket implementation, not parent spec completion. Source base d2a9d197a8806950c3e8c0906528e624526bc960; separate import commit118de0c independently reviewed0/0. Subsequent slice base118de0c. User confirmed all three public seams and fixed-point rule. Source checkout /home/clusteradmin/.codex/workspaces/agent-mm-issue-8-20261115, branch feat/issue-9-memory-evidence. Original product is non-Git; only reviewed payload paths may be selectively synchronized after preimage/hash checks. No whole-workspace initialization or upload.

## Acceptance mapping

| Issue9 condition | Software evidence | Physical boundary |
|---|---|---|
|1 >=5Hz MemAvailable + phase/cgroup/model signals |02scopes/missing,03clockholes,16oversample10Hz/200ms cutoff,05/21task/cancel phases;06probe;15weak cache counts; memory/curve artifacts in10TLS |Actual in-container cadence/current/peak under GPU load **未验证**. A missing signal remainsNone, not0/empty. |
|2 task, non-sensitive owner, profile, input scale; separate unified-memory scopes |05trace salted owner_tag/size/refcount;22generate/fast/standard/high profile matrix;11host/runtime/session negative cases;17canonical prompt association;13source pins |Hardware/runtime identities not physically validated in production. No sum across host/container/GPU. |
|3 reproducible command/raw curve/min/peak/load-release/base, no content leakage |10actual CLI subprocess twice via real TLS/app/auth/Store/worker, distinct UUID keys/executions; PNG decode1024/saved;09four client times;14fault denominator and sentinel leak checks;19download deadline;20runtime descriptor; SVG and baseline emitted |External inference and memory are controlled substitutes. Stable synthetic baseline is not a real calibration, speed claim or enabled profile. |
|4 minimal read-only lifecycle; accepted vs completed |04epoch0 until consumed flags/unload/reset/soft-cache return;07write fault preserves backend result;08launcher hooks fixed worker;13unknown source rejected;15weakref/caches; release_proven/resident_profilesNone |No reliable old graph/CPU-weight attribution. Epoch does not prove safe release. T09 must fail closed on missing proof. |
|5 safe initial real task before switches |Read-only preflight recorded LTXactive/imagefailed/guardinactive/~37.6GiB available; no models/guards/other jobs changed |Single real-task observe **not_run**, no switch experiment. #9 staysOPEN until safe controlled capture; parent#1 unchanged. |

## Verification contract

Commands discovered from README and approved T08 plan, with explicit affected file selection. Product .venv supplies interpreter. User affected-only requirement overrides skills' full-suite defaults. Typecheck/static lint/build/CI, Compose/seed/security/mutation gates **N/A** (not configured). No database migration, new runtime dependency or destructive operation. Production migration/deployment/recovery/physical rollback **未验证**, actual Windows/macOS Harness **未验证** (existing platform/joint tickets).

Tests use real gateway/auth/SQLite/task reducer/serial worker/Pillow/HTTP/TLS/subprocess/save, substituting only external inference, resource/clock and fault boundaries. Permission matrix and idempotency/cancel/recovery regressions run only in affected files. No output from an uncollected/skipped test is counted. Existing AnyIO warning is retained.

## Interpretation limits

The basic validate_run schema retains the approved contract's timing-only minimum for compatibility; actual observe always emits evidence_version1 and enforces raw host/runtime/session/terminal/unique-canonical-execution/sampling checks. The simple good_run unit fixture proves arithmetic, not actual measurement. Software-observed loading stage interval is not precise weight I/O duration. memory.peak is container lifetime peak; it may predate the task. Release-operation duration does not prove every graph/weight released. Baseline windows/tolerance are explicit measurement inputs, not safety budgets. Profile reports always not_calibrated/enabled=false.

Timing-only schema compatibility and any invalid/incomplete physical evidence cannot enable a profile or establish safety. A single task cannot certify model switching, multi-cycle calibration, all profiles or desktop parity.

## Reversibility and hygiene

Disable IMAGE_TELEMETRY_DIR and perform normal controlled service maintenance to stop observation. Preserve raw evidence/new files/tasks/keys/journals, T07 terminal protections, owner isolation and20GiB guard. No DROP, reset or new seed. Source changes are local commits, no push/production deployment. Private observations/config/images never enter committed payload. Selective delivery records SHA256 pre/post and preserves preimages privately. Code review and final verification appended after the immutable fixed commits are available.

## Slice B pre-commit verification

Collected43/351; focused selector43passed; prescribed selector45passed; explicit affected12-file selection196passed (b-final-affected.txt), one existing AnyIO warning. b-source-hashes.json freezes code/tests/launchers at this verification. No code edits occurred during the final affected run. Earlier190-test run is historical pre-review evidence only.

Remaining physical acceptance is tracked by https://github.com/Zeming-Yuan/Agent-/issues/24. Requested ready-for-human label was absent (verified label inventory), so follow-up created without inventing a replacement label; #9 remainsOPEN. No model run occurred. Trailing whitespace in pytest captures normalized with original/normalized hashes; no outcome or diagnostic rewritten.

## Repair verification

Initial review Standards1P2/Spec2P2; all reproduced and repaired (review-b.md). Fresh collection51/359; focused module51passed; planned53passed; explicit affected204passed/one existing warning (repair-affected.txt). repair-source-hashes.json freezes the verified source. No full gates, production or hardware actions. Independent re-review pending fixed repair commit.

## Second repair verification

Spec node5 correction:29RED→GREEN, focused module53passed. Final affected12-file run206passed, one existing warning; final-source-hashes.json freezes source/launchers/tests and final-collect.txt records nonempty ticket collection. Code unchanged during final run. Standards/Spec re-review follows fixed commit. Original-product selective delivery still pending.
