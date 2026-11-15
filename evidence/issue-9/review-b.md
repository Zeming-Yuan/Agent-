# Slice B independent two-axis review

Base118de0c14f2f53dfc3d641a81561ecd1bb3309cb; initial fixed HEAD3b586756259383d7086bf7d40678fc5ebc137e77. Nonempty git diff BASE...HEAD; commits2e0d0e7/3b58675. Independent fresh reviewer-role contexts gpt-6.1-sol/high, exact axis/spec/standards sources plus full smell baseline for Standards; no full gates or product edits by reviewers.

## Standards

Initial1P2: task record errors only warned, so an intermediate phase write fault did not reach later evidence and incomplete run could validate. Reproduced against actual record_task with one generating-stage OSError; loading/completed retained and validator returned[]. Contradicted ADR0003 missing/invalid-evidence rule. Repair23 adds Store-instance observation-health latch and validator error/continuous-sequence checks; new real fault RED→GREEN.

## Spec

Initial2P2: same missing intermediate evidence; node boundary metadata discarded although full spec requires text/vision encoding, sampling, VAE decode, save and cleanup. Repair24 preserves only fixed sanitized node/operation labels and cleanup event; public HTTP/raw-curve test RED→GREEN. Repair25 requires operation coverage and rejects cached sampler/no-op. Repair27 preserves owned cached-encoding evidence without pretending it executed;28 rejects malformed/unowned/unknown metadata. Runtime source completeness26 also improved.

Initial counts: Standards1P2, Spec2P2. All entered repair; final independent re-review must be appended before completion. Hardware not_run is explicitly unresolved under#24, not a code-review pass or defect waiver.
