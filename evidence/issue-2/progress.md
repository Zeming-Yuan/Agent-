# Execution ledger — issue #2 T01

Plan: docs/superpowers/plans/2026-11-14-image-01-legacy-expand.md
Base: 443fc6022af58f9679b99bc3fb2b40cbc616138c
Execution: native/serial; independent Standards and Spec reviewers per slice.
Seams: migration APIs, KeyRegistry, real HTTP→Store→worker→external image backend; user confirmed 2026-11-15.
Source: 12/12 files match source-baseline.json; user authorized isolated sanitized Git checkout and verified change sync.
Tasks: A ownership expand and preflight; B identity, shared fixture, old/new compatibility and restart.
Ruling: keep original files/tasks columns and use a side table. New legacy writes may be unowned until explicit expand; preflight must expose this. Do not add triggers or migrate T02/T03 here.
Ruling: strict must fail closed until owner-aware T02/T03/T04 land. Staging is explicitly isolated test configuration; production factory stays legacy.
Gates: README pytest command and T01 focused commands; no configured type/lint/build gate. Hardware, production, Windows/macOS acceptance out of scope and unverified.

Task A: Standards no findings; Spec factory-preflight gap fixed with numeric-only pre-expand startup report. a-review-red.txt → a-review-green.txt, 11 passed.

Task A: complete, commits 443fc602..0d555b5; Standards 0, Spec 1 P2 factory preflight fixed, both re-reviews clean.
Task B: registry red→green, auth red→green, invalid/strict modes red→green. Existing-behavior compatibility checks green without manufactured red: old/new/old image flow, frozen baseline original cases, atomic interruption/retry, concurrent expand and registry, backup restore.
Ruling: first full run 4 failed / 74 passed. Three existing image tests hit disabled live backend (503 before expected 429/422); independently reproduced all three unchanged in original product directory. Inject shared external backend only in these tests. Fourth was missing public CA in sanitized checkout; copy only public CA cert, no private key. No production behavior weakened.
Task B verification before commit: T01 29 collected; focused 31 passed; full pytest 79 passed / 1 existing Starlette warning, suite-final.txt. Type/lint/build N/A, unconfigured.
