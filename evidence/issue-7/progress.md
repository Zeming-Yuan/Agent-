# T06 execution ledger — plan: docs/superpowers/plans/2026-11-14-image-06-mcp-resume.md

User confirmed base 45fa55afde3cbe97549f89ccb18eb71c5e677b68 and MCP/stdio → HTTP auth/Store/worker → download/save + bundle seams. #6 CLOSED. Inline execution; shared bridge and packaging serialized. Two independent review agents per slice.

Ruling: Reuse existing controlled source checkout on new feat/issue-7-mcp-resume branch; original non-Git product unchanged until verified selective delivery. No reinitialization/upload/private runtime.
Ruling: User affected-only checks override skill fullsuite instruction. No configured type/lint/build/CI gates; mark N/A. Real platform/hardware acceptance remains #13/#14/#15.
Pre-flight: Task1 journal.prepare and ImageBridge request_id feed Task2 MCP/list/save/bundle. Keep signatures from shared contract; carry client/request_journal.py in package as specified. No shared service edits planned.
Task1: in progress. Baseline hashes match product.

Task1: RED 01-red TypeError missing journal_path; GREEN01-green 1passed; a-regression3passed. New-intent and conflict cases retained as already-green regressions. Scope split: A freezes no-reference generation/journal; B adds edit/reference/list/save/bundle. domain-modeling used to synchronize ADR0001 without new state machine.
