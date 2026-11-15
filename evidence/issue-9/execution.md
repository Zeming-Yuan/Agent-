# T08 / issue #9 execution ledger

Single-ticket implement + TDD; inline serial implementation. User confirmed three public seams (benchmark import/observe HTTP+save; resource sampler clock/proc/cgroup; read-only lifecycle worker signal) and modification-before HEAD for fixed reviews. Baseline d2a9d197a8806950c3e8c0906528e624526bc960, clean controlled checkout reused on feat/issue-9-memory-evidence; old shared draft left untouched. Product 122 source paths compared: only docs/source-baseline.json absent from original product (historical metadata), all actual product/test/docs equal.

Issue #8 CLOSED; #9 claimed. No model workload/deployment authorized by inference from prior runs. Existing single-task observe will require fresh safety evidence. Guard stays enabled, no quota/scheduling changes.

Ruling: approved plan already specifies design and tests; user execution request authorizes that plan. User's affected-only checks override implement's full-suite default. Type/lint/build/CI/Compose/security/mutation gates N/A (not configured). README/plan pytest commands use supported product .venv.

Slice A import: initial RED surfaced a real earlier side effect (mkdir at import, absent historical output parent). Added write-denying import assertion; RED explicitly import attempted filesystem write. Moved mkdir into main and guarded asyncio.run; GREEN3 (ticket+two planned regression cases). No real config/network touched. Historical benchmark direct execution otherwise unchanged until observe slice.
