# SDD ledger — plan: docs/superpowers/plans/2026-11-14-image-04-owner-contract-cutover.md
Base: cf25676799312be86fc5e6cb5c6278c605e88cef
Execution: native serial, independent parallel Standards/Spec review per slice (user requirement overrides inline skill one-review policy).
Confirmed seams: migration function/CLI, real SQLite/files copies, strict startup, public HTTP. No production data/service/model operations.
Ruling: user explicitly permits offline #5 while #4 stays OPEN; production cutover stays blocked. No dependency closure inferred.
Pre-flight: Task 1 produces contract marker/backfilled requests; Task 2 consumes marker to enable strict and remove fallback. Retain expand runtime until Task 2; exercise frozen SQL for legacy compatibility.
Ruling: preserve function contract_ownership(db_path, legacy_owner), add optional backup_dir; default exclusive backup under data root. All contract mutations require verified backup. CLI dry-run remains read-only.
Ruling: user requires affected verification only; no full test gates. Type/lint/build/CI not configured: N/A.
Tasks: 1 migration/backups; 2 strict runtime/fallback removal/recovery.

Task 1: complete (commits cf25676..54ab202; tests38focused/122planned regression; two-axis fixed review0/0).
Task 2: implementation complete (commit17913dd;69focused/198affected13files; two-axis fixed review0/0). Offline scope only, #4/#5OPEN production gates remain.
Ruling: preserve parent-spec terminal file deletion lifecycle with transactional file_tombstones; without this strict startup falsely refuses valid deletions. Cost: new owner evidence side table must accompany all backups/owner-aware recovery.
Ruling: explicit factory identity mode is mandatory; deployment remains untouched. Cost: future production startup without prepared environment fails closed rather than silently sharing legacy access.
Ruling: unknown task columns/implicit unique constraints or migration versions refuse before backup/mutation; operator must choose a matching migrator rather than lose data.
Ruling: preserve failed capture outcomes and normalize only pytest trailing whitespace for repository hygiene; original hashes retained.
Final verification/delivery pending selective sync and product affected command.

Final delivery: source issue69/plan153/affected198passed; product cwd affected198passed. Whole-range diff-check clean after audit-recorded log whitespace normalization. Independent A/B review0/0. Production remainsblocked; no push/deploy/Key/model operations. All rulings and N/A/unverified boundaries copied to evidence/issue-5.
