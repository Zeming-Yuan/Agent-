## Parent / current boundary

Part of #10 (T09), also related to #9/#24, #12 and #15.

T09 offline admission code consumes correlated ResourceSample.release_proven/release_task_id/host/runtime/session evidence. Current fixed Comfy0.33.2 T08 observer intentionally emits release_proven/resident_profiles=None and cannot attribute all old graph/CPU-weight references. A returned worker release epoch is insufficient. No positive production proof producer is delivered or enabled by the offline T09 implementation; signed safe-start config cannot replace it. #10 must remain OPEN until this gap and real acceptance are resolved.

## What to deliver

Implement and verify a trustworthy producer for actual old-profile release and its correlation to the gateway's requested task; or document and implement a bounded operator-controlled isolation mechanism that proves old references are gone. Keep the single serial control boundary. Never infer complete release from HTTP200, fixed sleep, count-zero alone, an epoch or an input task ID echoed without backend evidence. Preserve fixed-source verification and disabled API/custom nodes.

## Acceptance

- [ ] Identify actual roots/caches/model/CPU references relevant to generate, fast LoRA, standard/high and prove their release on fixed runtime; unsupported/missing observations remain unknown.
- [ ] Correlate fresh proof to backend host/runtime/session, target old profile and exact switching task; reject replay, unrelated task, process restart and stale/gapped evidence.
- [ ] Continuous >=5Hz raw memory/lifecycle evidence after a safe initial task; #24 safe window/guard requirements apply. Do not stop other workloads or lower20GiB protection.
- [ ] Through real HTTPS/MCP show /free ACK without release, old running prompt, low cgroup/system headroom, missing/expired budget and proof loss cannot start a model; valid recovery preserves original task identity or gives explicit failure.
- [ ] Validate fast→standard→generate, cancel→return and no orphan inference/LoRA residue. Profile budgets/production enablement remain #12; actual dual-Harness acceptance remains #15.
- [ ] Test-first fixes, affected-only checks, fixed-diff Standards/Spec review, docs/ADR/evidence and rollback path synchronized.

## Safety / state

No hardware run authorized by this follow-up's creation. Keep profiles disabled until real proof and applicable calibration exist. Record not_run/未验证 honestly; no benchmark/safety claim from synthetic positive fixtures. Missing production/runtime evidence is not solved by changing a flag to true.
