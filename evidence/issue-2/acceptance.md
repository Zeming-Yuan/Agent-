# Issue #2 / T01 acceptance evidence

Scope: T01 only, serial native implementation of existing plan. User confirmed public seams and authorized isolated sanitized source checkout. Original product directory remains non-Git. No deployment, production data, raw Key, private CA key, or real inference was used. Original source hashes match 12/12 planned baseline entries. Frozen old source package verifies every service SHA256 before importing; it is not the evolving implementation relabelled as legacy.

## Acceptance mapping

| Issue criterion | Automated evidence in tests/test_tb01_legacy_expand.py |
| --- | --- |
| Stable owner, Key mapping and compatible object ownership; shared Key only legacy | registry persistence/rotation/revocation; cannot reassign a Key; default Key revocation survives app restart; legacy mode rejects A/B; staging resolves Principal without token fallback; invalid/strict modes fail closed; require_owner uses same 404 for foreign and missing |
| Old and transitional applications write and complete upload→generate→download on expanded copy | old_and_new_complete_image_flow_on_same_copy runs frozen old→new→old against same expanded runtime, verifies decodable result PNG, stable prior IDs/results, reference and foreground; original_cases_on_expanded_copy runs original upload/idempotency tests under both factories |
| Read-only preflight counts unowned files/tasks/idempotency/running, no new production access | preflight_is_read_only_and_counts_old_writes before/after expand, byte-identical database; nonexistent DB not created; factory numeric-only pre-expand report; production factory remains legacy and strict startup blocked |
| IDs, reference/foreground/result links, global boundaries and recovery preserved | old/new/old image flow, interrupted transaction rollback/retry, old positional writer concurrency, backup_restores_image_and_task_identity includes files + DB + registry; existing queue and atomic quota regressions in suite |

Old/new compatibility cases and robustness tests that already passed are regression evidence, not fabricated red. New ownership, preflight, validation, registry, authentication and mode behavior have recorded red→green cycles in a-*/b-* evidence. KeyRegistry concurrency uses real SQLite and four synchronized threads; migration interleaves an old writer transaction. External inference only is replaced by httpx.MockTransport; routes, auth, SQLite, storage and worker are real.

## Verification scope

- Supported command source: README (`.venv/bin/python -m pytest -q`) and T01 plan's focused pytest/collect commands. In isolated checkout use the existing product virtualenv's absolute interpreter path.
- Configured typechecking, linting, build, CI, Docker Compose, security scanner, mutation testing and release gates: N/A (none configured for this Python project). No substitute commands invented.
- First suite: 74 passed / 4 failed (`suite.txt`). Three stale image tests also fail unchanged in original product dir because a stopped live backend returns 503 before their intended queue/validation assertions. Only their external transport was changed to the shared backend; assertions retained. Fourth failure was missing public CA in sanitized checkout; copied only certificates/agent-root-ca.crt, no private key.
- Fresh final suite: **79 passed**, 1 existing dependency warning; T01 collection **29/79** and focused regression **31 passed**.
- Final raw outputs: `b-focused.txt`, `collect.txt`, `suite-final.txt`. Review evidence: `review-a.md`, `review-b.md` after review.
- Existing Starlette/AnyIO deprecation warning remains; dependency versions unchanged.
- Production data migration, deployed HTTPS/backend, physical model memory calibration, hardware/driver/container operation, Windows/macOS actual Harness, seed/migrations in production and release/rollback in production: **未验证**. These need later tickets/maintainer-controlled rollout; T01's backup/restore and old-app fallback evidence is offline and synthetic.
- No file/task owner access migration is claimed. T02/T03/T04 retain that responsibility; parent #1 remains open and no production multiuser switch was enabled.

## Independent reproduction and rollback

Checkout each slice commit and run the corresponding focused T01 pytest command. `tests/fixtures/t01-legacy-services.zip` plus manifest makes the frozen old application available without Git at test runtime. Restore drills copy SQLite via backup and files while gateway is stopped, then reopen a separate restored directory and verify task/results/key identity; never overwrite newer data. For single-owner application fallback keep side tables, all new data and private config. With revoked/rotated credentials revalidate the old single-token config; after multiple owners only owner-aware application fallback is safe. See OPERATIONS.md for the operational sequence.
