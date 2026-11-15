# Issue #4 / T03 implementation and verification

User-confirmed base: `ee26c31eb74d891b33b26ab428514e1c84dcb636`. Serial single-ticket implement + TDD; controlled source checkout `/home/clusteradmin/.codex/workspaces/agent-mm-issue-2-20261115`, branch `feat/issue-4-owner-tasks`. Product directory remains non-Git. No source push, production deployment, service start or real Key issuance.

## Acceptance mapping

All test names below are in tests/test_tb03_owner_tasks.py with prefix test_tb03_. These are approved HTTP/temporary Key CLI seam evidence, not physical backend or desktop acceptance.

| Issue #4 criterion | Automated evidence | Remaining acceptance |
| --- | --- | --- |
| 1. Reproducible Key issue/revoke/rotation, persisted digest+owner, no raw Key logs | issue_to_private_file_persists_only_digest_and_owner: registry reopened, private0600, raw absent from DB bytes; failed_key_delivery: collision preserves existing file, write fault revokes and removes only own partial output; combined SQLite revocation failure still cleans owned output and returns safe recovery key_id; key_cli_issue_rotate_revoke_and_http_access runs real subprocess CLI, repeated revoke, output without raw; me_and_rotated_key logs contain no raw | Production private delivery/operational release not run |
| 2. A/B generation/edit/retrieval, task/cancel/download/media isolation, uniform404 | worker_result_stays_private matrix A/B×generate/edit uses real worker and decodes PNG; running_task_foreign_cancel_cannot_interrupt; existing_media_task_access_is_scoped covers all4 media kinds; media_worker_reads_owner_source_and_keeps_result_private uses real PDF/poppler processing | Real MCP/HTTPS and physical inference unverified; Windows/macOS actual Harness tracked by T14/#15 |
| 3. owner-scoped request identity, changed input409, cross-owner independence, temporary IDs ignored | same_request_key_does_not_cross_owners; changed_payload_conflicts_and_queue_replay_does_not_take_slot; different_upload_ids_same_material_replay; material_content_and_reference_order_are_business_input; sync_and_async_share_owner_request_identity; new_request_replays_after_original_material_deleted | Historical pre-T03 deleted-source limit below; offline-ready replay belongs T05/#6 |
| 4. Rotated Key retains task access, revoked/unknown401, no forged owner | me_and_rotated_key_retain_owner_and_existing_result; real CLI rotation; client_cannot_forge_owner (body/options owner/key_id422); restart_and_restored_copy_keep_task_identity_and_revocation | Production registry recovery not run |
| 5. Task/result/reference/cleanup owners match, explicit callers, retain expand | A/B worker matrix, real PDF worker, sync/async identity, existing T02 foreground and cleanup regressions; frozen legacy old→new/new→old task replay; ADR caller inventory. task_requests beside unchanged12-column tasks; nonlegacy idemNULL; legacy original fingerprint representation retained | Contract/strict rollout belongs T04/#5; production mixed-owner rollback to older code forbidden |
| 6. Global4 queue/replay capacity unchanged; multi-identity production still gated | full queue replay202/same task, changed409, new429/Retry-After10, cancel frees exactly1 slot; concurrent_same_owner_replays_and_cross_owner_keys_are_atomic; existing global2GiB/upload/admission/legacy+strict regressions | Real20GiB/model admission safety and final production cutover are later gates |

## TDD and review evidence

- Cross-owner same-key request returned one shared ID before fix (`a-first-red.txt`). Different upload IDs originally caused409; now same-byte content replay. Legacy fallback originally raised UNIQUE tasks.idem; dual-direction frozen legacy test now passes. See execution.md.
- Slice A independent Standards/Spec each found one P2: historical legacy source already deleted. HTTP reproducer failed first (`a-review-red.txt`), then explicit409 recovery fix and new-T03 deleted-source replay tests passed (`a-review-green.txt`:116). Re-review of fixed ee26c31...f56cf69: Standards0/Spec0 (`review-a.md`).
- Slice B: /v1/me404 (`b-me-red.txt`), missing issue_to_file (`b-file-red.txt`), partial delivery file remained (`b-delivery-red.txt`), CLI did not write a file (`b-cli-red.txt`), each verified red→green. No original credentials in published logs; synthetic sentinel redacted from recorded failure text only.
- Configured checks found in README, approved T03 plan and deploy/gateway-requirements.lock. No package.json, Makefile or CI/type/lint configuration. Use product `.venv/bin/python` (absolute interpreter from controlled checkout).
- `python -m pytest --collect-only -q -k tb03_owner_tasks`:28/128 collected (`collect.txt`), not an empty selector.
- `python -m pytest -q tests/test_tb03_owner_tasks.py`:28 passed (`b-focused.txt`).
- Affected12-file command: task/T01/T02/gateway/validation/images/image_gateway/media/cancel/uncertain/admission/bridge:124 passed (`b-affected.txt`); one existing Starlette/AnyIO deprecation warning. Full suite/gates omitted per explicit user scope.
- Offline new-directory restore uses SQLite backup for state+KeyRegistry and copies files while quiescent, then tests revoked401, owner-scoped task/result200/foreign404 and persisted content-equivalent replay with no extra backend work. Not a live production recovery claim.

## Explicit limits and recovery

Pre-T03 legacy rows have only ID-based fingerprints. If original material was deleted BEFORE canonical fingerprint persistence, equivalence of a fresh upload cannot be proven. Safe outcome:409 with SAME owner's original task_id, original completed task/result still retrievable, no new inference. New T03 requests retain content fingerprints and replay after source deletion/reupload. This ruling and its cost are explicit in execution.md/review-a.md; no fabricated historical content identity.

N/A (unconfigured): type checker, static lint, build/CI, Compose, seed, security scanner and mutation gate. Security behavior is tested through authentication, private outputs, no-key logging and owner isolation; no scanner result is implied. Actual HTTPS/CA/MCP, physical image backend, memory calibration/20GiB guard, Windows/macOS desktop Harness, production migration/release/backup/rollback: **未验证**. Existing T04–T14 tickets (#5–#15) retain those responsibilities; no performance conclusion (`baseline_status=not_run`). Full ticket acceptance remains pending live-entry evidence; #4 must not be represented as fully accepted solely from these offline tests.

Rollback: stop admission and staging access; preserve all new DB/files/registry/ownership/request/digest data; stop targeted work and verify backend idle. Restore only to owner-aware equivalent-or-newer code and a NEW validated copy, never overwrite newer live writes. Mixed-owner data must not run under T02/older global task visibility. Schema expands with side tables; no irreversible destructive migration or new personal quota.

Plan commands: `python -m pytest -q -k tb03_owner_tasks` →28 passed (`focused-final.txt`); planned regression selector →31 passed (`plan-regression.txt`).

Slice B review correction: both axes found the same P2 (revocation error skipped owned-file cleanup). Real SQLite authorizer denies revocation UPDATE while issuance/reads still work; both fresh partial output and existing-target cases first fail (`b-review-red.txt`). Fix independently cleans owned output, preserves prior files, raises safe KeyDeliveryError with key_id for manual revoke after DB recovery. It does NOT claim successful revocation while DB writes are unavailable. Actual disk exhaustion was not simulated. Docs/ADR/operations describe the recovery requirement.

组合故障修复后重新采集30/130（collect-final.txt），受影响12文件126 passed（b-review-green.txt），1条既有弃用警告；先前28/124为修复前历史记录。未运行完整门禁。
