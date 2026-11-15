# Fixed slice A review: 5e64eb0...471acb1

## Standards

2 P2 findings: (1) resource wait upper bound not monitored while another owner's job holds inference; (2) follower gets null rank but no known blocking owner-head reason. Relevant sources ADR0004/resource-clock boundary and docs/IMAGE-SERVICE T10 diagnosis contract. Reviewer independently ran ticket5passed plus real HTTP synthetic reproductions. No whole gates.

## Spec

P1: raw pre-release capacity gate prevents required old-resident release (25GiB before/free,60GiB after; current worker0/free0/prompt, fixed-base1/free1/prompt completed). P2: currently recovered head expires before next turn because old waiting record is not refreshed. Each violates parent ordered release/admission and #11 recovered-head next-turn promise.

Summary: Standards2 (worstP2); Spec2 (worstP1). All accepted for RED/GREEN repair and independent re-review. No unaddressed judgement-call smells reported.
