# T02 / issue #3 execution ledger

Scope: single ticket, native serial implement + TDD. User confirmed HTTP seams on 2026-11-15: real auth/routes/SQLite/files/worker, external backend replaced only.
Fixed point: 2509e43 (T01 source checkout; clean before branch). Review command: git diff 2509e43...HEAD.
Plan: docs/superpowers/plans/2026-11-14-image-02-owner-file-migration.md; spec: docs/specs/2026-11-14-image-service-reliability-and-multiuser.md; issue snapshot: issue.json.
Pre-flight: Task A produces owner file access/write; Task B consumes it for references, cleanup and worker results. Same files/state; serial only.
Source check: product services/tests/docs match T01 checkout. Original plan's gateway hash differs due to verified T01; other 11 hashes still match. Product remains non-Git.
Ruling: reuse existing controlled source checkout on local feat/issue-3-owner-files, keep changes local; sync only reviewed files after preimage hash checks. No deployment or production state.
Ruling: user requires scoped verification, so no full project gates. Focused pytest commands come from T02 plan and README; type/lint/build/CI not configured (N/A). Actual backend, HTTPS and Windows/macOS Harness remain unverified; deferred to T14.
Task A: download RED foreign=200 -> GREEN 404; own delete RED 404 -> GREEN 200 with foreign/missing identical 404 and independent same-byte uploads.
Ruling: three T01 tests construct pre-migration writes. Use frozen legacy Store for their setup, preserving original assertions; new Store deliberately writes file owners immediately.
Ruling: existing quota test called route endpoint directly. Move concurrent requests to HTTP ASGITransport since Request Principal is now mandatory; preserve global 2GiB assertion.
Task A regressions initially found missing owner on generated compatibility writes; fixed within original same transaction. No new schema columns, task ownership or idempotency behavior changed.
Task A review complete at 81c77e2: independent Standards 0 / Spec 0, no outstanding findings (review-a.md).
Task B: roundtrip RED owner reference rejected404 -> GREEN real worker saves result to owner. Minimal task owner write and worker_task lookup are necessary plumbing only; task API access/idempotency/list migration remains T03, production legacy/strict guards unchanged.
Task B: foreign image references during backend offline RED503 -> GREEN404 before readiness; PDF/video foreign/missing references already404 and retained. Post-rejection valid request executes exactly one backend job.
Task B: synchronous result owner RED404 -> GREEN200; digest lookup is owner scoped with random opaque IDs. Same-owner replay reuses source/task; B same bytes uses distinct source. Synchronous foreign foreground RED503 -> GREEN404 before backend probe.
Task B: pending reference409/foreign404, queue-full cleanup preserving A bytes, cross-app simultaneous same/different owner edit, transparent foreground pixels retained as regression. Initial foreground fixture lacked transparency then was resized; corrected synthetic fixture, no production change and neither failure counted as business red.
Task B: injected exclusive-create name collision RED original file download500 (old unconditional unlink removed it) -> GREEN original bytes200. Cleanup now unlinks only paths this call created; generated save includes SQLite commit failures in cleanup boundary.
Ruling: new file_digests side table preserves old files/tasks column counts and existing legacy writes; task owner side-table insert is required to carry durable file identity across worker/restart, without implementing T03 task access or per-owner idempotency.
Task B initial affected run: 93 passed / one pre-existing Starlette/AnyIO dependency warning. No full suite/gate run per user scope constraint.
Task B final before commit: 21 T02 tests collected, focused21 passed, plan regression24 passed, affected96 passed; one existing dependency warning. Synthetic restart/new-directory recovery and controlled delete-during-readiness race also passed. Missing configured type/lint/build etc remain N/A; hardware/platform/production unverified. git diff --check passed.
Task B complete at d1ca934: independent Standards0 / Spec0; Spec independently ran focused21 passed. No review findings require fixes. Source checkout clean after each implementation commit.
Delivery: controlled source and product preimages matched all41 changed paths before closure docs, zero conflicts; only this ticket's source/test/docs/evidence paths will sync. No private paths, production data or deployment touched.

Delivery verification: original product cwd affected96 passed (product-final.txt), existing1 dependency warning. Selective sync zero conflicts; product remains non-Git. Final aggregate whitespace check caught trailing whitespace in pytest failure logs; normalized evidence only and reran diff checks, no runtime code changes. Synthetic/physical verification limits unchanged.
