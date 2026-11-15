# T07 slice A independent two-axis review

Fixed user baseline:60cad80cc7f33330dd794018a64c7f77a5186f8f. Initial HEAD660a746; repaired HEAD727e436. Commands: git diff 60cad80...<HEAD>, git log 60cad80..<HEAD> --oneline. Both ranges nonempty. Separate reviewer role agents, configured gpt-6.1-sol/high, fresh contexts and immutable archives; no full gates.

## Standards

Initial: one P1, native asyncio shutdown could interrupt held cleanup and publish cancelled with backend still running. ADR0002 and T07 serial-control rule. Fixed with native shielded cleanup settlement and shutdown propagation. Mixed task/runtime snapshot also reproduced and repaired with one JOIN. Final at727e436:0 actionable findings, no baseline smells. Independent scoped7passed.

## Spec

Initial: one P1, accepted cancel after process_image returned stranded running/cancelling while the next job advanced. HTTP timing fault harness read-only observed Task.done to force the window; no Store/worker mocks. Fixed explicit successful-return cancellation reconciliation and deletion of unreturned output. Final at727e436:0 actionable findings; independent7passed including foreign owner and unknown outcome.

Counts: Standards0, Spec0. No unresolved important finding or deferred minor within slice A. Events, rendering, general failure boundaries reviewed separately in slice B.
