# Issue #5 / T04 offline implementation evidence

User-approved fixed base: cf25676799312be86fc5e6cb5c6278c605e88cef. Controlled source checkout `/home/clusteradmin/.codex/workspaces/agent-mm-issue-2-20261115`, branch `feat/issue-5-owner-contract`. Product cwd remains non-Git. Explicit exception: #4 stays OPEN, offline #5 may proceed; production cutover stays blocked. No push, deployment, real Key issuance, production migration or model operation.

## Acceptance mapping

| #5 criterion | Offline evidence | Remaining boundary |
| --- | --- | --- |
| 1 Consistent backup, explicit takeover owner, refuse running/dangling | 01 running refusal;02 private/exclusive database+files+adjacent registry backup, literal old bytes and restored owner;04 all five reference roles × dangling/cross-owner;05 unsafe/invalid-state refusal;06 real CLI dry-run no writes/missing DB no creation;07 explicit legacy guard, SQLite authorization interruptions;08 triggers;A-review symlink refusals | All writers must be stopped externally; filesystem/registry consistency cannot be guaranteed by the main SQLite lock alone. Production maintenance/backup not run. |
| 2 Complete ownership, references/idempotency, retry with same IDs | repeat_keeps_legacy_ids_requests_and_indexes verifies rowid,ID,values,index,map;SQL create/copy/rename faults leave original DB byte-identical and retry succeeds;explicit trigger behavior preserved;14 actual legacy PNG task plus queued/cancelled/running→failed states, preserved associations and same replay ID;concurrent retries serialize;15 unknown column/version/implicit uniqueness refusal | Historical dangling references without owner deletion proof block migration for operator investigation. No automatic reconstruction or inference replay. |
| 3 Remove old fallbacks only after callers migrated | 09 omitted owner fails all seven user Store APIs;AST inventory verifies production callers explicit;11 new idemNULL/request-map-only storage;12/17 no automatic startup claim or unmapped legacy replay;strict validates v1 and absence of global uniqueness;explicit and implicit global idem indexes removed | Current production deployment has not configured AGENT_IDENTITY_MODE. Future startup requires explicit mode; it must be prepared/validated as part of a separate production cutover. |
| 4 New owners cannot read legacy, no automatic running retries | 14 real archived legacy worker, strict legacy downloads200/A404/cross-cancel404;A/Bsame-key distinct task IDs;new key same owner200/old revoked401;original backend work count1 through archive/restore;strict A/B×generate/edit worker-result matrix;16 legitimate deletion404/restart/replay without new backend job | Physical inference, actual HTTPS/MCP, Windows/macOS Harness not run this ticket. #4 and final #15 retain those gates. |
| 5 Production record and preserve new writes | OPERATIONS T04 records required private takeover mapping, backup/manifest/owner-aware rollback version/archive/idle/release fields;14 old backup restored separately and latest archive restores new A/B task/file IDs, maps and current revocations;source history remains recoverable | Production takeover people, rollout record, real backups, release and recovery are **未指定/未验证**. #5 remains OPEN; no claim of full production acceptance. |

## Verification commands and results

Use product virtualenv interpreter (checkout has no .venv). Actual repository gates found in README and T04 plan; no package.json/Makefile/CI/type/lint/build config.

- `python -m pytest --collect-only -q -k tb04_owner_contract`:69 selected/202 total (collect.txt), nonempty.
- `python -m pytest -q tests/test_tb04_owner_contract.py`:69 passed (17-unmapped-green.txt).
- A plan regression:122 passed/49 deselected after fixes (a-review-regression.txt).
- B affected13-file command (gateway/validation/images/image_gateway/media/cancel/uncertain/admission/T01/T02/T03/bridge/T04):198 passed (b-affected.txt).
- `git diff --check`:exit0 before slice commits. One existing Starlette/AnyIO deprecation warning, no failure hidden or skipped.
- Real subprocess CLI and SQLite/files/registry snapshots are exercised automatically. Only external image inference is substituted; no GPU or desktop acceptance implied.

N/A (not configured): type checker, static lint, build/CI, Compose, seed, security scanner, mutation-testing gate. Full suite/gates not run per user's explicit affected-only scope. No scanner or mutation result implied. Production backup/recovery, actual deployment, real HTTPS/CA/MCP, physical image models, memory envelope/20GiB calibration, Windows/macOS Harness: **未验证**. No performance claim.

## Review and recovery

Two independent reviewer contexts per slice, fixed nonempty diffs only. Slice A details in review-a.md (initial Standards2P2/Spec1P2, both repairs red→green and fixed range0/0). Slice B fixed54ab202...17913dd review is recorded in review-b.md:Standards0/Spec0, independently69 focused tests passed; no unhandled important findings or deferred minors.

Recover only with T04 or an equivalent owner-aware implementation supporting task_requests and file_tombstones. Stop admission/all writers, confirm backend idle, preserve the current complete DB/files/registry in a new verified private archive, inspect the pre-cutover backup in another directory, validate the latest complete archive under isolated strict auth, then make an explicit production decision. Do not deploy a shared-access pre-owner version or overwrite newer writes/revocations with an old backup. Automated incremental merge and production cutover are outside this offline delivery.


## Final delivery verification

Fresh issue selector69passed/133deselected (final-focused.txt); fresh planned regression153passed/49deselected (final-plan-regression.txt). After selective delivery, the original product cwd ran the affected command below:198passed,1 existing warning (product-final.txt). product-final-first.txt is an earlier run with absolute product test paths but source cwd, retained for transparency; it is not the evidence for original-cwd delivery verification.

```bash
python -m pytest -q tests/test_gateway.py tests/test_gateway_validation.py tests/test_images.py tests/test_image_gateway.py tests/test_media.py tests/test_image_cancel.py tests/test_image_uncertain.py tests/test_image_admission.py tests/test_tb01_legacy_expand.py tests/test_tb02_owner_files.py tests/test_tb03_owner_tasks.py tests/test_image_bridge.py tests/test_tb04_owner_contract.py
```

All delivered payload paths had their original bytes verified against the fixed base, then were replaced per-file and SHA256 compared. sync-manifest.json records before/after hashes; no conflicting product files overwritten. Only code/tests/docs/sanitized evidence copied, no private configuration/credentials/models/production data. AST inventory found0 production Store calls missing owner. Scoped credential-marker/path inspection found0 suspicious/private/linked payload paths; no configured scanner result is implied. Whole committed range git diff --check passes after documented log whitespace normalization.

Offline implementation and review are complete; full #5 production acceptance is not. #4/#5 remain OPEN, no source push or deployment/activation occurred. Existing #4 and final #15 cover actual entry/physical/Harness evidence; #5 retains production takeover/backup/release/recovery approval and evidence. Future factory startup without explicit AGENT_IDENTITY_MODE refuses; prepare that deployment configuration separately when production gates clear.
