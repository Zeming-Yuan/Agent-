---
status: accepted
---

# Fail-closed serial image resource admission

T09 consumes the T08 ResourceSample with additive optional release_proven/release_task_id/host/runtime/session fields. Unknown stays unknown. A returned epoch alone is insufficient. Cold release requires an empty resident set, empty running set, actual proof tied to the requesting task, newer epoch than the pre-request observation, identical backend identity and a continuous <=200ms-gap stable window. T08 currently cannot produce this proof; production profiles stay disabled.

The existing serial worker owns release HTTP settlement, evidence wait, admission, loading, inference, persistence and cleanup. There is no second task state machine: resource_wait enters the existing reducer/transaction and retains queued status with blocked_reason. Explicit queued cancellation can be terminal while an outstanding control request still holds worker ownership. Running inference cancellation retains T07 stop/cleanup confirmation. Resource and inference clocks remain separate; final evidence is rechecked immediately before /prompt.

System and container scopes are independent; a conservative cold incremental budget plus margin must leave >=20GiB system reserve and fit cgroup headroom. No hot-profile reuse is inferred from last kind; physical hot-profile calibration belongs to T11. Explicit test injections contain synthetic evidence only. Default missing configuration refuses new work while same-owner request replay/history/results remain available.

No schema migration or public observation endpoint. Retain task/runtime tables and owner-aware access on rollback, disable new admission, preserve all new results/evidence, and confirm backend/control calls settled before operator recovery. Production restore and actual release/calibration are unverified. Full configuration/envelope/fault matrix is delivered in T09 slice B.

Review repair: uploads and external event connection complete before acquiring the release/admission window; no asynchronous setup is interposed between the final recheck and /prompt submission. The final sample must continue the <=200ms evidence stream. A missing initial sample is retried within the original wait deadline, before issuing one release request. Lost release proof at recheck stops the worker/new admission instead of being treated as an ordinary memory timeout.

Slice B binds each profile to a budget and explicit input envelope (output size, reference count/pixels, composition, prompt/title limits). Unsupported inputs or expired/mismatched budgets are refused before acceptance; decoded reference dimensions are also checked before backend upload. All samples across the admitted window must have sufficient independent system/container headroom. Repeated identical file observations add no evidence; they neither reset a valid window nor extend it. A current identical last sample may be reused only while fresh and within the continuity bound.

Only a dedicated private controlled-calibration configuration is loadable. An operator reviews the real baseline/guard/backend-idle evidence and pins the exact config SHA256 in the trusted deployment environment; config parameters and baseline bytes have their own integrity bindings. This is an approval pin, not a cryptographic signature or hardware proof. Baseline schema checks cannot replace that human review or current runtime release proof. An ordinary not_calibrated report, unsigned/unpinned file, stale/mismatched budget, missing positive windows or normal-production mode stays disabled. T11 owns normal production certification and evidence-bound hot/cold budgets. The alternative of trusting profile names/last_kind or schema-only approval was rejected because current T08 cannot establish old-profile release.

The deliberate cold-release fallback can worsen warm latency; no performance equivalence is claimed. Startup cleanup fails closed after one attempt. Graceful shutdown preserves queued resource waits after owned control requests settle; running tasks retain fail-on-interruption and never automatically repeat inference. Invalid/unknown release or cleanup stops admission, whereas a proven release with memory-only wait expiry fails that task with a resource diagnostic. No schema change or destructive migration is needed. Actual production configuration, guard state, release evidence, model switching and restore remain unverified.

Final review repair: wait_timeout also bounds the visible pending-release phase. On expiry, the existing task reducer records failed/release_unconfirmed and the admission health latch rejects new work immediately. The in-flight HTTP operation retains serial ownership until it settles under its separate transport bound; terminal visibility never authorizes a successor task. The latch is process health, not a second task state machine, and resets only through controlled operator recovery/restart.

Cancellation settlement must validate the eventual HTTP result as well as wait for completion. A queued task may remain cancelled, but a failed/unknown release response still latches admission unavailable and stops the worker. Cancellation cannot turn a failed release into acknowledged success, including repeated native cancellation while the owned request is settling.

## T11 calibration evidence gate (2026-11-16)

Normal profile enablement consumes `scripts.image_measurement.validate_profile_report`. The gate requires at least three complete cycles represented by at least nine independently identified runs, a matching runtime hash, a positive evidence-bound budget with at least a 20 GiB reserve, valid output and memory evidence for every run, no guard events, and a positive release proof. It also rejects duplicate task/request identities and non-stable baselines when a baseline status is present. A report that fails any check remains disabled.

The `model-switch` benchmark records generate/edit/generate attempts and writes private per-profile reports. It does not manufacture release proof or budgets; with the current T08 observer reports remain `not_calibrated` and `enabled=false`. Physical model-release evidence, signed/approved budgets, and real hardware measurements remain required before any profile can be enabled. This preserves the existing fail-closed admission boundary and 20 GiB guard.

## T14 最终构建与恢复证据（2026-11-16）

联合验收报告中的完整 profile 记录继续经过 `validate_profile_report`，并要求与最终构建的 `runtime_hash` 一致；缺少真实 profile 证据不得启用或宣称交付。后端离线、未知提交、资源不足和取消/完成竞态的恢复必须停接单、确认控制请求结算并保全新写入，不能重新推理或绕过 20 GiB 保护。`check_image_acceptance` 只做只读证据门禁，不替代实机资源释放证明。
