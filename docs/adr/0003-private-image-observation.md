---
status: accepted
---

# Private image resource observations

T08 uses an opt-in private file stream shared by the existing image and gateway launchers. Resource reads run within the image container so cgroup.current/peak/max correspond to inference, while /proc/meminfo retains system scope. Host identity is a hash of the read-only host machine-id; runtime identity pins Comfy0.33.2 source and hashes image, flags, model verification manifests and observer code. Client monotonic durations never subtract backend monotonic values: UTC plus host identity aligns raw phases.

The gateway records the existing T07 committed stage snapshots and canonical prompt ID; it does not create a second task state machine. Owner tags use a process-random salt, stable for that process's lifecycle only. No raw key, prompt, material name/content or user-readable owner appears in observations. Private0700/0600 files are operator-only, with no user HTTP route. Model/GPU allocation, cgroup and host totals must not be added on unified memory.

The pinned external adapter wraps the real worker queue-get, consumed flags, unload, executor reset and post-GC soft-cache return through the existing launcher, before worker thread start. It neither edits third-party source nor enables custom/API nodes. A release epoch means worker operations returned, not that old profile graphs/CPU weights are gone; resident_profiles/release_proven remain None. Cache counts use a weak executor reference to avoid telemetry itself retaining graphs. Missing signals cannot become empty sets or safe defaults. T09 must independently require real release proof and calibrated budgets.

Observation write failure is surfaced as missing/invalid evidence, not a new task lifecycle or inferred successful measurement. The collector preserves every attempted request, validates decode/dimensions/durable save, uses fresh request identity per run and refuses performance samples with mismatched host/runtime/session, missing/duplicate execution, missing/raw-gap signals or guard violation. Reports never enable a profile. Cadence targets10Hz with a strict200ms evidence-gap limit; physical >=5Hz remains unverified.

No schema change or destructive migration. Disable opt-in observation to roll back while preserving new raw evidence and all owner/lifecycle behavior. Production deployment, actual GPU cadence/old-profile attribution and physical recovery remain unverified; issue#9 remains open for the controlled real task.
