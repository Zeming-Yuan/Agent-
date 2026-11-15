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
