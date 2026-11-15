# Issue #6 / T05 server recovery evidence

User-confirmed fixed base ea6092f33bc394315a6801166180cabb2a70694e; controlled checkout `/home/clusteradmin/.codex/workspaces/agent-mm-issue-2-20261115`, branch `feat/issue-6-server-resume`. User explicitly allowed offline implementation while #5 remains OPEN and confirmed HTTP seams: synchronous generation/editing, async submit/query, owner listing and authenticated downloads. Only external backend, clock and filesystem scheduling boundary substituted. Real auth, SQLite, Store, worker and PNG decoding. No deployment, push, production migration, real Key issuance or GPU operation.

## Acceptance mapping

| #6 criterion | Automated evidence | Boundary |
| --- | --- | --- |
| 1 Disconnect/query timeout/async lost response preserve accepted work; sync timeout returns recovery ID | 04 generate/edit ASGI disconnect RED cancelled→GREEN completed and downloadable; 06 both sync504 detail.task_id survive app recreation and one inference; both async lost submit response and lost GET response find original via list and replay, one inference |03/04 invalid-harness attempts explicitly retained, not businessRED. Only route clock advanced for570s timeout. Real network/desktop not claimed. |
| 2 Same-owner replay before readiness; offline read/replay/download |01 async503RED→GREEN,05 sync generate/edit503RED→GREEN;08 edit new upload/same content matches old request, conflict409;09 revokedKey401/new same-ownerKey recovers offline; stopped uncertain worker still returns same failed task |Inputs must remain valid and owned; missing/deleted original material can be reuploaded for content matching, or recover directly by task ID. No new client journal. |
| 3 Owner-only pagination/status, recover lost response, no unowned/cross-owner leak |02 paginationRED→GREEN;03 invalidstatusRED→GREEN; explicit1..100/default20 and25same-time tasks; five statuses; other/unknown/empty cursors404; A/B/unowned list empty; unauthenticated401; response object/data/has_more/next_cursor, no owner/internal fingerprint |Order stable by(created,rowid), ID cursor validated in same read snapshot. No queue fairness or quota added. |
| 4 New offline requests503/no new task; inference once |08 async/sync generation/edit all503 and empty task list; failed sync edit cleans its created reference; concurrent readiness barrier forces two prelookups to miss then transactional second lookup gives one ID/job;01/05/06/08/09 assert actual backend job counts |Existing global4pending/2GiB and20GiB protection unchanged. No memory/performance measurement. |
| 5 Restart queue/result persistence, running fails, deleted results unavailable/no rerun |07 child processos._exit after real worker starts, strict app reconstructed same root:completed readable,queued preserved,running failed; offline replays all IDs; resumed worker executes queued only;08 async/sync deletedresult404 with same task/no second job |Migration still refuses running. Runtime read-only inspection permits owned contracted running then recover before workers. Existing backend cleanup handles orphan work before admitting queued inference; no GPU resume promise. |

## TDD and review evidence

A commits a53df86 (vertical core), bb4d8b3 (review repairs). A independent axes initially Standards2P2/Spec1P2: contracted list fields and pre-read fingerprint/deletion race. Both reproduced and fixed red→green, independently re-reviewed Standards0/Spec0. review-a.md records fixed ranges. A focused9passed; affected135passed.

B adds cancellation separation and shared image submission; a real crash revealed T04 strict runtime preflight prevented recover. Runtime-only allow_running retains all ownership checks and migration refusal; T04 former legitimate-running refusal replaced by queued/running × fivecorruption matrix (10passed). B review pending until fixed commit, see review-b.md when recorded.

## Verification entry points

Use the supported product virtualenv interpreter. No package.json/Makefile/CI/type/lint/build configuration exists. Commands discovered in README and T05 plan:

```bash
python -m pytest --collect-only -q -k tb05_server_resume
python -m pytest -q -k tb05_server_resume
python -m pytest -q -k "tb05 or image_admission or unknown_submit_outcome or restart_marks_running_failed"
python -m pytest -q tests/test_gateway.py tests/test_gateway_validation.py tests/test_images.py tests/test_image_gateway.py tests/test_media.py tests/test_image_cancel.py tests/test_image_uncertain.py tests/test_image_admission.py tests/test_tb01_legacy_expand.py tests/test_tb02_owner_files.py tests/test_tb03_owner_tasks.py tests/test_image_bridge.py tests/test_tb04_owner_contract.py tests/test_tb05_server_resume.py
```

T05 focused33passed (b-focused-final.txt). Initial14-file affected230passed (b-affected.txt) before the additional5corruption parameters; those10cases independently passed (10-strict-running-corruption.txt). Final current-range result is recorded separately; do not treat earlier230 as the final235 matrix. One existing Starlette/AnyIO deprecation warning. No hidden skip/deselect used for acceptance.

N/A (not configured): typechecking, static lint, build/CI, Compose, seed, security scanner, mutation gate. Fullsuite/full gates **not run** per user's affected-only scope. Production deployment/HTTPS/MCP/backup recovery, actual image models, memory envelope/20GiB calibration, Windows/macOS Harness **未验证**. Existing #4/#5 retain production boundaries; #12–#15 retain hardware/platform/final acceptance. No performance conclusion.

## Recovery and delivery

No schema migration is introduced. Before rollback, stop new work/writers, preserve latest database/files/registry together, confirm backend work is stopped/cleaned, then use an owner-aware version retaining task_requests and deletion tombstones. Keep disconnect-does-not-cancel behavior; old T04 strict may require explicit maintenance reconciliation before restart. Do not overwrite newer writes/revocations with an earlier backup, delete request maps, restore shared access or blindly re-run failed work.

Product delivery must verify each changed path against base before replacing, then compare SHA256. Only scoped code/tests/docs/sanitized evidence, no private data or config. baseline.json records controlled checkout inputs (product matched before implementation); final sync-manifest.json records actual selective delivery when performed. Until recorded, delivery and product-cwd verification remain pending.

Additional factory-path RED→GREEN:11-factory-crash-red reproduced the separate application() precheck refusal; factory now uses the same runtime inspection as create_app.11-factory-crash-green verifies both direct reconstruction and isolated factory restore,2passed. b-commit-affected235passed precedes this final one-line factory change; b-before-review is the fresh affected factory/plan selection. Final postreview14-file result will supersede prior counts.
