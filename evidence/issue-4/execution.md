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

Slice A re-review at f56cf69: Standards0/Spec0. Historical data ruling remains explicit in review-a.md and user docs; no unhandled important findings.

## Slice B

Base: f56cf69. GET /v1/me red404→owner-only response; rotation preserves original result while revoked/unknown401. issue_to_file red missing public function→private0600/digest-only; write-failure red left partial target→revoked/cleaned; pre-existing target preserved. CLI red no target (module had no entrypoint)→real subprocess issue/rotate/revoke with private output and same-owner HTTP access. Full focused task module28 passed (b-focused.txt). No production keys issued.

Slice B verification: collected28/128; issue selector28 passed; plan-regression31 passed; affected124 passed, one existing warning. No full gates. git diff --check exit0. Key/identity slice ready for fixed-diff review.

Slice B initial review: Standards1/Spec1, same P2: revoke failure skipped own-output cleanup. Added real SQLite authorizer failure injection at DB boundary (no mocked KeyRegistry) plus file-write failure. Red: leftover file / missing recovery ID. Green: independent cleanup + safe KeyDeliveryError.key_id, then successful revoke after authorizer removed; existing file unchanged.

组合故障修复后重新采集30/130（collect-final.txt），受影响12文件126 passed（b-review-green.txt），1条既有弃用警告；先前28/124为修复前历史记录。未运行完整门禁。
