# Slice B two-axis review

Fixed base f56cf69; initial reviewed HEAD a0c170e. Diff git diff f56cf69...a0c170e; commit a0c170e feat(identity): deliver private keys and retain owner through rotation (#4). Two fresh independent reviewer roles (gpt-6.1-sol/high), read-only and scoped; no full gates.

## Standards

P2 at identity.py:74: revocation failure (SQLite lock/I/O error) skips owned target unlink, leaving a live credential output after failed delivery and hiding the initial delivery error. Breaches ADR/OPERATIONS promise of own-output cleanup. Ensure cleanup is independent of revocation and report rollback failure safely. No other actionable baseline smells. Reviewer ran5 focused tests and a combined-fault reproducer.

## Spec

P2 same combined delivery/revoke failure, against Task2 '创建/写入失败撤销新 Key' and ADR cleanup requirement. Ensure cleanup still runs and provide a recovery mechanism when revocation cannot complete. Reviewer ran28 focused tests; actual disk exhaustion and physical deployment not tested.

Initial summary: Standards1 (worstP2), Spec1 (worstP2).

## Fix and evidence

Public issue_to_file boundary test uses real SQLite authorizer to reject UPDATE (permits issuance and reads), combines write failure or existing-output collision, and verifies safe key_id-based recovery. Initially fails on leftover output and absent recovery ID (b-review-red.txt). Fix independently attempts descriptor close, revoke, owned-file cleanup; incomplete rollback raises credential-free KeyDeliveryError with key_id and CLI recovery guidance. Test restores DB writes and successfully revokes using that ID. Existing targets are never removed. Docs explicitly state revocation is unconfirmed until retry succeeds; no unsupported atomic DB/filesystem guarantee.
