# Issue7 / T06 MCP recovery evidence

User-approved fixed base45fa55afde3cbe97549f89ccb18eb71c5e677b68; controlled source checkout /home/clusteradmin/.codex/workspaces/agent-mm-issue-2-20261115, branchfeat/issue-7-mcp-resume. #6 CLOSED. User confirmed public MCP call_tool/realstdio → HTTP auth/Store/SQLite/worker → download/atomic save plus personal bundle seam. External inference and explicit network/filesystem fault boundaries only substituted; real temporary TLS for stdio acceptance. No source push,deployment,production migration,real credential issuance or GPU work.

## Acceptance mapping

| #7 criterion | Evidence | Limits |
| --- | --- | --- |
|1 persist before submit,replay identity,new intention|01 RED missing journal_path→GREEN real MCP accepted response loss/recreated bridge/original task. Public RequestJournal.pending read at POST proves committed identity. New-intent/conflict regression; a-id RED→GREEN invalid IDs never POST. 08 accepted mapping cannot be overwritten.|Same business inputs and explicit originalrequest_id for retry; local log loss recovers by server task list, not guessed content dedupe.|
|2 generation/edit/reference scoped replay;no second inference|02 correctedRED→GREEN2; actual call_tool both kinds, original upload reused,deleted material reuploaded same digest/key,original task/one backend job. Concurrent same key and conflicting input tests keep one mapping/job.|Initial02-invalid-foreground was an invalid opaque fixture,not businessRED. No real GPU performance claim.|
|3 local loss/server list,owner/service/Key isolation|03 RED editrequest_id ignored→GREEN real MCP list fields/status/pagination,ownerB empty,sameowner newKey sees same records,serviceB local empty,delete journal and recover from server; auth/revokedKey401,other task/cursor404.|Same fake HTTP app under two hostnames intentionally isolates local partition while serverowner unchanged.|
|4 local fault preservescompleted;realImageContent retry|04 RED PNG/permission/fsync/directory,network alreadyregression→GREEN5. Existing output unchanged,no temp leftovers,servercompleted,samefid,pngdecoded,one taskPOST/job. Real childstdio test uses actual blocked destination then repairs and downloads.|Physical diskfull/WindowsACL not exercised; deterministic filesystem boundary faults plus actual directory error. Deleted results404,no regenerate.|
|5 explicit personal config/platform inputs;no sharedKey/log|05 legacy builder import attempts implicit globalKey→new explicitAPI,unpack standalone and realstdioinitialize. 06 RED disguisedotherKeyasset→GREEN rejects key/runtime/traversal/overrides,exact packageentry allowlist. Newoutputexclusive,private modes;URLs rejectcredentials/query;journal bytes exclude testKey.|Only synthetic keys/temp CA in tests; resources are trusted selected code/docs,not a secret-scanning substitute.|
|6 stable sharedcontract before platforms|build_bundle(config_path,platform_assets,output_path),rootwrapper+canonicalclientmodules+common pinnedrequirements;5 MCP tools with request_id schemas;explicitplatformassetmapping;tests realstdio outside repo.|T12/T13 must provide platformassets and actual Harness acceptance; this ticket doesn't implement installers.|

## Independent stdio acceptance

Test test_tb06_mcp_resume_stdio_kill_restart_and_save_recovery starts actual ephemeral loopback HTTPS with real gateway/auth/Store/worker and only external backend replaced. Builds personalzip,unpacks outside source,starts actual MCP child,no source PYTHONPATH. After HTTP202 acceptance before response,killchild;newPID list finds pending request withtask_idnull,serverlist originalID;repeatrequest replaysoriginal. A file occupies outputdirectory,get_image_task errors;repair directory,nextcall emits realImageContent and saved samePNG;backendjobs1;testkey absentjournal. 07-stdio-and-regression initially21passed; later scoped result supersedes this count. This is Linux stdio acceptance,not actual Windows/macOS desktop.

## TDD,review and validation

A commits735df49,ca5e2ef;review-a.md Standards2 initial/Spec1 initial all fixed RED→GREEN;independent re-review0/0,8passed. B review pending at time of initial record. Captured outputs are whitespace-normalized only; diagnostic facts preserved. 05 RED observes forbidden implicit globalKey access with no such file present;no actual global credential was read.

Commands discovered in README and T06 plan,using supported existing productvirtualenv:

```bash
python -m pytest --collect-only -q -k tb06_mcp_resume
python -m pytest -q -k tb06_mcp_resume
python -m pytest -q -k "tb06 or bridge_returns_real_mcp_image_content"
python -m pytest -q tests/test_tb06_mcp_resume.py tests/test_tb06_mcp_stdio.py tests/test_image_bridge.py tests/test_tb05_server_resume.py
```

b-collect26selected/266total; b-affected-before-review61passed,oneexistingStarlette/AnyIOdeprecationwarning. Final postreviewchecks recorded below. No package.json/Makefile/pyproject/CI or configured type/lint/build gates. N/A:not configuredtypecheck,staticlint,build/CI,Compose,seed,securityscanner,mutationgate. Fullsuite/fullgates notrun per affected-only userinstruction. Production deployment/backuprestore/rollback,realGPU/20GiB/memory,actual Windows/macOS Harness 未验证 under existing#4/#5/#12–#15;parentspec remainsOPEN/unchanged. No serverdatabase migration added.

## Delivery and rollback

Before original nonGit productdelivery,verify per-file basehash then selectivelycopy reviewedcode/tests/docs/evidence and SHA256verify. Preserve private runtime/config/keys;never initialize/upload whole product. Delivery pending.

Rollback:stopnewclientwork,retain journal and serviceDB/files/registry including new writes/revocations,confirm backendcleanup as existingoperations require. Use owner-aware package/server with retained mappings;known taskIDs can query/download directly. Do not remove journal then autoresubmit,overwrite latestDB with oldbackup,restore sharedaccess or replayfailedGPUwork blindly. No irreversible migration. Resource/platform/profile integration remains tracked in existing downstreamtickets;no untracked scope expansion.
