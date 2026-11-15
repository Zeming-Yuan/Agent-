# T05 ledger — plan: docs/superpowers/plans/2026-11-14-image-05-server-resume.md

Fixed base: ea6092f33bc394315a6801166180cabb2a70694e. User confirmed offline dependency exception (#5 remains OPEN) and HTTP seams (sync generate/edit, async submit/query, owner listing, authenticated download). Real Store/workers; only external image backend/time boundary substituted. No deployment, push, production data, keys or GPU operations.

Task 1: pending — offline replay + owner listing, commit A and independent two-axis review.
Task 2: pending — disconnect, pagination, concurrency, restart, deletion, commit B and independent two-axis review.

Pre-flight: Task 2 consumes Task 1 request lookup/listing; common Store/gateway/image_routes must be integrated serially.
Ruling: reuse controlled clean source checkout on new feat/issue-6-server-resume branch. Product cwd remains non-Git; deliver only scoped, baseline-checked files after review.
Ruling: affected-only checks per explicit user instruction override generic full-suite skill instructions. No configured type/lint/build/CI gate; report N/A.
Ruling: T05 seams/design already approved in ticket plan and explicitly reconfirmed in chat; no duplicate design interview.

Task 1: red 01 (503 replay), green; red 02 (pagination ignored), green; red03 (unknown/empty filter200), green8. Existing cursor/auth/limit guards passed as regressions. No type checker configuration exists (N/A).
