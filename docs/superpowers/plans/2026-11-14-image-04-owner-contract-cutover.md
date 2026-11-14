# T04 Contract：旧数据有明确归属后切换到完整多人隔离 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 维护者明确指定 legacy 接管身份后，旧图与旧任务仍可取回，新用户只能访问自己的内容，服务不再存在无 owner 的共享回退。

**Architecture:** Consumes: T03 全部 owner 感知调用方。Produces: contract_ownership(db_path:Path, legacy_owner:str)->dict（scripts.migrate_image_owners）；CLI --db、--legacy-owner、--backup-dir、--dry-run；启动 strict 模式先做只读预检，有 running 或悬空关联则拒绝切换。 先读共享执行契约并保留既有兼容边界；本票只交付确认的纵向行为，不扩展为通用重构。

**Tech Stack:** Python、FastAPI、SQLite、httpx、Pillow、stdio MCP；固定 ComfyUI 0.33.2；平台专属脚本按本票列出的操作系统执行。

**Spec:** [父规格 #1](https://github.com/Zeming-Yuan/Agent-/issues/1)；[完整规格](../../specs/2026-11-14-image-service-reliability-and-multiuser.md)；[共享执行契约](2026-11-14-image-execution-contract.md)。执行者必须同时读取三者。

**Ticket:** T04；Blocked by：T03。只有文件与任务所有调用方完成迁移，才能删除无归属回退并切换生产身份。

**Plan status:** 已确认 ticket 的实施计划；本轮尚未实现产品或运行新测试/硬件测量。

## Global Constraints

- Windows 和 macOS 分别从实际桌面 Harness → MCP → HTTPS → 图片后端 → 鉴权取图 → 显示与本地保存验收。
- 不新增个人任务数、存储量、每日次数、积分、计费或限流配额。
- 20GiB 余量保护继续作为最后防线；不通过降低或关闭保护器取得通过。
- 图片执行串行，控制权覆盖停止、卸载、加载、推理和清理；共享服务与迁移串行整合。
- 当前全局最多 4 个未完成媒体任务，上传与生成文件合计 2GiB；不放宽现有尺寸、参考图、单文件和结果大小限制。
- 保留生成 8 步、fast 编辑 4 步、standard 20 步、high 40 步及 fast LoRA 隔离；未实测模式如实列未验收。
- Python 客户端要求 3.11+；原始 Key、私有配置与业务样图不进入公开文档/日志。
- 产品目录当前非 Git；独立提交按共享契约在受控源码 checkout 完成，不能把文档仓库提交伪装为产品实现。

## Review Focus

1. 运行任务未停止：contract 必须拒绝 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
2. 中途失败重跑：不重复归属或改 ID → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
3. 旧结果/参考关联：悬空必须拒绝而非丢弃 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
4. 多身份新增写入：备份恢复不可覆盖丢失 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
5. 旧全局 idem UNIQUE：删除兼容后不同人同键仍成功 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。

---

## File structure and interfaces

- Create: scripts/migrate_image_owners.py — 预检、备份、迁移及 strict 门禁
- Modify: services/ownership.py / services/store.py — 明确归属、去旧索引
- Modify: services/gateway.py — strict 启动检查，移除用户路径默认 owner
- Create: tests/test_tb04_owner_contract.py
- Modify: OPERATIONS.md / docs/adr/0001-owner-scoped-storage.md

**Consumes / Produces:** Consumes: T03 全部 owner 感知调用方。Produces: contract_ownership(db_path:Path, legacy_owner:str)->dict（scripts.migrate_image_owners）；CLI --db、--legacy-owner、--backup-dir、--dry-run；启动 strict 模式先做只读预检，有 running 或悬空关联则拒绝切换。

## Task 1: 首条用户反例与最小纵向实现

**Files:** 使用上面列出的本票实现文件；首条测试写入 `tests/test_tb04_owner_contract.py`。本任务最小实现核心位于 `scripts/migrate_image_owners.py`。

**Interfaces:** 消费上述输入，产出本票外部行为；新公共签名以 Architecture/共享契约为准，不另起别名。

- [ ] **Step 1: 写第一条失败测试**

```python
import pytest
from services.store import Store
from scripts.migrate_image_owners import contract_ownership

def test_tb04_running_task_blocks_contract(tmp_path):
    store = Store(tmp_path)
    item = store.submit("image_generate", None, {"prompt":"x"}, None, owner="legacy")
    store.update(item["id"], status="running")
    with pytest.raises(ValueError, match="running"):
        contract_ownership(store.db, "legacy")
```

- [ ] **Step 2: 运行并确认预期失败原因**

Run: `python -m pytest -q tests/test_tb04_owner_contract.py`

Expected: T03 后尚无 contract 入口；首次失败为模块/函数不存在。实现后若遗漏运行任务门禁，测试会明确失败为 DID NOT RAISE，而非因连接异常误报。 这是执行前预期，不是本轮已取得的测试结果。

- [ ] **Step 3: 最小实现，先让这一条完整路径可工作**

在 `scripts/migrate_image_owners.py` 应用以下核心，按该文件职责接入真实路由/存储，不替换真实业务层为 mock：

```python
import sqlite3
from services.ownership import expand_ownership

def contract_ownership(db_path, legacy_owner):
    if not legacy_owner:
        raise ValueError("explicit legacy owner required")
    with sqlite3.connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT count(*) FROM tasks WHERE status='running'").fetchone()[0]:
            raise ValueError("running tasks must be reconciled")
        for kind, table in (("file","files"), ("task","tasks")):
            db.execute("""INSERT OR IGNORE INTO object_owners
                SELECT ?,id,? FROM """ + table, (kind, legacy_owner))
        dangling = db.execute("""SELECT count(*) FROM tasks t
            LEFT JOIN files f ON f.id=t.file_id
            WHERE t.file_id IS NOT NULL AND f.id IS NULL""").fetchone()[0]
        if dangling:
            raise ValueError("dangling file references")
        db.execute("CREATE TABLE IF NOT EXISTS ownership_migration(version INTEGER PRIMARY KEY)")
        db.execute("INSERT OR IGNORE INTO ownership_migration VALUES(1)")
    return {"version":1, "legacy_owner":legacy_owner}
```

- [ ] 先用 SQLite backup API 和文件清单生成一致性备份，演练在临时目标恢复；记录切换后新增写入的归档位置。
- [ ] 把 contract_ownership 的示例门禁扩展到 options 中全部 image_ids/foreground_file_id、结果 file_id 及其 owner 一致性；任何悬空/跨人关联都拒绝切换，先报告对象 ID。
- [ ] remove_global_idem_constraint 仅在无旧写入的维护事务内执行，并在同一事务回填 request 映射、保留 rowid/ID 和既有显式索引；事务失败整体回滚。

- [ ] **Step 4: 运行首条测试和受影响既有回归**

Run: `python -m pytest -q tests/test_tb04_owner_contract.py`

Run: `python -m pytest -q -k "tb01 or tb02 or tb03 or tb04 or task_idempotency"`

Expected: 所选测试采集非零、断言通过；任何 HTTP/后端替身错误都解释，不能用 deselect/skip 当完成。

- [ ] **Step 5: 同步文档/ADR**

- [ ] OPERATIONS.md：停接单、备份、接管映射、strict 门禁与恢复新写入
- [ ] docs/adr/0001-owner-scoped-storage.md：调用方迁移完成并将决策标 Accepted

- [ ] **Step 6: 独立提交边界 A**

提交范围：首个外部行为、测试和必要文档；不夹带下一票迁移。Git checkout 中选择实际改动文件后执行：

```bash
git add -- scripts/migrate_image_owners.py services/ownership.py services/store.py services/gateway.py tests/test_tb04_owner_contract.py OPERATIONS.md docs/adr/0001-owner-scoped-storage.md
git commit -m "feat(image): t04 vertical core"
```

非 Git 产品目录使用逐任务审查快照与 SHA256 变更清单；不在此处初始化或推送整个工作区。

## Task 2: 状态反例、完整验收与恢复边界

**Files:** `tests/test_tb04_owner_contract.py`、上面列出的责任模块、文档；新增核心位于 `scripts/migrate_image_owners.py`。

**Interfaces:** 延续 Task 1 的命名/字段/返回值；所有异常路径仍以 owner 隔离和同一任务身份为边界。

- [ ] **Step 1: 把 Review Focus 反例写成具体测试**

以下代码与 Task 1 的测试置于同一测试模块，保留该模块已经定义的 import/帮助函数；不是只画状态图：

```python
from services.ownership import expand_ownership

def test_tb04_repeat_contract_keeps_ids(tmp_path):
    store = Store(tmp_path)
    fid = "file-" + "d"*32
    store.add_file(fid, "old.png", 3, owner="legacy")
    expand_ownership(store.db, "legacy")
    assert contract_ownership(store.db, "legacy")["version"] == 1
    assert contract_ownership(store.db, "legacy")["version"] == 1
    assert store.file(fid, owner="legacy")["id"] == fid

def test_tb04_no_default_owner_after_contract(owner_env):
    import inspect
    from services.store import Store
    assert inspect.signature(Store.task).parameters["owner"].default is inspect.Parameter.empty
    assert inspect.signature(Store.path).parameters["owner"].default is inspect.Parameter.empty

def test_tb04_new_owner_cannot_read_legacy(owner_env):
    with owner_env.client(identity_mode="strict") as c:
        fid = owner_env.upload(c, "legacy")
        assert c.get(f"/v1/files/{fid}/content", headers=owner_env.auth("A")).status_code == 404

def test_tb04_dangling_reference_blocks_cutover(tmp_path):
    store = Store(tmp_path)
    item = store.submit("image_generate",None,{"prompt":"x"},None,owner="legacy")
    with store.connect() as db:
        db.execute("UPDATE tasks SET file_id=? WHERE id=?",("file-"+"f"*32,item["id"]))
    with pytest.raises(ValueError,match="dangling"):
        contract_ownership(store.db,"legacy")

```

- [ ] **Step 2: 执行反例，确认尚缺行为的失败而不是环境错误**

Run: `python -m pytest -q tests/test_tb04_owner_contract.py`

尚未实现的边界必须出现对应断言失败；已经满足的反例作为回归保留。缺依赖/网络误连/测试未采集先修正测试环境，不能计作业务 red。

- [ ] **Step 3: 用最小改动满足反例，完成必要接线**

`scripts/migrate_image_owners.py` 的核心内容：

```python
TASK_COLUMNS = ("id,kind,file_id,options,status,progress,result,error,"
                "idem,fingerprint,created,updated")

def remove_global_idem_constraint(db):
    db.execute("""CREATE TABLE tasks_next(id TEXT PRIMARY KEY, kind TEXT,
        file_id TEXT, options TEXT, status TEXT, progress REAL, result TEXT,
        error TEXT, idem TEXT, fingerprint TEXT, created INTEGER, updated INTEGER)""")
    db.execute("INSERT INTO tasks_next(rowid," + TASK_COLUMNS + ") SELECT rowid," + TASK_COLUMNS + " FROM tasks ORDER BY rowid")
    db.execute("DROP TABLE tasks")
    db.execute("ALTER TABLE tasks_next RENAME TO tasks")
```


- [ ] 去掉用户路径 owner 默认值和全局 idem 回退；以 rg 定位所有 Store 文件/任务调用并逐一传 owner，worker 显式走内部入口。
- [ ] 旧库副本上的失败注入点分别位于复制表前、复制后、重命名前；每次回滚后验证原表和结果仍可读，再重跑成功。
- [ ] T01 中原版兼容测试只使用原 SQL 位置写入与读行，不依赖当前 Store 的默认 owner；将其固定为旧 schema 副本测试。现代应用测试全部显式传 owner，不能为了旧测试保留生产无归属回退。

- [ ] **Step 4: 按逐条验收映射验证，并记录原始证据**

| 本票验收条件 | 验证安排 |
| --- | --- |
| 1. 迁移前保存一致性备份；未指定 legacy owner、存在悬空关联或未完成处理中的任务收敛时，拒绝切换而非默认公开。 | running_task_blocks_contract、缺legacy拒绝；维护状态执行一致性备份与恢复演练。 |
| 2. 文件、各状态任务、结果、素材关联及旧幂等记录完整归属；迁移中断后可重试，原 ID 与结果引用保持有效。 | repeat_contract_keeps_ids；复制/重命名前故障注入，重跑后原ID和结果可读。 |
| 3. 所有迁移调用方已切换，才删除旧全局幂等/无 owner 访问回退；未配置归属不得静默回到共享模式。 | no_default_owner_after_contract＋rg所有调用方审查；不同owner同键成功。 |
| 4. 新用户默认无权读旧数据；接管 legacy 的 owner 可继续下载旧结果；保留保守的运行中任务失败策略，不自动重跑。 | new_owner_cannot_read_legacy、dangling_reference_blocks_cutover；旧结果接管下载。 |
| 5. 生产启用记录包含接管映射、回滚版本、备份和新增写入保全方案；不把共享旧 Key 再分发给多人。 | 在副本插入切换后新文件/任务再恢复，先归档并核对新写入不丢失；生产映射单独登记。 |

Run: `python -m pytest --collect-only -q -k tb04_owner_contract`

Run: `python -m pytest -q -k tb04_owner_contract`

Run: `python -m pytest -q -k "tb01 or tb02 or tb03 or tb04 or task_idempotency"`


独立演示：在包含上传、排队、运行、完成任务的旧库副本中断并重跑迁移；使用 legacy 接管 Key 和新用户 Key 通过 API 比对数据归属。



- [ ] **Step 5: 文档、ADR 与证据同步**

将实际测试输出、受影响回归、失败与恢复步骤写入 OPERATIONS.md；与当前计划对应的 AC 映射逐项填证据。没有实测的项保持未验收，不能只打勾。

- [ ] **Step 6: 独立提交边界 B**

提交范围：其余反例测试、守卫/兼容接线、有效文档；保持本票在前置完成后独立可演示。

```bash
git add -- scripts/migrate_image_owners.py services/ownership.py services/store.py services/gateway.py tests/test_tb04_owner_contract.py OPERATIONS.md docs/adr/0001-owner-scoped-storage.md
git commit -m "test(image): t04 boundaries and recovery"
```

## Rollback / compatibility strategy

先停接单并保全切换后的新增文件/任务；只回退到仍识别 owner 的兼容版本。需要恢复备份时先归档、核对新增写入，禁止覆盖丢失新结果或恢复共享可读入口。

维护过程先停止新工作并保全新增写入；对运行图片定向停止且确认后端空闲。不能回退成跨用户共享访问、关闭保护器或盲目重跑。

## Out of scope

不增加配额、不更改模型；不自动决定生产接管人名单；不把最终双端业务验收计为本票已完成。

## Verification environment

以下 python 指令在受支持的工程虚拟环境执行。原工作区可用 .venv/bin/python；Windows 使用对应 .venv\\Scripts\\python.exe。新测试尚未创建，未采集到测试不算通过；本轮仅编写计划，不冒充 red/green 或实机验收已执行。


## Self-review and execution handoff

- [x] 每个本票验收条件已映射到上表；父规格归属：AC-11、AC-12、AC-13、AC-19、AC-20。
- [x] 第一条失败原因与最小实现明确；状态反例为测试代码/实际演示，不只保留图。
- [x] 新签名来自共享契约，当前尚未实现的接口由明确前置/本票交付。
- [x] 边界 A/B 各自带测试与文档；回退不会丢新数据或恢复共享读取。
- [ ] 后续执行者运行 red/green、受影响回归与所需实机验收，填写实际证据后再声明完成。

本次只批准编写和发布计划，不启动产品实现。执行时由用户选择原生或子代理方式；未取得执行授权前不启动实现/部署。

## 一致性备份最小实现与恢复测试

写入 scripts/migrate_image_owners.py；仅在维护步骤已停止全部写入者并确认后端空闲后执行。备份目录必须是新的独占目录，不能覆盖旧备份。

```python
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

def backup_state(db_path,backup_dir):
    db_path=Path(db_path); target=Path(backup_dir)
    target.mkdir(parents=True,exist_ok=False)
    with sqlite3.connect(db_path) as source, sqlite3.connect(target/"state.sqlite3") as copy:
        source.backup(copy)
    source_files=db_path.parent/"files"
    shutil.copytree(source_files,target/"files")
    hashes={str(p.relative_to(target)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in target.rglob("*") if p.is_file()}
    (target/"manifest.json").write_text(json.dumps(hashes,sort_keys=True)+"\n",encoding="utf-8")
    return hashes
```

```python
from scripts.migrate_image_owners import backup_state

def test_tb04_backup_does_not_overwrite_previous_snapshot(tmp_path):
    store=Store(tmp_path/"runtime")
    target=tmp_path/"backup"
    hashes=backup_state(store.db,target)
    assert "state.sqlite3" in hashes
    with pytest.raises(FileExistsError):
        backup_state(store.db,target)
```
