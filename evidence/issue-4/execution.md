# T03 execution ledger

Spec: GitHub #4, docs/superpowers/plans/2026-11-14-image-03-owner-task-migration.md and shared execution contract. User confirmed base ee26c31eb74d891b33b26ab428514e1c84dcb636 and HTTP/temporary Key CLI seams on 2026-11-15.

Native serial implementation; independent parallel Standards/Spec reviewers only. Product directory is non-Git; reuse controlled checkout and selectively sync after preimage checks. No production deployment, model workload or real credential issuance.

Ruling: user explicitly limits verification to affected checks; do not run full suite despite implement skill default. Unconfigured type/lint/build/CI gates are N/A. Cost: unrelated regressions remain outside evidence.
Ruling: execute approved T03 design and two logical slices; no new design/plan approval cycle. Highest actual desktop/HTTPS seam stays unverified, tracked by later tickets, while approved HTTP regression seam is used here.

## Slice A

Base: ee26c31eb74d891b33b26ab428514e1c84dcb636. Deliver scoped task access, owner request mapping/content fingerprints, explicit callers and worker isolation. Preserve legacy columns and strict startup guard.

Red→green: cross-owner key replay originally returned the SAME task ID (a-first-red.txt), now independent IDs and foreign404. Reuploaded identical bytes originally202/409, now202/same ID. Frozen legacy replay originally raised UNIQUE tasks.idem, now old→new and new→old reuse IDs in a legacy-only copy.

Already satisfied behavior retained as regressions: changed payload409, global4/replay slot preservation, parallel same-owner replay and cross-owner independence, A/B generation/edit real worker/private PNG, foreign running cancellation404, forged owner/key_id422, media query/cancel isolation and real PDF worker/private extracted result.

Test correction: forged owner options initially collided with fixture's owner argument (TypeError); send JSON directly. Existing media restart fixture only registered metadata; now saves real bytes via public save_generated for stream hashing. Neither fixture error counts as a business red.

Slice A verification: approved affected12-file command in a-affected.txt →114 passed, one existing Starlette/AnyIO deprecation. Type/lint/build gates N/A (none configured). git diff --check exit0. Slice A code/tests/docs ready for independent fixed-diff review; Key CLI and /v1/me are slice B.

Slice A review fix: historical deleted material now409 with original owner-scoped task_id; new content-fingerprint replay after source deletion remains202/same task. Public red→green recorded, affected116 passed in a-review-green.txt.
