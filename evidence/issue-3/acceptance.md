# Issue #3 / T02 acceptance evidence

Scope: single ticket, serial implement + TDD at user-confirmed public HTTP seams, temporary A/B KeyRegistry + SQLite/files + real gateway/worker. Only external image inference is replaced with the existing backend transport. No production data, service restart, deployment, real Key issuance or image-node workload.

## Acceptance mapping

| Issue criterion | Evidence in tests/test_tb02_owner_files.py |
| --- | --- |
| Two explicit owners in controlled test; production legacy unchanged | owner_env supplies independent random A/B/legacy Keys; existing T01 legacy/staging/strict tests rerun. Production factory unchanged; A/B rejected in legacy, strict still fail-closed. |
| Upload/download/delete/edit/image_ids/foreground/media references; uniform foreign/missing404 | other_owner_cannot_download; same_bytes_are_independent_objects; sync_edit_deduplicates_only_within_owner; foreign_reference_rejected_before_enqueue covers edit, foreground, PDF, video; sync_foreign_foreground_checked_before_backend; own_pending_reference_is_protected returns409 to owner,404 to stranger. |
| Same-content dedup is owner scoped and IDs do not expose hashes | sync_edit_deduplicates_only_within_owner: A replay reuses own task/source, B gets a distinct source; guessed content hash ID404; deleting B retains exact A bytes. Concurrent two-app same/different owner edits confirm stable scope. Ordinary uploads remain independent opaque UUID objects. |
| Own upload→reference→retrieve; foreign rejected before enqueue without filename | owner_upload_reference_result runs real worker and decodes PNG; own_transparent_foreground_result_is_private checks known foreground pixel; foreign tests assert identical error bodies without filename/ID, then subsequent valid work is the only backend job. Offline foreign requests404 before readiness. |
| Concurrent upload/failure/in-use protection and global atomic bound preserved | failed_edit_keeps_other_owners_file checks429/Retry-After, exact A bytes and no new scratch file; concurrent_edit_uploads_have_owner_scoped_dedup; global_upload_quota_is_atomic_between_app_instances yields200/413; existing upload quota regression rerun. Exclusive-create failure preserves existing A file. Reference deleted between precheck/readiness and submit returns404 and leaves all four queue slots free. |

All names above have the `test_tb02_` prefix. Production factory, legacy fixture compatibility, existing global queue/storage/size checks, image cancellation/uncertain outcome and bridge regressions are included in the affected run. No task access/list/idempotency isolation claim: those remain #4/T03 and #5/T04. Minimal task owner persistence exists solely for file reads/result saves.

## TDD evidence

Recorded red→green: a-download (foreign200→404), a-delete (own404→200), b-roundtrip (own reference404→completed/private result), b-reference (offline503→404), b-sync (own result404→200 and owner-local random reference), b-sync-foreground (503→404), b-exclusive (collision destroyed existing file, subsequent500→200/exact bytes).

Already satisfied counterexamples are regression evidence, not manufactured red. `b-boundaries-first.txt` records an invalid opaque foreground fixture, later corrected to a genuinely transparent, unscaled known-pixel fixture; no production fix was made for this test error. Test outputs with random temporary Bearer values are redacted for publication; assertions/statuses remain intact; trailing log whitespace is normalized.

## Verification

Commands derive from README, T02 plan and existing focused file execution; use product `.venv/bin/python` as absolute interpreter in source checkout:

- `python -m pytest --collect-only -q -k tb02_owner_files`: **21/100 collected**, `collect.txt`.
- `python -m pytest -q -k tb02_owner_files`: **21 passed**, `focused-final.txt`.
- `python -m pytest -q -k "tb02 or upload_quota_is_atomic or rejected_edit_releases_only_new_unreferenced_uploads or edit_references_cannot_be_deleted"`: **24 passed**, `plan-regression-final.txt`.
- Affected files only: test_tb02_owner_files, test_tb01_legacy_expand, test_gateway, test_gateway_validation, test_images, test_image_gateway, test_media, test_image_cancel, test_image_uncertain, test_image_admission, test_image_bridge (**96 passed**, `affected-final.txt`). No full suite/gates run per user instruction.
- Configured typecheck/static lint/build/CI/security scanner/mutation/Docker Compose/seed/release gates: N/A, none configured; not substituted with invented commands. Git whitespace diff check is recorded separately.
- Offline multi-owner SQLite backup/files restore to a NEW directory and restart/replay: restart_and_restored_copy_preserve_private_files. Does not stand in for a production recovery exercise.
- Actual HTTPS/CA deployment, physical image backend, memory calibration/20GiB guard behavior, Windows/macOS actual desktop Harness, production migration/release/rollback: **未验证**, owned by existing later tickets (T08–T14), not waived by HTTP unit/integration evidence. No latency/memory performance conclusion (`baseline_status=not_run`).
- Existing Starlette/AnyIO deprecation warning remains; dependency versions unchanged.

## Review, reproduction and rollback

User-confirmed ticket base: 2509e43. Slice A: 81c77e2; independent Standards0/Spec0 (`review-a.md`). Slice B: d1ca934; independent Standards0/Spec0 (`review-b.md`), Spec independently reran21 tests. Both diffs are fixed and non-empty. Each local slice commit contains code/tests/docs/evidence and can be checked out for independent focused verification.

Product directory remains non-Git; controlled source checkout: `/home/clusteradmin/.codex/workspaces/agent-mm-issue-2-20261115`, local branch `feat/issue-3-owner-files`. Only verified changed files are synced after preimage checks; sync hashes recorded separately. No source push/deployment is implied by a local commit.

Before operational rollback stop admission, preserve database/files/registry/new writes, stop targeted inference and verify backend idle. Close controlled staging access, serve legacy-owned data only, retain new owner/digest metadata and file checks. Multi-owner data MUST NOT be handed to T01 or earlier globally-readable code. Restore rehearsed only on synthetic copies; never overwrite newer live state. No irreversible schema rebuild in T02.

## Product delivery verification

After SHA256/preimage-checked selective sync (43 payload paths at first sync, zero conflicts), the original product cwd ran the same affected11-file command: **96 passed**, one existing warning (`product-final.txt`). `sync-manifest.json` records original preimages and final payload hashes; source checkout remains local and product remains non-Git. Final added-diff scan found no private-key/API-secret patterns or unexpected untracked paths. Only evidence whitespace/redaction changed after the last product run; no runtime code changed.
