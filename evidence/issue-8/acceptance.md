# Issue #8 / T07 acceptance evidence

User-confirmed fixed baseline60cad80cc7f33330dd794018a64c7f77a5186f8f; #7 closed before work, #8 claimed. Single-ticket implement+tdd. Original source checkout was shared; isolated final source lives at /home/clusteradmin/.codex/workspaces/agent-mm-issue-8-20261115 on feat/issue-8-truthful-lifecycle. Original non-Git product has not yet been selectively synchronized. No push, production deployment, Key issuance, real inference or guard modification.

Seams confirmed by user: existing HTTP task API / actual stdio MCP. Only external inference, request timing and file/database faults substituted. Real auth, Store/SQLite, worker, image processing, HTTPS, subprocess bridge, PNG retrieval and local save run. T07 public reducer/CAS tests are from the approved ticket plan; they complement HTTP evidence.

## Acceptance mapping

| #8 AC | Evidence | Limits |
|---|---|---|
|1 Persist orthogonal stage, timestamps, reason; no invented ETA/percent |02-stage RED→GREEN;03-order RED→GREEN;10-mcp RED→GREEN;CAS phase-start regression;test_tb07_stdio loading/saving/cancelling Chinese output |waiting_resources vocabulary exists; measured resource waiting/admission remains T09. Wait duration is approximate UTC wall-clock age; no ETA. |
|2 Owned sampling; late/duplicate/reconnect cannot regress/overwrite |04-events missing factory RED→GREEN,05-websocket HTTP-before-subscribe RED→GREEN,11-subscription acknowledgement race RED→GREEN;real local websocket with initial status/sid and canonical prompt ID, binary/malformed/unowned ignored;CAS/5 reducer counterexamples |ComfyUI0.33.2 protocol source checked; production runtime not exercised. No automatic websocket reconnect/re-execution; lost observation stays explicit. |
|3 Queued cancel immediate, running cleanup first |01-cancel RED→GREEN;A native shutdown RED→GREEN;16-stdio actual cancel/list waits for targeted stop barrier |No proof of model weight release; T08/T09. |
|4 Serial stop/cleanup, stable terminal race |A completion-race RED→GREEN plus second owner queued;09-slow-save RED→GREEN;12-profile RED→GREEN;14-terminal RED→GREEN |File/stop barriers deterministic. No GPU concurrency measurement. |
|5 Save durably/readable before completed; no implicit cancel |07-save fsync failure RED→GREEN;09-slow-save interface remains responsive, cancel awaits write and removes result;real TLS stdio completed ImageContent and saved PNG;T05 disconnect/T06 killed-tool regressions |Physical power-loss/disk-full/platform ACL not tested. Data fsync and directory fsync precede SQLite publication. |
|6 Unknown submit/stop failure degrades, new503, old queries/replay survive |06-stop failed-stage RED and cleanup halt GREEN;existing unknown_submit_outcome regression;08-event-failure RED→GREEN;15-owned execution_error RED→GREEN with sanitized error |Operator restart requires real backend cleanup; production recovery not run. Event observation loss alone retains stage, no fake steps, and HTTP history can still prove completion. |

## TDD and source audit

Slice A660a746/727e436 independently reviewed to0/0; see review-a.md. Each subsequent behavior has numbered RED/GREEN outputs. 06 initial test execution hung in teardown on unsafe old worker retry; it was terminated. The 06-stop-red.txt is explicitly an inverse pre-fix worker-handler check in an isolated snapshot, not an untouched original-source run. Test cleanup now always releases external gates. It demonstrates the pre-fix cancelling stage on failed status; no original-hang output is presented as an assertion result.

During B, shared images.py reverted after verification, writer unknown. Current draft diff was preserved; only already-tested edits reconstructed in a standalone local clone. 17-isolated-tests and final verification are authoritative; earlier successful outputs prove their then-current source only. Source hashes checked before/after final tests. Refactored existing TLS setup into tests/image_test_harness.py to share actual stdio acceptance, without creating a production test workflow.

## Verification and unverified boundaries

Commands come from README, T07 plan and their affected-file selections, using the existing supported product .venv. Run collection -k tb07_lifecycle;ticket tests, prescribed affected -k and explicit affected image/owner/recovery/bridge tests. Final counts and independent slice B review recorded below after execution. Earlier pre-review affected147passed; no full test suite/full gates per user instruction. Existing AnyIO deprecation warning retained. Optional uvicorn websocket protocol is disabled in TLS test harness, which serves HTTP routes only.

N/A (not configured): package.json/Makefile, typechecker, static lint, build/CI, Compose, seed, security scanner, mutation gate. Tests exercise temporary SQLite schema expansion/reopen/recover, owner isolation, concurrent cancellation, file failure and rollback of uncommitted publication. No irreversible migration/drop; task_runtime is additive. Production migration/release/backup-restore/rollback, real model/20GiB envelopes and Windows/macOS Harness remain **未验证**, covered by existing #4/#5/#9–#15 as applicable; no performance result is claimed.

## Recovery and delivery

Retain latest DB/files/keys and client journal; stop admission/writers, confirm targeted backend stop before maintenance. Deploy only an owner-aware version that retains final cancellation and explicit-column runtime writes. Do not downgrade to slice A's seven-value runtime INSERT after step columns exist, or to pre-T07 premature cancellation. Stage display/events may be disabled while preserving final lifecycle rules. No destructive schema rollback is needed; retain task_runtime and new data.

Slow output bytes are written to private .pending-* within files without the DB write lock, fsynced, then exclusively linked and published with owner metadata/capacity checks in one transaction. No permanent quota expansion; pending scratch is transient. A process crash may leave unregistered .pending-* or a file linked before commit: preserve evidence, stop all writers, compare DB/files before operator cleanup. Never delete while a writer may be alive or silently rerun an interrupted task. Physical crash cleanup not yet automated or production-verified.

Selective original-product delivery must compare each destination to the pre-work product-baseline hash, copy only reviewed ticket paths, verify SHA256, preserve original bytes privately, then rerun affected tests there. No whole-workspace init/upload/private runtime copy.

## Fixed pre-review verification

Explicit affected-file selection:275passed/one existing dependency warning (b-final-affected.txt), source hashes unchanged. T07 collection26 selected at this snapshot (b-collect.txt); actual stdio includesone T07 test and one retained T06 subprocess regression. 19-active-node-green runs prescribed affected selection after the final event fix. Counts are evidence for their recorded source snapshots, not a claim about later review repairs.

## Slice B initial review and repair

Fixed1c566b6 review: Standards1 P1 (failed unreturned-result unlink did not halt admission); Spec1 P2 (pending /free HTTP request not settled before cancellation). Both repaired with independent failing reproductions and affected31passed (b-review-repair-affected.txt). Reclaim failures now always become cleanup_unconfirmed, including cancellation-during-save and successful-return race. /free uses existing settled_post; response loss halts admission using the existing uncertainty policy. It still does not prove model release. Independent re-review pending next fixed commit.

## Final reviewed source and verification

Implementation HEAD85ee22d; independent final Standards0/Spec0 (review-b.md). Both archived product/ADR payloads SHA256-match the fixed commit. Fresh final-affected.txt:**277passed**, one existing AnyIO warning; final-collect.txt:**28selected/308collected** across T07 lifecycle/stdio names. Narrow repair selection31passed. Source hashes unchanged before/after the final affected run. No unresolved important findings or deferred minors; no full-suite/full-gate claim. Production/physical GPU and actual desktop-platform acceptance remain explicitly未验证.
