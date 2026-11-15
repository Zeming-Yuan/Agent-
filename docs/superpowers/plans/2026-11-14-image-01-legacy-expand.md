# T01 Expand：旧身份可在兼容结构上完成原有图片流程 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 维护者在旧数据副本上扩展身份与归属结构后，原用户仍能上传、生成、查询和取图，任务 ID 与结果引用不变。

**Architecture:** Consumes: 当前 Store(root, max_pending=4) 和 create_app(root, token)。Produces: 执行契约中的 Principal、KeyRegistry、expand_ownership、preflight_ownership、require_owner、owner_env；新增 create_app 的 key_registry/identity_mode 参数，默认 legacy。 先读共享执行契约并保留既有兼容边界；本票只交付确认的纵向行为，不扩展为通用重构。

**Tech Stack:** Python、FastAPI、SQLite、httpx、Pillow、stdio MCP；固定 ComfyUI 0.33.2；平台专属脚本按本票列出的操作系统执行。

**Spec:** [父规格 #1](https://github.com/Zeming-Yuan/Agent-/issues/1)；[完整规格](../../specs/2026-11-14-image-service-reliability-and-multiuser.md)；[共享执行契约](2026-11-14-image-execution-contract.md)。执行者必须同时读取三者。

**Ticket:** T01；Blocked by：无（可立即开始）。可以立即开始；这是共享迁移的兼容前置。

**Plan status:** 已确认 ticket 的实施计划；本轮尚未实现产品或运行新测试/硬件测量。

## 执行记录（2026-11-15）

用户已明确授权执行 issue #2，确认迁移接口、KeyRegistry 与真实 HTTP/Store/worker 测试 seam，并授权在工作区外建立脱敏源码 Git checkout。以下“本次只批准编写计划”等表述保留为 2026-11-14 的历史记录，不限制此次已授权实现。

本票原生串行完成两个切片，分支 `issue-2-legacy-expand` 位于 `/home/clusteradmin/.codex/workspaces/agent-mm-issue-2-20261115`；基线 `443fc602`，实现提交 `f1f8084`、预检修复 `0d555b5`、身份与兼容验证 `a6ef5ed`。源码基线 12/12 匹配，旧服务冻结副本 8/8 精确匹配。计划的核心/边界步骤已由实际 red→green、独立提交和各切片双轴 review 执行；不把历史代码示例或未勾选的原计划当成执行证据。

验证：29 项 T01 已采集，受影响回归 31 passed，最终 pytest 全套 79 passed（1 项既有依赖弃用警告）。Standards 无发现；Spec 的 factory 预检 P2 已修复并复审通过，最终无未处理发现。证据及逐 AC 映射见 `evidence/issue-2/acceptance.md`；审查见 `review-a.md` / `review-b.md`；决策见 `progress.md` 与 Proposed ADR 0001。

本次只完成离线合成旧数据副本验证和本地提交/同步；未部署、未推送。生产旧数据、实机后端与 Windows/macOS Harness 未验证。strict 暂拒绝启动，staging 仅隔离测试；文件/任务 owner 迁移继续由现有 #3/#4/#5（T02/T03/T04）承接，最终实机和双端由 #12—#15 承接；父规格不关闭。

## PR 交付接续（2026-11-15）

用户随后授权创建 PR，并在无冲突时合并。远端 main 原先仅含计划和规格；PR 分支 `pr/issue-2-legacy-expand` 从远端 main 建立，先引入已核对的公开源码基线，再逐提交接入 T01。远端独有的 `2026-11-14-image-source-baseline.json` 保留；脚本可执行权限与原审查树一致。原始审查提交号保留为本地来源记录，PR 上的对应提交号因接入远端历史而改变，冻结旧服务仍按独立 SHA256 校验。

既有“未推送、未部署”记录描述前一个本地交付阶段；本次授权发布源码并合并 PR，不包含生产部署或启用多人入口。应用、测试与前述已审查版本逐字节核对；只补充交付记录及保留远端文档。类型/静态/构建门禁仍未配置，生产与双端实机验收仍未验证。

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

1. 旧版位置 INSERT：新增旁表后仍可写原 4/12 列 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
2. legacy owner 缺失：必须拒绝默认归属 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
3. expand 重复运行：保留已有 owner 不覆盖 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
4. 旧版在 expand 后新增行：预检必须发现 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
5. 凭证泄露与非法模式：摘要存储，legacy 不放行其他 owner → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。

---

## File structure and interfaces

- Create: services/identity.py — 随机 Key、摘要与稳定身份
- Create: services/ownership.py — 旁表 expand 与只读预检
- Modify: services/gateway.py — 可选身份注册表，默认 legacy 模式
- Create: tests/conftest.py — 执行契约中定义的 owner_env/ImageBackend
- Create: tests/test_tb01_legacy_expand.py
- Modify: OPERATIONS.md — expand/预检及兼容回退

- Create: docs/adr/0001-owner-scoped-storage.md — 本票文档/ADR/实际测量记录同步

**Consumes / Produces:** Consumes: 当前 Store(root, max_pending=4) 和 create_app(root, token)。Produces: 执行契约中的 Principal、KeyRegistry、expand_ownership、preflight_ownership、require_owner、owner_env；新增 create_app 的 key_registry/identity_mode 参数，默认 legacy。

## Task 1: 首条用户反例与最小纵向实现

**Files:** 使用上面列出的本票实现文件；首条测试写入 `tests/test_tb01_legacy_expand.py`。本任务最小实现核心位于 `services/ownership.py`。

**Interfaces:** 消费上述输入，产出本票外部行为；新公共签名以 Architecture/共享契约为准，不另起别名。

- [ ] **Step 1: 写第一条失败测试**

```python
import sqlite3
from services.store import Store
from services.ownership import expand_ownership, preflight_ownership

def test_tb01_legacy_expand_preserves_positional_writes(tmp_path):
    store = Store(tmp_path)
    fid = "file-" + "a" * 32
    with store.connect() as db:
        db.execute("INSERT INTO files VALUES(?,?,?,?)", (fid, "旧图.png", 3, 1))
    expand_ownership(store.db, "legacy")
    with store.connect() as db:
        db.execute("INSERT INTO files VALUES(?,?,?,?)",
                   ("file-" + "b" * 32, "new.png", 4, 1))
    with store.connect() as db:
        assert db.execute("SELECT bytes FROM files WHERE id=?", (fid,)).fetchone()[0] == 3
    assert preflight_ownership(store.db)["unowned_files"] == 1
    expand_ownership(store.db, "legacy")
    assert preflight_ownership(store.db)["unowned_files"] == 0
```

- [ ] **Step 2: 运行并确认预期失败原因**

Run: `python -m pytest -q tests/test_tb01_legacy_expand.py`

Expected: 当前 services.ownership/services.identity 都尚不存在，首次失败为新模块缺失；补齐模块后仍须验证旧位置参数写入和预检的语义断言，不能仅让 import 通过。 这是执行前预期，不是本轮已取得的测试结果。

- [ ] **Step 3: 最小实现，先让这一条完整路径可工作**

在 `services/ownership.py` 应用以下核心，按该文件职责接入真实路由/存储，不替换真实业务层为 mock：

```python
import sqlite3
from fastapi import HTTPException

def expand_ownership(db_path, legacy_owner):
    if not legacy_owner:
        raise ValueError("explicit legacy owner required")
    with sqlite3.connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("""CREATE TABLE IF NOT EXISTS object_owners(
            kind TEXT NOT NULL, object_id TEXT NOT NULL, owner TEXT NOT NULL,
            PRIMARY KEY(kind, object_id))""")
        for kind, table in (("file", "files"), ("task", "tasks")):
            db.execute(f"""INSERT OR IGNORE INTO object_owners
                SELECT ?, id, ? FROM {table}""", (kind, legacy_owner))

def preflight_ownership(db_path):
    report = {}
    with sqlite3.connect(db_path) as db:
        for kind, table in (("file", "files"), ("task", "tasks")):
            has_owners = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='object_owners'").fetchone()
            if not has_owners:
                report["unowned_" + table] = db.execute("SELECT count(*) FROM " + table).fetchone()[0]
                continue
            report["unowned_" + table] = db.execute(f"""
                SELECT count(*) FROM {table} x LEFT JOIN object_owners o
                ON o.kind=? AND o.object_id=x.id WHERE o.object_id IS NULL
            """, (kind,)).fetchone()[0]
        report["running_tasks"] = db.execute(
            "SELECT count(*) FROM tasks WHERE status='running'").fetchone()[0]
    return report

def require_owner(db, kind, object_id, owner):
    found = db.execute("""SELECT 1 FROM object_owners
        WHERE kind=? AND object_id=? AND owner=?""",
        (kind, object_id, owner)).fetchone()
    if not found:
        raise HTTPException(404, "Object not found")
```

- [ ] 不改变 files/tasks 的原列数；把 legacy 归属旁表与预检放进 factory 初始化，旧进程新写入仍由预检暴露。
- [ ] 本任务仅接入 ownership 旁表和原 SQL 兼容测试；暂不创建 tests/conftest.py，也不向 gateway 引入 services.identity。身份注册表、鉴权切换和共享夹具统一在 Task 2 完成，确保边界 A 可以独立通过。

- [ ] **Step 4: 运行首条测试和受影响既有回归**

Run: `python -m pytest -q tests/test_tb01_legacy_expand.py`

Run: `python -m pytest -q -k "tb01 or task_idempotency_cancel_and_persistence or upload_limit_paths_and_delete"`

Expected: 所选测试采集非零、断言通过；任何 HTTP/后端替身错误都解释，不能用 deselect/skip 当完成。

- [ ] **Step 5: 同步文档/ADR**

- [ ] OPERATIONS.md：expand、只读预检、旧版写入兼容和回退步骤
- [ ] docs/adr/0001-owner-scoped-storage.md：旁表兼容、阶段门禁及为何不直接加列；记录 Proposed，T04 后再 Accepted

- [ ] **Step 6: 独立提交边界 A**

提交范围：首个外部行为、测试和必要文档；不夹带下一票迁移。Git checkout 中选择实际改动文件后执行：

```bash
python - <<'PY'
from pathlib import Path
import subprocess
candidates = ["services/identity.py","services/ownership.py","services/gateway.py","tests/conftest.py","tests/test_tb01_legacy_expand.py","OPERATIONS.md","docs/adr/0001-owner-scoped-storage.md"]
paths = [p for p in candidates if Path(p).is_file()]
subprocess.run(["git", "add", "--", *paths], check=True)
PY
git commit -m "feat(image): t01 vertical core"
```

非 Git 产品目录使用逐任务审查快照与 SHA256 变更清单；不在此处初始化或推送整个工作区。

## Task 2: 状态反例、完整验收与恢复边界

**Files:** `tests/test_tb01_legacy_expand.py`、上面列出的责任模块、文档；新增核心位于 `services/identity.py`。

**Interfaces:** 延续 Task 1 的命名/字段/返回值；所有异常路径仍以 owner 隔离和同一任务身份为边界。

- [ ] **Step 1: 把 Review Focus 反例写成具体测试**

以下代码与 Task 1 的测试置于同一测试模块，保留该模块已经定义的 import/帮助函数；不是只画状态图：

```python
import pytest
from services.identity import KeyRegistry

@pytest.mark.parametrize("repeat", [1, 2, 3])
def test_tb01_expand_is_repeatable(tmp_path, repeat):
    store = Store(tmp_path)
    with store.connect() as db:
        db.execute("INSERT INTO files VALUES(?,?,?,?)", ("file-" + "c" * 32, "x", 1, 1))
    for _ in range(repeat):
        expand_ownership(store.db, "legacy")
    assert preflight_ownership(store.db)["unowned_files"] == 0

def test_tb01_missing_legacy_owner_is_rejected(tmp_path):
    store = Store(tmp_path)
    with pytest.raises(ValueError):
        expand_ownership(store.db, "")

def test_tb01_registry_stores_no_raw_key(tmp_path):
    registry = KeyRegistry(tmp_path / "keys.sqlite3")
    raw = registry.issue("A")
    assert registry.resolve(raw).owner == "A"
    assert registry.resolve("wrong-key") is None
    assert raw.encode() not in (tmp_path / "keys.sqlite3").read_bytes()

def test_tb01_legacy_mode_blocks_other_owner(owner_env):
    with owner_env.client(identity_mode="legacy") as c:
        assert c.get("/v1/models", headers=owner_env.auth("A")).status_code == 401
        assert c.get("/v1/models", headers=owner_env.auth("legacy")).status_code == 200

def test_tb01_expand_preserves_explicit_owner(tmp_path):
    store = Store(tmp_path)
    fid = "file-"+"e"*32
    with store.connect() as db:
        db.execute("INSERT INTO files VALUES(?,?,?,?)",(fid,"x",1,1))
    expand_ownership(store.db,"legacy")
    with store.connect() as db:
        db.execute("UPDATE object_owners SET owner='A' WHERE kind='file' AND object_id=?",(fid,))
    expand_ownership(store.db,"legacy")
    with store.connect() as db:
        assert db.execute("SELECT owner FROM object_owners WHERE object_id=?",(fid,)).fetchone()[0] == "A"

```

- [ ] **Step 2: 执行反例，确认尚缺行为的失败而不是环境错误**

Run: `python -m pytest -q tests/test_tb01_legacy_expand.py`

尚未实现的边界必须出现对应断言失败；已经满足的反例作为回归保留。缺依赖/网络误连/测试未采集先修正测试环境，不能计作业务 red。

- [ ] **Step 3: 用最小改动满足反例，完成必要接线**

`services/identity.py` 的核心内容：


def test_tb01_preflight_reads_unexpanded_legacy_schema(tmp_path):
    store = Store(tmp_path)
    with store.connect() as db:
        db.execute("INSERT INTO files VALUES(?,?,?,?)",("file-"+"f"*32,"legacy",1,1))
    assert preflight_ownership(store.db)["unowned_files"] == 1

```python
import hashlib
import secrets
import sqlite3
import uuid
from dataclasses import dataclass

@dataclass(frozen=True)
class Principal:
    owner: str
    key_id: str

class KeyRegistry:
    def __init__(self, db_path):
        self.db_path = db_path
        with sqlite3.connect(db_path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS api_keys(
                key_id TEXT PRIMARY KEY, owner TEXT NOT NULL,
                digest TEXT UNIQUE NOT NULL, revoked INTEGER NOT NULL)""")
    def register(self, owner, raw_key):
        if not owner or len(raw_key) < 16:
            raise ValueError("owner and strong key required")
        digest = hashlib.sha256(raw_key.encode()).hexdigest()
        with sqlite3.connect(self.db_path) as db:
            db.execute("INSERT OR IGNORE INTO api_keys VALUES(?,?,?,0)",
                       (uuid.uuid4().hex, owner, digest))
            row = db.execute("SELECT owner,key_id FROM api_keys WHERE digest=?",
                             (digest,)).fetchone()
        if row[0] != owner:
            raise ValueError("key already belongs to another owner")
        return Principal(*row)
    def issue(self, owner):
        raw = secrets.token_urlsafe(32)
        self.register(owner, raw)
        return raw
    def resolve(self, raw_key):
        digest = hashlib.sha256(raw_key.encode()).hexdigest()
        with sqlite3.connect(self.db_path) as db:
            row = db.execute("SELECT owner,key_id FROM api_keys WHERE digest=? AND revoked=0",
                             (digest,)).fetchone()
        return Principal(*row) if row else None
    def revoke(self, key_id):
        with sqlite3.connect(self.db_path) as db:
            db.execute("UPDATE api_keys SET revoked=1 WHERE key_id=?", (key_id,))
```


- [ ] 先创建上面的 KeyRegistry，再将已验证的 Bearer 解析结果交给 resolve；legacy 模式只接受 owner=='legacy' 并设置 request.state.principal。无注册表时用原 token 注册 legacy；staging/strict 只来自服务配置。
- [ ] 按共享契约实现完整 owner_env/ImageBackend：模拟边界只在 /prompt、/history、/view、/queue、/interrupt 和 /system_stats；返回真实可解码 PNG，所有真实 HTTP/Store/worker 保留。
- [ ] 把旧版本复制到临时审查目录，在同一 expand 后数据副本运行原有 task_idempotency 和上传测试；不是只让新版读取旧库。

- [ ] **Step 4: 按逐条验收映射验证，并记录原始证据**

| 本票验收条件 | 验证安排 |
| --- | --- |
| 1. 新增稳定 owner、Key 映射及对象归属的新表示；与旧表示并存，当前共享 Key 仅映射到明确 legacy owner。 | 首次失败测试及旧 SQL 位置写入；旧版/过渡版各跑原 task_idempotency 与上传用例。 |
| 2. 旧版应用和过渡版分别在 expand 后的数据副本完成原有单用户上传→生成→取图；不能仅证明查询兼容而破坏旧写入。 | 旧版与过渡版在同一 expand 后副本做真实上传→生成→取图，比较原 ID/结果。 |
| 3. 提供只读迁移预检，统计无归属文件、任务、幂等记录与运行中任务；不给新用户开放生产访问。 | preflight_ownership 统计无归属/运行任务；注入旧版新写入和缺 owner 的反例。 |
| 4. 原任务 ID、参考图/前景关联、结果引用及全局容量边界保留；重启恢复行为无意外改变。 | 全量现有回归＋副本重启，核对参考/结果映射与全局边界。 |

Run: `python -m pytest --collect-only -q -k tb01_legacy_expand`

Run: `python -m pytest -q -k tb01_legacy_expand`

Run: `python -m pytest -q -k "tb01 or task_idempotency_cancel_and_persistence or upload_limit_paths_and_delete"`


独立演示：在脱敏旧数据副本执行 expand，分别用旧版和过渡版以 legacy 身份提交一张图并取回；比对既有任务与文件仍可读取。



- [ ] **Step 5: 文档、ADR 与证据同步**

将实际测试输出、受影响回归、失败与恢复步骤写入 OPERATIONS.md；与当前计划对应的 AC 映射逐项填证据。没有实测的项保持未验收，不能只打勾。

- [ ] **Step 6: 独立提交边界 B**

提交范围：其余反例测试、守卫/兼容接线、有效文档；保持本票在前置完成后独立可演示。

```bash
python - <<'PY'
from pathlib import Path
import subprocess
candidates = ["services/identity.py","services/ownership.py","services/gateway.py","tests/conftest.py","tests/test_tb01_legacy_expand.py","OPERATIONS.md","docs/adr/0001-owner-scoped-storage.md"]
paths = [p for p in candidates if Path(p).is_file()]
subprocess.run(["git", "add", "--", *paths], check=True)
PY
git commit -m "test(image): t01 boundaries and recovery"
```

## Rollback / compatibility strategy

仍在 expand 阶段保留旧表示；通过已验证的旧版兼容路径回退应用，不删除新表示或数据。旧版不能完整写入则本票不通过。

维护过程先停止新工作并保全新增写入；对运行图片定向停止且确认后端空闲。不能回退成跨用户共享访问、关闭保护器或盲目重跑。

## Out of scope

不开放多人生产使用；不清理旧字段/索引；不做公平排队、进度、内存策略或个人配额。

## Verification environment

以下 python 指令在受支持的工程虚拟环境执行。原工作区可用 .venv/bin/python；Windows 使用对应 .venv\\Scripts\\python.exe。新测试尚未创建，未采集到测试不算通过；本轮仅编写计划，不冒充 red/green 或实机验收已执行。


## Self-review and execution handoff

- [x] 每个本票验收条件已映射到上表；父规格归属：AC-19、AC-20。
- [x] 第一条失败原因与最小实现明确；状态反例为测试代码/实际演示，不只保留图。
- [x] 新签名来自共享契约，当前尚未实现的接口由明确前置/本票交付。
- [x] 边界 A/B 各自带测试与文档；回退不会丢新数据或恢复共享读取。
- [ ] 后续执行者运行 red/green、受影响回归与所需实机验收，填写实际证据后再声明完成。

本次只批准编写和发布计划，不启动产品实现。执行时由用户选择原生或子代理方式；未取得执行授权前不启动实现/部署。

## T01 必须交付的共享测试夹具（完整起始内容）

以下内容写入 tests/conftest.py；后续 T07/T09 在各自票中串行扩展事件/资源注入，不在本票引入未实现的资源模块。

```python
import asyncio
import io
import json
import threading
import time
from types import SimpleNamespace
import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from services.gateway import create_app
from services.identity import KeyRegistry

class ImageBackend:
    def __init__(self,hold=False,hold_stop=False):
        self.jobs=[]; self.running=set()
        self.started=threading.Event(); self.finish=threading.Event()
        self.release_stop=threading.Event(); self.offline=threading.Event()
        if not hold: self.finish.set()
        if not hold_stop: self.release_stop.set()
        buf=io.BytesIO(); Image.new("RGB",(8,8),"green").save(buf,format="PNG")
        self.png=buf.getvalue()
    async def __call__(self,req):
        p=req.url.path
        if p=="/system_stats":
            return httpx.Response(503 if self.offline.is_set() else 200,json={"system":{}})
        if p=="/health": return httpx.Response(200,json={"status":"ready"})
        if p=="/queue" and req.method=="GET":
            return httpx.Response(200,json={"queue_running":[[0,x,{}, {}, []] for x in self.running],"queue_pending":[]})
        if p=="/queue": return httpx.Response(200,json={})
        if p=="/interrupt":
            pid=json.loads(req.content).get("prompt_id")
            if pid in self.running:
                stopped=await asyncio.to_thread(self.release_stop.wait,2.0)
                if not stopped: return httpx.Response(503,json={"error":"stop held"})
                self.running.discard(pid)
            elif pid is None:
                self.running.clear()
            return httpx.Response(200,json={})
        if p=="/prompt":
            body=json.loads(req.content); pid=body["prompt_id"]
            self.jobs.append(body); self.running.add(pid); self.started.set()
            return httpx.Response(200,json={"prompt_id":pid})
        if p.startswith("/history/"):
            pid=p.rsplit("/",1)[-1]
            if not self.finish.is_set(): return httpx.Response(200,json={})
            self.running.discard(pid)
            return httpx.Response(200,json={pid:{"status":{"completed":True,"status_str":"success"},
                "outputs":{"9":{"images":[{"filename":"fixture.png","subfolder":"","type":"output"}]}}}})
        if p=="/history": return httpx.Response(200,json={})
        if p=="/free": return httpx.Response(200,json={})
        if p=="/upload/image": return httpx.Response(200,json={"name":"fixture.png","subfolder":""})
        if p=="/view": return httpx.Response(200,content=self.png)
        return httpx.Response(404,json={"error":"unexpected backend path"})

@pytest.fixture
def owner_env(tmp_path):
    registry=KeyRegistry(tmp_path/"keys.sqlite3")
    keys={o:registry.issue(o) for o in ("legacy","A","B")}
    env=SimpleNamespace(root=tmp_path/"runtime",registry=registry,keys=keys,new_backend=ImageBackend)
    env.auth=lambda owner:{"Authorization":"Bearer "+keys[owner]}
    def client(*,backend=None,run_worker=False,identity_mode="staging"):
        backend=backend or ImageBackend()
        app=create_app(env.root,keys["legacy"],key_registry=registry,
            identity_mode=identity_mode,transport=httpx.MockTransport(backend),
            run_worker=run_worker,audio_enabled=False,images_enabled=True)
        return TestClient(app)
    env.client=client
    def upload(c,owner="A"):
        png=ImageBackend().png
        r=c.post("/v1/files",headers=env.auth(owner),files={"file":("fixture.png",png,"image/png")})
        assert r.status_code==200,r.text
        return r.json()["id"]
    env.upload=upload
    def submit(c,owner="A",*,kind="image_generate",request_key=None,**options):
        headers=env.auth(owner)
        if request_key is not None: headers["Idempotency-Key"]=request_key
        return c.post("/v1/tasks",headers=headers,json={"kind":kind,"options":{"prompt":"fixture",**options}})
    env.submit=submit
    def wait_task(c,tid,owner,predicate,timeout=3.0):
        deadline=time.monotonic()+timeout; last=None
        while time.monotonic()<deadline:
            r=c.get("/v1/tasks/"+tid,headers=env.auth(owner)); assert r.status_code==200,r.text
            last=r.json()
            if predicate(last): return last
            threading.Event().wait(.01)
        raise AssertionError(f"task did not converge: {last}")
    env.wait_task=wait_task
    return env
```
