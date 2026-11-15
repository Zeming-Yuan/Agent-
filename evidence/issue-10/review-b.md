# T09 full offline independent review

Fixed command git diff da2acfb62b8abd478f18b4cc84b448e87003ed66...0b8ae7179692d80082e499b0a38030eaed7982c2; commits27b4c54/2901c83/0b8ae71. Review only own diff, separate reviewer contexts per axis. Source unchanged during review; previous b-source-hashes matched. Root414affected/85focused; no full gates.

## Standards

0 actionable findings. Prior P1continuity/P2reserve-order repaired. Reviewer independently16focused passed; existing AnyIO warning only. Permissions/config integrity, input envelopes, restart, startup, cached evidence and cold behavior agree with ADR0004 and declared offline limits.

## Spec

1 P2: /free HTTP wait could outlive configured resource wait_timeout because the code checked it only after the owned request returned (under its separate30s network timeout). Reviewer independently27focused passed but reproduced wait_timeout.08s / ACK.4s still queued>.2s. Spec requires explicit failure at configured wait ceiling.

## Repair

22RED: real HTTP/auth/Store/worker with held external ACK exceeded.08s and was not failed within.3s. GREEN: deadline sets failed/release_unconfirmed and a global admission-health latch immediately; new work503, no inference. The in-flight control request remains owned and is settled before worker exit, including native cancellation. No second task lifecycle table/state machine; existing reducer terminal event remains authoritative. Root fresh affected verification and fixed-commit re-review follow.

Reliable actual positive release producer and physical acceptance remain absent/unverified in#26, not counted as passed. #10OPEN; no production profile/config/benchmark claim.

## Re-review and cancellation repair

Fixed11ebbefe: Spec0, independently3passed (ACK deadline, pending cancellation settlement, queued restart). Standards1P2: cancel queued task during/free, then HTTP503 returned; cancelled settlement discarded HTTP result, health200/new202.23RED reproduced HTTP-error branch (disconnect already safe), GREEN2 validates the owned response inside the settlement coroutine, propagates release failure through a health latch and ReleaseUnconfirmed while preserving terminal cancelled. Full affected verification/re-review follow the next fixed commit. No deferred findings/rulings.

Final independent re-review of code07a3d9db291c00ea517a06c90a2c6c9465eebc12: Standards0 / Spec0, all prior actionable findings repaired with RED→GREEN. Reviewers independently3/3focused passed; no full gates or edits. Root88ticket/417affected and final source hashes rechecked unchanged after return. Physical producer#26/real acceptance remains open, #10OPEN. Later metadata commits do not change reviewed source.
