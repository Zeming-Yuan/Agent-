# T06 execution ledger — plan: docs/superpowers/plans/2026-11-14-image-06-mcp-resume.md

User confirmed base 45fa55afde3cbe97549f89ccb18eb71c5e677b68 and MCP/stdio → HTTP auth/Store/worker → download/save + bundle seams. #6 CLOSED. Inline execution; shared bridge and packaging serialized. Two independent review agents per slice.

Ruling: Reuse existing controlled source checkout on new feat/issue-7-mcp-resume branch; original non-Git product unchanged until verified selective delivery. No reinitialization/upload/private runtime.
Ruling: User affected-only checks override skill fullsuite instruction. No configured type/lint/build/CI gates; mark N/A. Real platform/hardware acceptance remains #13/#14/#15.
Pre-flight: Task1 journal.prepare and ImageBridge request_id feed Task2 MCP/list/save/bundle. Keep signatures from shared contract; carry client/request_journal.py in package as specified. No shared service edits planned.
Task1: in progress. Baseline hashes match product.

Task1: RED 01-red TypeError missing journal_path; GREEN01-green 1passed; a-regression3passed. New-intent and conflict cases retained as already-green regressions. Scope split: A freezes no-reference generation/journal; B adds edit/reference/list/save/bundle. domain-modeling used to synchronize ADR0001 without new state machine.

A independent initial review: Standards P1 direct CLI import + P2 empty request_id; Spec P2 empty request_id. Both reproduced RED then fixed, a-review-green8passed (one existing dependency warning). Re-review required at new fixed HEAD.

Task1: complete at ca5e2ef. Fixed range45fa55a...ca5e2ef re-reviewed independently Standards0/Spec0, both scoped8passed; Standards used immutable archived commit. No deferred minor.
Task2: refs RED edit missing request_id + foreground random-ID fingerprint mismatch -> GREEN2; initial02-invalid-foreground fixture was opaque and invalid, retained as invalid-harness evidence, not RED. Reference tests strengthened to actual build_server.call_tool both generation/editing.
Task2: MCP recovery RED edit request_id ignored -> GREEN owner/service/rotation/lost journal; atomic save RED4 (PNG/permission/disk/directory), network existing pass -> GREEN5. Bundle RED legacy builder tried implicit global key at import -> new explicit function + unpacked real stdio GREEN. Credential disguised as README asset RED -> same-extension guard GREEN. URL credential/query RED3 -> GREEN3; conflicting accepted mapping RED -> CAS guard GREEN1.
Task2: independent real stdio/TLS acceptance kills actual MCP child after HTTP accept before response, restarts, resumes same request, repairs real blocked output path and returns PNG with one inference. All artifacts ephemeral/synthetic, not production keys or samples.
Task2: b-collect26selected; b-affected-before-review61passed/1existing dependency warning. Type/lint/build/CI N/A; only affected tests per user. Review B pending.
