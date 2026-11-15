# T08 / issue #9 execution ledger

Single-ticket implement + TDD; inline serial implementation. User confirmed three public seams (benchmark import/observe HTTP+save; resource sampler clock/proc/cgroup; read-only lifecycle worker signal) and modification-before HEAD for fixed reviews. Baseline d2a9d197a8806950c3e8c0906528e624526bc960, clean controlled checkout reused on feat/issue-9-memory-evidence; old shared draft left untouched. Product 122 source paths compared: only docs/source-baseline.json absent from original product (historical metadata), all actual product/test/docs equal.

Issue #8 CLOSED; #9 claimed. No model workload/deployment authorized by inference from prior runs. Existing single-task observe will require fresh safety evidence. Guard stays enabled, no quota/scheduling changes.

Ruling: approved plan already specifies design and tests; user execution request authorizes that plan. User's affected-only checks override implement's full-suite default. Type/lint/build/CI/Compose/security/mutation gates N/A (not configured). README/plan pytest commands use supported product .venv.

Slice A import: initial RED surfaced a real earlier side effect (mkdir at import, absent historical output parent). Added write-denying import assertion; RED explicitly import attempted filesystem write. Moved mkdir into main and guarded asyncio.run; GREEN3 (ticket+two planned regression cases). No real config/network touched. Historical benchmark direct execution otherwise unchanged until observe slice.

Read-only live preflight: LTX worker active, agent-mm-image failed, image memory guard inactive; local MemAvailable 39406236KiB (~37.6GiB). Cannot prove safe image startup under existing competing workload. Do not stop LTX/start models/modify guards for sampling. Hardware observe not_run; physical verification remains open.

Slice A fixed independent review0/0: review-a.md. Slice B serial RED→GREEN:02resource scopes/missing;03clock deadlines/holes;04release worker completion;05owned/sanitized task stages (initial implementation exposed missing public owner, fixed via internal worker_task read before authoritative GREEN);06execution/sample stream;07observer I/O fault does not replace backend result;08thread launcher;09validation/timing;10actual TLS subprocess observe twice;11invalid evidence matrix;12fixed-source torch namespace;13unknown source reject;14external HTTP/save failures;15cache signals/weak ownership.

Ruling:14's RED shows missing external transport seam, not six previously broken business outcomes. After explicit transport injection six fault paths are regression GREEN; do not misrepresent them as new business fixes.10's RED shows legacy script ignored observe/config and attempted its historical private Key path; no real key/network was used.

Ruling: pinned adapter cannot prove old graph/CPU weight attribution; resident_profiles and release_proven remain None even after release_epoch advances. New epoch only means worker unload/reset/post-GC cache calls returned; T09 safety cannot default allow. Cache counts use weakref to avoid retaining executor. Ruling superseded by16: target10Hz, reject gaps above200ms to support >=5Hz even with scheduling jitter. Hardware remains not_run.

N/A (unconfigured): typechecker, lint/static, build, CI, Compose/seed, security/mutation scanners. No migration introduced. Production/GPU/Windows/macOS/deploy/physical rollback unverified. Only the approved affected checks are run. Safe rollback disables opt-in sampler and preserves data/evidence/owner/T07 lifecycle/guard. ADR0003 and operations/measurement/plan records synchronized.

16cadence RED200ms→GREEN100ms nominal/200ms maximum evidence gap.17canonical prompt mismatch RED→GREEN.18scoped refactor GREEN; observer fetch/write errors stay optional and disabled observation avoids extra reads.19download timeout RED→GREEN covers whole async attempt, not just polling.20backend environment descriptor RED→GREEN.21cancel phase RED→GREEN.22profile grouping regression GREEN (all four profile labels; no physical profile verification).

Pre-review collection43/351; prescribed selection45passed/306deselected. Earlier affected190passed corresponds to then-current snapshot and is not the final payload. Fresh b-final-affected follows after all code edits. No full suite or full gate claim.

Final pre-commit verification:43collected/focusedpassed; planned45passed; affected196passed, one existing AnyIO warning. Hardware follow-up#24 created; ready-for-human label absent in actual repository, follow-up left unlabelled (no taxonomy mutation). #9 remainsOPEN, no parent closure. Logs normalized only trailing whitespace with hashes.

Initial B independent review at3b58675: Standards1P2 (transient stage-write loss could pass), Spec2P2 (same gap; dropped encoding/VAE node boundaries). Verified feedback against code/spec;23actual transient write and seq99 RED→GREEN;24owned node/cleanup export+SVG RED→GREEN;25missing nodes/cached sampler RED→GREEN. Fixed formerly sparse raw fixture and added explicit positive valid fixture so negative tests cannot pass merely because baseline fixture is invalid.26runtime metadata RED→GREEN (workflow+launcher/kernel/available driver).27cached encoding preserved vs sampler no-op RED→GREEN;28unowned/unknown/malformed cache-event filtering RED→GREEN. No task reducer, state schema, scheduling or protection changes.

Repair collection51/359; planned53passed. Fresh affected run is repair-affected.txt; code stays frozen during it. Hardware#24/#9OPEN unchanged. Updated ADR/operations/measurement explain observation-health latch, continuous sequence and cached-work limits.

At81b1bfc Standards re-review0/original resolved; Spec original2 resolved, one newP2 edit-node5 negative text/vision encoding mislabeled conditioning.29generate/edit public export+SVG and negative executed/cached coverage RED→GREEN; focused53passed. No unrelated behavior change. Fresh final-affected follows.

Final fixed-source re-review d5861af:Standards0/Spec0, all findings resolved; independent5/7targeted tests. Root206affected/53focused, final-source-hashes unchanged. Proceed to selective preimage-checked original-product delivery; no deployment.

Original-product selective sync90paths,0preimage conflicts, allSHA256match; private rollback preserved. Actual original cwd affected206passed/one existing warning, source hashes unchanged in both directories. Delivery metadata only follows reviewed code; #9/#24OPEN, no push/PR/deploy/model/guard changes.
