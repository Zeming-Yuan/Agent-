---
status: accepted
---

# Fail-closed serial image resource admission

T09 consumes the T08 ResourceSample with additive optional release_proven/release_task_id/host/runtime/session fields. Unknown stays unknown. A returned epoch alone is insufficient. Cold release requires an empty resident set, empty running set, actual proof tied to the requesting task, newer epoch than the pre-request observation, identical backend identity and a continuous <=200ms-gap stable window. T08 currently cannot produce this proof; production profiles stay disabled.

The existing serial worker owns release HTTP settlement, evidence wait, admission, loading, inference, persistence and cleanup. There is no second task state machine: resource_wait enters the existing reducer/transaction and retains queued status with blocked_reason. Explicit queued cancellation can be terminal while an outstanding control request still holds worker ownership. Running inference cancellation retains T07 stop/cleanup confirmation. Resource and inference clocks remain separate; final evidence is rechecked immediately before /prompt.

System and container scopes are independent; a conservative cold incremental budget plus margin must leave >=20GiB system reserve and fit cgroup headroom. No hot-profile reuse is inferred from last kind; physical hot-profile calibration belongs to T11. Explicit test injections contain synthetic evidence only. Default missing configuration refuses new work while same-owner request replay/history/results remain available.

No schema migration or public observation endpoint. Retain task/runtime tables and owner-aware access on rollback, disable new admission, preserve all new results/evidence, and confirm backend/control calls settled before operator recovery. Production restore and actual release/calibration are unverified. Full configuration/envelope/fault matrix is delivered in T09 slice B.

Review repair: uploads and external event connection complete before acquiring the release/admission window; no asynchronous setup is interposed between the final recheck and /prompt submission. The final sample must continue the <=200ms evidence stream. A missing initial sample is retried within the original wait deadline, before issuing one release request. Lost release proof at recheck stops the worker/new admission instead of being treated as an ordinary memory timeout.
