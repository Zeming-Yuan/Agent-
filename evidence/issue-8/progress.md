# T07 execution ledger

Plan: docs/superpowers/plans/2026-11-14-image-07-truthful-lifecycle.md
User-confirmed baseline: 60cad80cc7f33330dd794018a64c7f77a5186f8f. HTTP task API / real stdio MCP seams confirmed; only external inference and explicit fault boundaries replaced. #7 CLOSED; #8 claimed.

Ruling: Single-ticket implement + tdd; inline execution of shared files, independent two-axis review after each slice, affected tests only per user instruction (overrides full-suite skill defaults). Reuse controlled checkout; product non-Git directory remains untouched until selective verified delivery. No deployment, push, real credentials, GPU or guard changes.
Pre-flight: Task1 produces task_runtime/CAS/cancelling for Task2 events and terminal boundaries. Keep one lifecycle reducer and transaction writer; backend event normalization belongs at the external protocol boundary.
Ruling: source-baseline.json is the pre-T01 historical baseline; T06 committed/synchronized tip is authoritative for this ticket. Original directory hashes captured before changes; compare only delivery paths before copying. Cost if wrong: stop delivery on differing baseline.
Baseline command: python -m pytest -q -k 'cancelling_running_image or unknown_submit_outcome or image_submission_uses_uuid' -> 3 passed, one existing dependency warning.

Pending: slice A cancel cleanup; slice A review; slice B events/MCP and boundaries; slice B review/repairs; final verification and selective delivery.

Slice A: 01-cancel-red = API prematurely cancelled; 01-cancel-green = 1 passed. a-affected = 4 passed. Repeated cancel leaves cleanup un-interrupted; next owner job queued until stop release. All outputs include existing AnyIO deprecation warning. Types/lint/build CI not configured, N/A. Remaining event/render/failure boundaries explicitly slice B.

Slice A initial review at660a746: Standards P1 native shutdown interrupts cleanup; Spec P1 done-job cancellation stranded running/cancelling. Separate read-snapshot consistency issue reproduced. All three have RED->GREEN tests a-shutdown, a-snapshot, a-completion-race. Original timing test became green after shield repair; deterministic done-task observation at HTTP delivery fault boundary reproduced residual race (not counted as old test RED). Await shielded cleanup through repeated asyncio cancellation, propagate worker shutdown; reconcile accepted cancel in successful return path and delete unreturned generated result. Read tasks/runtime via one JOIN. a-repair-affected =7passed, existing dependency warning.
