# T05 ledger — plan: docs/superpowers/plans/2026-11-14-image-05-server-resume.md

Fixed base: ea6092f33bc394315a6801166180cabb2a70694e. User confirmed offline dependency exception (#5 remains OPEN) and HTTP seams (sync generate/edit, async submit/query, owner listing, authenticated download). Real Store/workers; only external image backend/time boundary substituted. No deployment, push, production data, keys or GPU operations.

Task 1: pending — offline replay + owner listing, commit A and independent two-axis review.
Task 2: pending — disconnect, pagination, concurrency, restart, deletion, commit B and independent two-axis review.

Pre-flight: Task 2 consumes Task 1 request lookup/listing; common Store/gateway/image_routes must be integrated serially.
Ruling: reuse controlled clean source checkout on new feat/issue-6-server-resume branch. Product cwd remains non-Git; deliver only scoped, baseline-checked files after review.
Ruling: affected-only checks per explicit user instruction override generic full-suite skill instructions. No configured type/lint/build/CI gate; report N/A.
Ruling: T05 seams/design already approved in ticket plan and explicitly reconfirmed in chat; no duplicate design interview.

Task 1: red 01 (503 replay), green; red 02 (pagination ignored), green; red03 (unknown/empty filter200), green8. Existing cursor/auth/limit guards passed as regressions. No type checker configuration exists (N/A).

A review initial: Standards2P2 (list schema, fingerprint/delete race); Spec1P2 (list schema). Both independently verified. Contract red→green8. Race red FileNotFoundError through HTTP, green9 with only filesystem scheduling boundary substituted. Shared fingerprint extraction keeps online submit revalidation and deletion exclusion; no schema change.

Task 1: complete (commits ea6092f..bb4d8b3, focused9passed; affected135passed; independent re-review Standards0/Spec0). Task2 begins from bb4d8b3.

Task2: disconnect RED observed cancelled for generate/edit, GREEN; sync offline RED503 both, GREEN; strict crash RED startup rejects persisted running, GREEN after runtime-only allow_running. Timeout/lost-response/deletion/owner/concurrency regressions already pass; no destructive change made to manufacture red.
Ruling: plan's disconnect helper needed lower-case ASGI headers and bounded cleanup when Starlette middleware waits after endpoint cancellation. Invalid-harness attempts retained separately, not counted as business RED;04-disconnect-red records actual cancelled assertions.
Ruling: #6 restart AC conflicts with T04 runtime non-running precondition. Allow only runtime inspection of validated contracted running, then fail before worker creation; migration default remains rejecting running. T04 outdated standalone running-refusal case replaced by full queued/running corruption matrix (10cases), T05 real crash verifies new positive behavior.

Task2 factory trace found a second default inspect_contract in application(). Extended real-crash test to isolated restored factory directory; RED startup refusal→GREEN2, no production path/network accessed. Both runtime entry points now permit recovery after validation.

Task2 pre-review: current plan/factory affected38passed/202deselected, one existing dependency warning (b-before-review.txt); prior broad235passed + factory crash2passed; fresh broader run deferred to final after review. N/A type/static/build configured gates. Scoped49path scan found0 credential/private/link markers.

Final diff hygiene: whole committed-range diff check exposed pytest trace trailing spaces in captured logs (initial untracked logs not included in working-tree diff check). Normalize evidence line endings/line trailing spaces only, retain assertion/failure contents. Final range check must be repeated after evidence commit.

Fresh final code verification:34/240collected;14affected files236passed,one existing warning. B Standards independent fixed snapshot24passed/83deselected and0findings; B Spec still pending.

Task 2: complete (commit2f6493b from bb4d8b3;14affected236passed; independent BStandards0/Spec0, no deferred minors). Both source/runtime entry points verified; no requested offline acceptance gap remains. Realbackend/production/desktop remain explicitly unverified under existing tickets4/5/12/13/14/15.

Delivery: baseline-check53paths0conflicts;all53SHA256matched. Original product cwd fresh14-file236passed (product-final.txt). Both axes0remaining for both slices. Final audit code and evidence only, no private payload or deployment. Last commit records delivery metadata; code remains independently verified at2f6493b.
