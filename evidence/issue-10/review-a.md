# Slice A independent two-axis review

Fixed command: git diff da2acfb62b8abd478f18b4cc84b448e87003ed66...27b4c54fe8ac0842c9ab4b4849c941da0e9ebaa1. One implementation commit. Scope only this diff; full configuration/envelope/fault matrix explicitly deferred to slice B. Both reviewers used independent reviewer contexts (gpt-6.1-sol/high requested by role); no product edits or full gates.

## Standards

1 P1: final recheck did not constrain proof-to-new-sample continuity, allowing a slow upload/event connection to bridge an observation gap contrary to ADR0004.

## Spec

2 P2: (1) initial sampler outage froze None epoch/identity and prevented recovery of the same accepted task; (2) release evidence lost on recheck failed only the task but left health ready/new work accepted, violating release-failure503.

## Repair

06 initial sampler outage RED -> bounded baseline reacquisition before the single owned release request -> GREEN. 07 slow external connection RED -> uploads/event connection moved before the resource window; final proof gap also constrained -> GREEN. 08 final release-loss RED health200/new202 -> distinct ReleaseUnconfirmed stop/degrade -> GREEN. No exception ruling or deferred minor. Fresh affected run and fixed-commit re-review follow.
