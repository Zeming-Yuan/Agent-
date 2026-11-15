---
status: accepted
---

# Persistent owner image turns with one owned execution slot

T10 uses the shared choose_next rule for atomic claims and read snapshots. Owners sort stably and resume immediately after the persisted last_owner; each owner's oldest durable enqueue_seq is the only candidate. Newly accepted tasks never reset the cursor. Existing rows are backfilled once in created/rowid order; subsequent inserts allocate sequence in the acceptance transaction. No personal quota or model affinity preference is added.

A claim is the serial execution control slot, separate from lifecycle status: T09 prepare keeps queued until actual loading starts. Cursor and claim commit atomically. Cancellation/terminal display does not free the slot before owned control/cleanup settles. Startup recover clears abandoned claims while preserving the cursor and existing queued/running recovery rules. The existing reducer remains the sole task lifecycle.

Readonly conservative T09 capacity checks gate owner heads and simulate queue_ahead without side effects. Preview is not actual release proof: the worker still runs the full T09 sequence before /prompt. Unknown/insufficient resources cannot be advertised as a certain rank. The snapshot counts the single occupied slot even during cancellation/cleanup and excludes nonimage work, exposing only counts and the caller's tasks.

Additive scheduling tables must travel with task/storage/identity backups. Rollback preserves new data and isolation; pause multiowner scheduling rather than silently restore global FIFO. Actual model release proof, physical performance, production restore and Windows/macOS Harness remain unverified. No performance gain is claimed; baseline_status=not_run.

Review rejected gating necessary release on memory still occupied by a known resident: such a task may take one owned release turn. When continuous correlated proof establishes idle but capacity remains insufficient, it yields queued without loading; subsequent scheduling uses read-only empty-resident checks instead of repeatedly releasing. This may use an extra conservative cold release per actual control turn; no warm latency improvement is asserted.

Unclaimed resource waits are refreshed while another task owns execution. The existing reducer's resource_ready event returns a recovered queued task to the ordinary queue and clears the resource wait clock; other owners' inference time cannot expire it. Insufficient heads still reach a visible bounded failure. The single slot records its generated prompt ID solely to recognize that exact currently running prompt in read-only snapshots; any other/unknown prompt remains unconfirmed. This identity is cleared with the claim, never sent in user task details and never substitutes for T09 release evidence.

The same release turn is available when the backend is observed idle but resident identity is unknown: the control request may establish knowledge. Read-only preview may normalize that unknown residency solely to check valid capacity inputs and identify release_required; it never normalizes unknown running work or changes the samples consumed by authoritative prepare/recheck. Thus an ACK or unknown profile still cannot authorize /prompt. Pending controlled release turns count in the same simulated order as claims; their own rank remains null until capacity is knowable.
