# Slice A two-axis review

Fixed base: ee26c31eb74d891b33b26ab428514e1c84dcb636. Initial reviewed HEAD: 941e9864ab63f2061c932f299ef21cd5e1de8e6f. Diff: git diff ee26c31...941e986. Commit: 941e986 feat(image): scope tasks and business request keys to owner (#4).

Independent reviewer roles: Standards and Spec, each reviewer (gpt-6.1-sol/high per configured role); read-only, fixed diff only, no full gates. Original issue #4 is represented by its fetched implementation plan/AC mapping and parent spec.

## Standards

P2: legacy fallback recomputes historical material fingerprint; completed legacy task whose original source was deleted raises FileNotFoundError on same-key/new-upload retry. Define a conflict and recovery guidance instead. Violates ADR's explicit404/409/429 error distinction. No additional actionable documented-standard breaches or baseline smells. Reviewer independently ran focused task/media20 tests (one existing warning).

## Spec

P2: same reproducible missing historical source at store.py:172, against '同人同键同业务输入复用任务' / '编辑重试不受临时素材 ID 变化干扰' and preserving old recoverable relationships. Frozen legacy real-worker edit completed, source deleted, reupload retry raised500. Reviewer independently ran18 task tests.

Initial summary: Standards1 (worstP2), Spec1 (worstP2).

## Fix and ruling

Public HTTP reproducer in test_tb03_legacy_missing_material_conflicts_with_recoverable_task fails first with FileNotFoundError (a-review-red.txt). Original legacy fingerprints contain only IDs; missing historical bytes cannot be reconstructed or honestly compared. Ruling: return explicit409 with the SAME owner's recoverable task_id, preserve existing result and admit no new inference; document historical limit. This is safer than treating unproven changed content as equivalent. Cost: automatic content-equivalent replay cannot be promised for already-deleted pre-T03 material. New T03 requests persist content fingerprints and are tested to replay after reference deletion/reupload. Legacy task/results remain accessible through original IDs. Subsequent re-review covers this ruling explicitly.
