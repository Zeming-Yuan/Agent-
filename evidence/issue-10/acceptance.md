# Issue10 / T09 offline delivery and remaining acceptance

Source checkout /home/clusteradmin/.codex/workspaces/agent-mm-issue-8-20261115, branch feat/issue-10-safe-admission. Initial fixed base da2acfb62b8abd478f18b4cc84b448e87003ed66. User confirmed3public seams and allowed offline implementation with #9/#24OPEN. Original product is non-Git; selective delivery only after source review/preimage/hash/rollback checks. No push/PR, real model load, production service change or guard adjustment.

## Requirement evidence

| #10 criterion | Offline evidence | Remaining boundary |
|---|---|---|
|1 serial ownership; HTTP/sleep/rise insufficient |03release policy;07slow external setup;08lost proof;16cached reads;17brief headroom spike; fault ack_only/no proof/old_running/unknown residents; T07 pending-free cleanup/cancel regressions |Actual old-profile positive proof producer is absent in current T08; tracked#26. Synthetic proof cannot enable production. |
|2 incremental budgets+margin+20GiB+cgroup |01/02policy negatives and exact literal boundary;04/10same-task low-memory recovery;09budget/runtime/expiry/envelopes;11decoded reference pixels; container/stale/session faults;12/13private configuration/sample parsing |Actual measured budgets/runtime and safe baseline未验证, #24/#12. |
|3 queued reason/cancel/recheck/deadline/separate clocks |04/06/10same tid recovery; queued cancel404/idem409/replay;07/08final recheck; resource wait expiry fault;19graceful queued restart; process inference clock remains900s after actual submit |Real MCP/HTTPS resource-fault acceptance未验证, #26/#15. |
|4 profile/fast-standard isolation and cancel return |Real gateway/worker with external backend: fast cancel→standard→generate→high, literalsteps4/20/8/40 and only fastLoRA; backend running empty; T07 targeted-stop/cancel races |Graph/protocol evidence only. Physical LoRA/old/new profile absence and real switching未验证, #26/#12. |
|5 uncertain release/submission degrades503, history recovers, no infinite loading retries |08release loss;15one-attempt startup cleanup; free_error/proof/session faults health503/new503/replay same tid;05saved result recovers under default disabled config; existing unknown_submit/T05/T07 tests |Production operator recovery/restore未验证, #15. |
|6 uncalibrated default disabled, controlled calibration only safe starting evidence |09invalid envelope/budget;12operator pin/expiry/private mode/raw digest/parameter binding;13missing/stale identity/partial/private sample;14default factory wired without positive proof; CLI0/1 |No delivered production config. Approval pin is not signature or hardware proof; true approval/raw provenance and release signal still required. Normal production profile certification remains#12. |

## Verification

Discovered commands: README supported .venv pytest and T09 plan/issue selectors; user's affected-only scope overrides full-suite defaults. Full applicable configured gates were **not** run. Type checker/static lint/build/CI/Compose/seed/security scanner/mutation gates: **N/A, not configured**. No DB schema migration, destructive seed or new runtime dependency; DB expand/contract gateN/A. Production deployment/restore/physical rollback, real GPU memory/release/switching, Windows/macOS actual Harness: **未验证**. No before/after performance experiment; baseline_status=not_run, comparative conclusion inconclusive.

Fresh final before fixed slice B commit:
- planned selector tb09 or tb07 or unknown_submit_outcome or unavailable_backend_rejects:114passed before final additional baseline case/telemetry repair; historical, not final source evidence.
- final ticket collection85/446; ticket85passed (b-final-collect.txt, b-final-focused.txt).
- explicit16affected files414passed (b-final-affected.txt), one existing Starlette/AnyIO deprecation warning.
- bash -n deploy/run-image.sh deploy/run-gateway-runtime.sh: exit0; these scripts were not executed.
- All implementation regressions captured RED→GREEN; red logs have temporary test Bearer values redacted and trailing whitespace normalized.21records a real T08 telemetry regression repair (6targeted pass), not a hardware capture.

## Decisions and reversibility

Conservative cold release is intentional until physical hot-residency/increment evidence exists (#12); warm latency may worsen and is not benchmarked. Control-request ownership outlives queued cancellation; graceful queued shutdown preserves intent only after owned calls settle. No personal quota, concurrency increase, guard decrease, state-machine duplication, public observer endpoint or owner fallback introduced. GLOSSARY/ADR0004/OPERATIONS/plan record the same boundaries.

Disable admission and preserve tasks/files/KeyRegistry/raw evidence; confirm backend inference/control requests settled before operator-controlled maintenance. Retain owner-aware T07/T09 behavior on rollback; never return to static20GiB-only admission or overwrite new data from an old snapshot. Original-product sync must preserve exact preimages privately and hash every delivered path. No real secret, runtime SQLite, model, production image or private config is in the payload.

## Open work

#26 explicitly tracks a reliable correlated actual old-profile release producer plus physical admission fault/recovery demonstration. Current T08 still emits unknown and will never be treated as positive proof. #24 is the safe single-task real measurement; #12 owns measured profile certification/hot budgets; #15 owns actual two-platform Harness and recovery. #10 remainsOPEN; parent#1 unchanged. This document does not claim complete #10 acceptance or production readiness.

Independent two-axis final review and original selective sync are appended after fixed source commits exist.

## Final review repair

Fixed B review: Standards0, Spec1P2 (review-b.md); reviewer targeted16/27passed.22RED→GREEN reproduces configured pending-ACK ceiling and adds visible failure/degrade/new503 without abandoning owned release settlement. The previous414/85counts are pre-repair source evidence only; repair-final-affected.txt and final re-review supersede them below.

Fresh repaired source: ticket86collected/86passed; explicit16affected415passed, one existing AnyIO warning. Bash syntax0. Scoped88payload path/private-key-marker inspection found0suspicious items (not a configured scanner). repair-source-hashes.json freezes tested source; no code changed during final tests. Independent fixed-commit re-review follows.

## Cancellation combination repair

11ebbefe re-review found one StandardsP2, Spec0: cancelled queued request's owned/free503 was ignored after settlement.23RED→GREEN2 now preserves cancelled while returning health503/new503 on HTTP error or unknown outcome. This strengthens AC1/AC5; cancellation never hides failed release. Fresh final source evidence below supersedes prior415/86counts after fixed commit.

Final cancelled-release repair source: ticket88collected/88passed (final-collect/final-focused), explicit16affected417passed (cancel-repair-affected), one existing AnyIO warning. Bash syntax0. Final-source-hashes.json freezes all modified product/test/launcher files; code unchanged during runs. Preimage inspection94paths/0conflicts; actual delivery awaits independent final review.

Final independent re-review of code07a3d9db291c00ea517a06c90a2c6c9465eebc12: Standards0 / Spec0, all prior actionable findings repaired with RED→GREEN. Reviewers independently3/3focused passed; no full gates or edits. Root88ticket/417affected and final source hashes rechecked unchanged after return. Physical producer#26/real acceptance remains open, #10OPEN. Later metadata commits do not change reviewed source.

Original-product delivery verified:95reviewed payload paths,0preimage conflicts, exclusive private rollback preimages preserved; every delivered postimageSHA256 matched source7ab3b97/reviewed code07a3d9d. Actual cwd /home/clusteradmin/Desktop/Agent多模态服务, supported.venv: same explicit16affected command417passed/one existing AnyIO warning (product-final.txt). Both directories'23modified source/test/launcher hashes still match final-source-hashes.json after tests/review. No live service/model/guard/config/key/database actions, no push/PR or full gates. Delivery metadata alone follows in a final commit/sync; original stays non-Git. #10OPEN and #26/#24/#12/#15 remain the declared incomplete boundaries.
