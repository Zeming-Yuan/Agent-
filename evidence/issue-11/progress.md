# T10 single-ticket execution ledger

Plan: docs/superpowers/plans/2026-11-14-image-10-fair-queue.md.
Fixed base: 5e64eb080341a28b35e912e52e8273e16e2fbcd2 (user confirmed).
Controlled checkout: /home/clusteradmin/.codex/workspaces/agent-mm-issue-8-20261115.
Branch: feat/issue-11-fair-queue. Original non-Git product remains unchanged until reviewed selective delivery.
User explicitly permits offline implementation despite #10 OPEN and confirmed scheduler policy, HTTP/auth/SQLite/serial worker, MCP output seams. External inference and resource evidence synthetic; no production/hardware/guard/key actions.
97 tracked source preimages match original product. Baseline planned affected selector: 90 passed, 359 deselected, one existing AnyIO warning.
01 selector: missing public module RED -> GREEN.
02 HTTP worker: A1/A2/B1 actual order RED -> A1/B1/A2 GREEN.
03 HTTP snapshots: absent queue_ahead RED -> fair positions 0/2/1 GREEN, owner-only details.
04 MCP: absent queue_text RED -> dynamic count/resource waiting text GREEN.
05 HTTP blocked head: B did not start RED -> readonly conservative capacity selection, same-owner head retained.
Ruling: claim reserves the existing serial control slot while task is still queued during T09 prepare. This preserves T07/T09 status semantics; running/loading is still set only after authoritative release/admission. Cursor and claim commit together. Claim is retained through terminal visibility until owned cleanup settles; startup recover clears abandoned slot without resetting cursor.
Ruling: queue resource preview reuses T09 admit as a conservative read-only capacity test, but is never release proof or permission to submit inference. Missing resources leave owner heads waiting without /free or /prompt retries. Expiry uses existing task runtime rather than a duplicate lifecycle.
Ruling: user affected-only scope overrides skills' full-suite defaults. Existing approved plan is reused; no new speculative design stage or integration graph is introduced.

06 T09 fixture root cause: release/session faults driven by nth sampler reads are invalid when read-only snapshots are introduced. Reproduced 2 failures; now tied to external /free event, 2 passed. No safety predicate weakened. Slice A fresh planned selector:95passed; no type/lint/build configuration (N/A). git diff --check exit0.

07 Spec P1 RED→GREEN: known resident25GiB→one owned/free→60GiB→completed. Pre-release capacity is not authoritative.
08 Standards clock P2 RED→GREEN: blocked A fails visibly on its resource deadline while B still runs; B slot is not released.
09 Spec recovered-head P2 RED→GREEN: resource_ready clears prior resource clock; A recovering before deadline waits for B and runs next.
10 Standards head diagnostic P2 RED→GREEN: follower null rank carries system_memory from blocked owner head.
11 Additional RED→GREEN: proven release but memory still insufficient yields queued slot; B runs; no repeated/free during blocking.
12 Additional RED→GREEN: actual current running prompt sample counts occupied slot rather than creating orphan diagnosis; only precisely bound slot prompt may be ignored for read-only capacity preview. Full T09 release proof unchanged.
13 Existing reopen tests exposed new column implicit INSERT; captured four failures and changed singleton insert to explicit columns; 11passed. A transient missing ResourceDeferred import was also corrected before verification (not counted as behavior RED).
Slice B regression coverage added for required already-satisfied cases (not manufactured REDs): selector matrix, immutable snapshot/head FIFO, global4/429 Retry-After/idem, concurrent same-time FIFO, cancel/restart/new-directory restore, all-blocked no control calls/wakeup, queued cancel holding/free occupies one slot, nonimage exclusion, actual stdio+TLS task display/cancel/download/save. 25passed before final verification; no GPU or real desktop.

14 additional RED→GREEN: snapshot now includes the same necessary-release control turn as claim; target still reports release_required/null until its own capacity is known.15 compatibility regression: T07 terminal comparison used an internal projection; switched to before/after public HTTP response, retaining explicit failed/error assertions (RED captured, GREEN1). First complete affected run391passed before final unknown-residency case.16 RED→GREEN2: backend known idle but old residency unknown can acquire one real release turn; only read-only preview substitutes the residency for capacity calculation, authoritative prepare/recheck still require actual correlated proof.

Slice B fresh affected verification:392passed/one existing AnyIO warning across17explicit affected files.27ticket collected. New schema reopen has explicit column insertion. No source changed during the run. User-required type/lint/build/CI etc are N/A (not configured); physical/production/platform gates remain未验证.

Fixed28ef55f review: Standards0/Spec1P2.17 RED→GREEN: accepted high budget expires after queuing/restart while generate remains valid. Local task expires with invalid_budget diagnostic/resource_wait_expired; health stays200 and second valid B runs. No invalid profile starts. Unknown backend evidence still globally fail-closed. Fresh affected verification/re-review follows; previous392/27counts are pre-this-repair.
