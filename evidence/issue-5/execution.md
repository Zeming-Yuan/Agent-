# Issue #5 execution

Base `cf25676799312be86fc5e6cb5c6278c605e88cef`, branch `feat/issue-5-owner-contract`.
User confirmed migration function/CLI, real SQLite/files copies, strict startup and public HTTP seams. User explicitly permits offline #5 while #4 stays OPEN; production cutover stays blocked. Native serial implementation, independent two-axis reviewer contexts per slice. No production data/model/service operation, no source push.

Repository plan and README provide Python pytest commands. No package.json, Makefile, CI, mypy/ruff/build configuration; these gates N/A. User explicitly requires affected checks only, overriding skills' full-suite defaults. The baseline planned regression selector returned 84 passed / 49 deselected (one existing Starlette/AnyIO warning).

Slice A: records 01–08 contain observed RED/GREEN outputs. First missing module is the plan's expected initial failure. Then running guard; private/exclusive SQLite+files+adjacent registry backup; ID/rowid/index/request preservation; invalid references; invalid state; real subprocess CLI read-only preview and mutation; authorizer fault injection before create/copy/rename; explicit trigger preservation. Fault injection and existing refusal cases already passed when introduced and remain regression tests; they were not broken to manufacture a red.

Rulings: legacy owner must match stable T01 `legacy`, not reassign already-owned data. Runtime and migrator share `task_fingerprint`. Backup writes use explicit directory or exclusive random path; all writers must be stopped externally. The SQLite write transaction serializes database writers but cannot stop independent filesystem/registry writers. Backups reject symlinks and targets inside files. Partial backups are retained and never reused.

Slice A excludes strict runtime cutover (slice B); expand compatibility remains until then. All fixture data synthetic. Historical migration rows may be seeded directly; actual worker evidence uses public HTTP and a controlled external inference replacement, never manufactured completed states.
