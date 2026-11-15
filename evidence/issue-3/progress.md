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
