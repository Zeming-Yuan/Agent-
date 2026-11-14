# T06 MCP 续取：工具重启与保存失败只重取，不重生成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用户的桌面工具在提交响应丢失、进程重启或本地保存失败后，能找回原任务并继续取图；重复提示词的新创作仍可单独生成。

**Architecture:** Consumes: T05 本人列表、GET /v1/me 和 scoped replay。Produces: 执行契约中的 RequestJournal；ImageBridge(..., journal_path=None)；generate/edit(..., *, request_id=None)；MCP list_image_tasks；构建入口不默认导出共享 Key。 先读共享执行契约并保留既有兼容边界；本票只交付确认的纵向行为，不扩展为通用重构。

**Tech Stack:** Python、FastAPI、SQLite、httpx、Pillow、stdio MCP；固定 ComfyUI 0.33.2；平台专属脚本按本票列出的操作系统执行。

**Spec:** [父规格 #1](https://github.com/Zeming-Yuan/Agent-/issues/1)；[完整规格](../../specs/2026-11-14-image-service-reliability-and-multiuser.md)；[共享执行契约](2026-11-14-image-execution-contract.md)。执行者必须同时读取三者。

**Ticket:** T06；Blocked by：T05。需要 T05 的本人任务列表与可重放服务端契约；公共桥接及公共打包改动在本票串行完成。

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

1. 进程在响应前退出：先持久化请求再发网络 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
2. 同人不同 Key：owner 不变，日志可恢复 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
3. 换人/换服务：同 request_id 不跨分区 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
4. 磁盘或目录失败：不触发第二次推理 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
5. 同提示词新意图：新 request_id 可生成，不能内容永久去重 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。

---

## File structure and interfaces

- Create: client/request_journal.py — 持久请求及 owner 分区
- Modify: client/spark_image_tools.py — request_id、恢复工具及原子保存
- Modify: scripts/build_image_client_bundle.py — 显式个人配置/平台资源输入
- Create: tests/test_tb06_mcp_resume.py
- Modify: docs/IMAGE-SERVICE.md

**Consumes / Produces:** Consumes: T05 本人列表、GET /v1/me 和 scoped replay。Produces: 执行契约中的 RequestJournal；ImageBridge(..., journal_path=None)；generate/edit(..., *, request_id=None)；MCP list_image_tasks；构建入口不默认导出共享 Key。

## Task 1: 首条用户反例与最小纵向实现

**Files:** 使用上面列出的本票实现文件；首条测试写入 `tests/test_tb06_mcp_resume.py`。本任务最小实现核心位于 `client/request_journal.py`。

**Interfaces:** 消费上述输入，产出本票外部行为；新公共签名以 Architecture/共享契约为准，不另起别名。

- [ ] **Step 1: 写第一条失败测试**

```python
import asyncio
from pathlib import Path
import httpx
from client.spark_image_tools import ImageBridge

def test_tb06_lost_response_replays_after_bridge_restart(tmp_path):
    accepted = {}
    dropped = False
    tid = "task-" + "a"*32
    def server(req):
        nonlocal dropped
        if req.url.path == "/v1/me":
            return httpx.Response(200,json={"owner":"A"})
        if req.url.path == "/v1/tasks" and req.method == "POST":
            key = req.headers["idempotency-key"]
            accepted.setdefault(key, tid)
            if not dropped:
                dropped = True
                raise httpx.ReadError("accepted response lost",request=req)
            return httpx.Response(202,json={"id":accepted[key],"status":"queued"})
        return httpx.Response(404)
    async def run():
        args = ("https://spark.invalid/v1","test-secret-token",
                Path("certificates/agent-root-ca.crt"),tmp_path/"out")
        journal = tmp_path/"requests.sqlite3"
        one = ImageBridge(*args,journal_path=journal,transport=httpx.MockTransport(server))
        try:
            await one.generate("p","1024x1024",0,"","",request_id="r1")
        except httpx.ReadError:
            pass
        finally:
            await one.close()
        two = ImageBridge(*args,journal_path=journal,transport=httpx.MockTransport(server))
        try:
            result = await two.generate("p","1024x1024",0,"","",request_id="r1")
            assert result["id"] == tid
            assert len(accepted) == 1
        finally:
            await two.close()
    asyncio.run(run())
```

- [ ] **Step 2: 运行并确认预期失败原因**

Run: `python -m pytest -q tests/test_tb06_mcp_resume.py`

Expected: 现有 ImageBridge 不接受 journal_path/request_id，或不发送 Idempotency-Key；首次为 TypeError/缺失 header。实现参数后必须进一步证明响应丢失时真正复用了同一个请求键。 这是执行前预期，不是本轮已取得的测试结果。

- [ ] **Step 3: 最小实现，先让这一条完整路径可工作**

在 `client/request_journal.py` 应用以下核心，按该文件职责接入真实路由/存储，不替换真实业务层为 mock：

```python
import json
import sqlite3

class RequestJournal:
    def __init__(self, path, service, owner):
        self.path, self.service, self.owner = path, service, owner
        with sqlite3.connect(path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS requests(
                service TEXT, owner TEXT, request_id TEXT, fingerprint TEXT,
                payload TEXT, task_id TEXT,
                PRIMARY KEY(service,owner,request_id))""")
    def prepare(self, request_id, fingerprint, payload):
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            key = (self.service,self.owner,request_id)
            row = db.execute("SELECT fingerprint,task_id FROM requests WHERE service=? AND owner=? AND request_id=?",key).fetchone()
            if row and row[0] != fingerprint:
                raise ValueError("request id reused with different input")
            if not row:
                db.execute("INSERT INTO requests VALUES(?,?,?,?,?,NULL)",
                    key+(fingerprint,json.dumps(payload,ensure_ascii=False)))
            return {"request_id":request_id,"task_id":row[1] if row else None}
    def accepted(self, request_id, task_id):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE requests SET task_id=? WHERE service=? AND owner=? AND request_id=?",
                       (task_id,self.service,self.owner,request_id))
    def pending(self):
        with sqlite3.connect(self.path) as db:
            return [{"request_id":r[0],"task_id":r[1]} for r in db.execute(
                "SELECT request_id,task_id FROM requests WHERE service=? AND owner=?",
                (self.service,self.owner))]
```

- [ ] 调用 /v1/me 成功确定 owner 后打开对应日志；prepare 提交成功才 POST /tasks。无 request_id 的明确新意图生成 UUID，单次传输重试保留该值；跨调用恢复必须使用日志/list_image_tasks 返回的标识，不猜测相同提示词就是重试。
- [ ] 编辑首次上传后把已确认素材 ID 与本地内容摘要保存在本地 payload；重试优先复用仍存在的本人素材，缺失时重新上传但沿用业务请求键。
- [ ] 取回结果先验证 PNG 解码/尺寸再原子写入；下载/写入失败不能调用 generate/edit，保留 completed 任务和 request 映射。

- [ ] **Step 4: 运行首条测试和受影响既有回归**

Run: `python -m pytest -q tests/test_tb06_mcp_resume.py`

Run: `python -m pytest -q -k "tb06 or bridge_returns_real_mcp_image_content"`

Expected: 所选测试采集非零、断言通过；任何 HTTP/后端替身错误都解释，不能用 deselect/skip 当完成。

- [ ] **Step 5: 同步文档/ADR**

- [ ] docs/IMAGE-SERVICE.md：恢复工具、request_id、新意图与重试区别
- [ ] OPERATIONS.md：客户端日志备份、Key 轮换及本地取图失败恢复

- [ ] **Step 6: 独立提交边界 A**

提交范围：首个外部行为、测试和必要文档；不夹带下一票迁移。Git checkout 中选择实际改动文件后执行：

```bash
git add -- client/request_journal.py client/spark_image_tools.py scripts/build_image_client_bundle.py tests/test_tb06_mcp_resume.py docs/IMAGE-SERVICE.md
git commit -m "feat(image): t06 vertical core"
```

非 Git 产品目录使用逐任务审查快照与 SHA256 变更清单；不在此处初始化或推送整个工作区。

## Task 2: 状态反例、完整验收与恢复边界

**Files:** `tests/test_tb06_mcp_resume.py`、上面列出的责任模块、文档；新增核心位于 `client/spark_image_tools.py`。

**Interfaces:** 延续 Task 1 的命名/字段/返回值；所有异常路径仍以 owner 隔离和同一任务身份为边界。

- [ ] **Step 1: 把 Review Focus 反例写成具体测试**

以下代码与 Task 1 的测试置于同一测试模块，保留该模块已经定义的 import/帮助函数；不是只画状态图：

```python
import pytest
from client.request_journal import RequestJournal

def test_tb06_journal_owner_and_service_partition(tmp_path):
    path = tmp_path/"journal.sqlite3"
    a = RequestJournal(path,"svc1","A")
    a.prepare("r","fp",{"prompt":"p"})
    a.accepted("r","task-a")
    assert RequestJournal(path,"svc1","B").pending() == []
    assert RequestJournal(path,"svc2","A").pending() == []
    assert RequestJournal(path,"svc1","A").pending()[0]["task_id"] == "task-a"

def test_tb06_same_key_changed_input_is_rejected(tmp_path):
    j = RequestJournal(tmp_path/"j.sqlite3","svc","A")
    j.prepare("r","first",{"prompt":"a"})
    with pytest.raises(ValueError):
        j.prepare("r","second",{"prompt":"b"})
    assert j.prepare("new","first",{"prompt":"a"})["task_id"] is None

def test_tb06_save_failure_does_not_delete_existing_target(tmp_path):
    from client.spark_image_tools import save_png_atomically
    target = tmp_path/"existing.png"
    target.write_bytes(b"old-result")
    with pytest.raises(ValueError):
        save_png_atomically(target,b"not-a-png")
    assert target.read_bytes() == b"old-result"

```

- [ ] **Step 2: 执行反例，确认尚缺行为的失败而不是环境错误**

Run: `python -m pytest -q tests/test_tb06_mcp_resume.py`

尚未实现的边界必须出现对应断言失败；已经满足的反例作为回归保留。缺依赖/网络误连/测试未采集先修正测试环境，不能计作业务 red。

- [ ] **Step 3: 用最小改动满足反例，完成必要接线**

`client/spark_image_tools.py` 的核心内容：

```python
import os
import tempfile
from pathlib import Path

def save_png_atomically(target, data):
    target = Path(target)
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("invalid PNG")
    target.parent.mkdir(parents=True,exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".image-",dir=target.parent)
    try:
        with os.fdopen(fd,"wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name,target)
    finally:
        if os.path.exists(name):
            os.unlink(name)
```


- [ ] 增加真实 MCP list_image_tasks 及 request_id 参数；工具说明要求先查原任务、显式取消才取消。测试从 build_server.call_tool 检查输出，不只调用内部方法。
- [ ] 公共打包函数接收 platform_assets、个人配置路径和独立输出位置；平台专属票不再改公共构建器。拒绝把恢复日志/其他 owner Key 放入包。
- [ ] 私有包中除根入口 spark_image_tools.py 外，按模块结构复制 client/request_journal.py；通过解压到独立临时目录并启动 stdio 验证导入，不能只在源码目录 PYTHONPATH 正常时通过。

- [ ] **Step 4: 按逐条验收映射验证，并记录原始证据**

| 本票验收条件 | 验证安排 |
| --- | --- |
| 1. 首次提交前持久化请求标识，提交重试复用；工具支持传入已有请求标识，明确的新意图使用新标识，不能永久按内容去重。 | lost_response_replays_after_bridge_restart，确认journal提交早于第一个POST；新增request_id可独立生成。 |
| 2. 生成、编辑及参考素材恢复均使用 owner 范围的幂等契约；提交响应丢失/MCP 重启后不出现第二次推理。 | 同一request_id的生成/编辑响应丢失后重放；真实MCP call_tool输出同一tid，后端执行一次。 |
| 3. 本地记录丢失可通过本人任务恢复工具找回；换到另一 owner 时不显示前一人的本地恢复列表，同人换 Key 保持归属。 | journal_owner_and_service_partition＋GET /v1/me换Key/换owner；本地记录丢失用列表恢复。 |
| 4. 网络、目录权限或磁盘问题只影响下载/保存；服务端 completed 结果保留，修复后重取同一图片并返回真实 MCP ImageContent。 | save_failure_does_not_delete_existing_target；网络/权限/磁盘失败后重试下载同fid，不发/tasks POST。 |
| 5. 公共桥接与打包入口支持显式个人配置和平台资源输入，不再自动把全局共享 Key 当成每个人的凭证；恢复日志不保存原始 Key。 | 解压个人包到独立目录运行stdio；审计包内仅指定owner凭证、CA、必要模块，无恢复库/其他Key。 |
| 6. 公共桥接契约在本票稳定；后续 Windows/macOS 票只接入各自平台资源，避免分别修改同一公共实现。 | T12/T13使用同一公共输出契约；本票先冻结桥接/打包的集成回归。 |

Run: `python -m pytest --collect-only -q -k tb06_mcp_resume`

Run: `python -m pytest -q -k tb06_mcp_resume`

Run: `python -m pytest -q -k "tb06 or bridge_returns_real_mcp_image_content"`


独立演示：通过真实 stdio MCP 提交后终止并重启桥接，用同一请求标识恢复；再制造不可写保存目录，修复后取得同一文件和图片内容。



- [ ] **Step 5: 文档、ADR 与证据同步**

将实际测试输出、受影响回归、失败与恢复步骤写入 docs/IMAGE-SERVICE.md；与当前计划对应的 AC 映射逐项填证据。没有实测的项保持未验收，不能只打勾。

- [ ] **Step 6: 独立提交边界 B**

提交范围：其余反例测试、守卫/兼容接线、有效文档；保持本票在前置完成后独立可演示。

```bash
git add -- client/request_journal.py client/spark_image_tools.py scripts/build_image_client_bundle.py tests/test_tb06_mcp_resume.py docs/IMAGE-SERVICE.md
git commit -m "test(image): t06 boundaries and recovery"
```

## Rollback / compatibility strategy

保留服务端任务及本地请求日志；使用同一 owner 直接查询/下载作为恢复路径。可回退公共包版本，但不得删除请求映射后自动重提。

维护过程先停止新工作并保全新增写入；对运行图片定向停止且确认后端空闲。不能回退成跨用户共享访问、关闭保护器或盲目重跑。

## Out of scope

不做 Windows/macOS 专属安装器与实际桌面验收；不改变公平排队、进度和内存策略；不新增个人配额。

## Verification environment

以下 python 指令在受支持的工程虚拟环境执行。原工作区可用 .venv/bin/python；Windows 使用对应 .venv\\Scripts\\python.exe。新测试尚未创建，未采集到测试不算通过；本轮仅编写计划，不冒充 red/green 或实机验收已执行。


## Self-review and execution handoff

- [x] 每个本票验收条件已映射到上表；父规格归属：AC-07、AC-08、AC-09、AC-10、AC-20。
- [x] 第一条失败原因与最小实现明确；状态反例为测试代码/实际演示，不只保留图。
- [x] 新签名来自共享契约，当前尚未实现的接口由明确前置/本票交付。
- [x] 边界 A/B 各自带测试与文档；回退不会丢新数据或恢复共享读取。
- [ ] 后续执行者运行 red/green、受影响回归与所需实机验收，填写实际证据后再声明完成。

本次只批准编写和发布计划，不启动产品实现。执行时由用户选择原生或子代理方式；未取得执行授权前不启动实现/部署。
