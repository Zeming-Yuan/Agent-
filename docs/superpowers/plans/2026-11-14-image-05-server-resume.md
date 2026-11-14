# T05 服务端续取：断线保留任务，后端离线仍能找回结果 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用户同步或异步提交后掉线，重连仍查询原任务；图片后端离线时也能找到自己的已有任务和已保存结果。

**Architecture:** Consumes: T04 strict owner 与 request 映射。Produces: GET /v1/tasks?status=&after= 的本人分页响应；Store.lookup_request(owner, request_key, fingerprint)->dict|None；Store.list_tasks(owner, *, status=None, after=None, limit=20)->dict；同步等待超时仍含 task_id。 先读共享执行契约并保留既有兼容边界；本票只交付确认的纵向行为，不扩展为通用重构。

**Tech Stack:** Python、FastAPI、SQLite、httpx、Pillow、stdio MCP；固定 ComfyUI 0.33.2；平台专属脚本按本票列出的操作系统执行。

**Spec:** [父规格 #1](https://github.com/Zeming-Yuan/Agent-/issues/1)；[完整规格](../../specs/2026-11-14-image-service-reliability-and-multiuser.md)；[共享执行契约](2026-11-14-image-execution-contract.md)。执行者必须同时读取三者。

**Ticket:** T05；Blocked by：T04。本人任务恢复列表和离线幂等重放必须建立在已收敛的 owner/幂等契约上。

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

1. 离线重放：已有记录不可被 readiness 拦截 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
2. 同步连接中断：不得变 cancelled → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
3. 分页游标属于别人：一致 404 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
4. 结果已删除：明确不可用，不重推理 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
5. 网关重启：保留身份，运行任务明确失败而非续算 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。

---

## File structure and interfaces

- Modify: services/gateway.py — 本人列表及已有请求先查
- Modify: services/image_routes.py — 同步等待断开不取消
- Modify: services/store.py — owner 分页与已有请求读取
- Create: tests/test_tb05_server_resume.py
- Modify: docs/IMAGE-SERVICE.md

**Consumes / Produces:** Consumes: T04 strict owner 与 request 映射。Produces: GET /v1/tasks?status=&after= 的本人分页响应；Store.lookup_request(owner, request_key, fingerprint)->dict|None；Store.list_tasks(owner, *, status=None, after=None, limit=20)->dict；同步等待超时仍含 task_id。

## Task 1: 首条用户反例与最小纵向实现

**Files:** 使用上面列出的本票实现文件；首条测试写入 `tests/test_tb05_server_resume.py`。本任务最小实现核心位于 `services/store.py`。

**Interfaces:** 消费上述输入，产出本票外部行为；新公共签名以 Architecture/共享契约为准，不另起别名。

- [ ] **Step 1: 写第一条失败测试**

```python
def test_tb05_replay_works_when_image_backend_offline(owner_env):
    backend = owner_env.new_backend()
    with owner_env.client(backend=backend, run_worker=True) as c:
        first = owner_env.submit(c, "A", request_key="keep")
        tid = first.json()["id"]
        owner_env.wait_task(c, tid, "A", lambda t: t["status"] == "completed")
        backend.offline.set()
        replay = owner_env.submit(c, "A", request_key="keep")
        assert replay.status_code == 202
        assert replay.json()["id"] == tid
        listing = c.get("/v1/tasks", headers=owner_env.auth("A")).json()
        assert tid in [t["id"] for t in listing["data"]]
        fid = replay.json()["result"]["file_id"]
        assert c.get(f"/v1/files/{fid}/content", headers=owner_env.auth("A")).status_code == 200
        assert len(backend.jobs) == 1
```

- [ ] **Step 2: 运行并确认预期失败原因**

Run: `python -m pytest -q tests/test_tb05_server_resume.py`

Expected: 当前 ensure_image_available 先于幂等读取，离线重放返回 503；GET 本人任务列表也尚不存在。不能用 backend 假成功使第一条测试变绿。 这是执行前预期，不是本轮已取得的测试结果。

- [ ] **Step 3: 最小实现，先让这一条完整路径可工作**

在 `services/store.py` 应用以下核心，按该文件职责接入真实路由/存储，不替换真实业务层为 mock：

```python
from fastapi import HTTPException

def lookup_request(store, owner, request_key, fingerprint):
    if not request_key:
        return None
    with store.connect() as db:
        row = db.execute("""SELECT task_id,fingerprint FROM task_requests
            WHERE owner=? AND request_key=?""", (owner, request_key)).fetchone()
    if row is None:
        return None
    if row["fingerprint"] != fingerprint:
        raise HTTPException(409, "Idempotency key reused with different request")
    return store.task(row["task_id"], owner=owner)
```

- [ ] 生成规范业务指纹后先 lookup_request；已命中直接返回，不探测图片后端。新任务才检查 readiness，再在事务内二次查幂等并创建，避免检查间竞争。
- [ ] 分页按本人稳定入队序读取，after 先查本人访问权；limit 限定 1..100，非法筛选 422。查询不依赖后端或 worker 活跃。
- [ ] 同步等待中的 CancelledError/断线只结束等待，不更新 status、不 active.cancel；显式取消仍由取消接口独立处理。

- [ ] **Step 4: 运行首条测试和受影响既有回归**

Run: `python -m pytest -q tests/test_tb05_server_resume.py`

Run: `python -m pytest -q -k "tb05 or image_admission or unknown_submit_outcome or restart_marks_running_failed"`

Expected: 所选测试采集非零、断言通过；任何 HTTP/后端替身错误都解释，不能用 deselect/skip 当完成。

- [ ] **Step 5: 同步文档/ADR**

- [ ] docs/IMAGE-SERVICE.md：同步断线/超时恢复、本人分页及已删结果
- [ ] OPERATIONS.md：离线仍可取已完成结果，重启不承诺 GPU 续算

- [ ] **Step 6: 独立提交边界 A**

提交范围：首个外部行为、测试和必要文档；不夹带下一票迁移。Git checkout 中选择实际改动文件后执行：

```bash
python - <<'PY'
from pathlib import Path
import subprocess
candidates = ["services/gateway.py","services/image_routes.py","services/store.py","tests/test_tb05_server_resume.py","docs/IMAGE-SERVICE.md"]
paths = [p for p in candidates if Path(p).is_file()]
subprocess.run(["git", "add", "--", *paths], check=True)
PY
git commit -m "feat(image): t05 vertical core"
```

非 Git 产品目录使用逐任务审查快照与 SHA256 变更清单；不在此处初始化或推送整个工作区。

## Task 2: 状态反例、完整验收与恢复边界

**Files:** `tests/test_tb05_server_resume.py`、上面列出的责任模块、文档；新增核心位于 `tests/test_tb05_server_resume.py`。

**Interfaces:** 延续 Task 1 的命名/字段/返回值；所有异常路径仍以 owner 隔离和同一任务身份为边界。

- [ ] **Step 1: 把 Review Focus 反例写成具体测试**

以下代码与 Task 1 的测试置于同一测试模块，保留该模块已经定义的 import/帮助函数；不是只画状态图：

```python
def test_tb05_other_owner_cursor_is_not_visible(owner_env):
    with owner_env.client() as c:
        tid = owner_env.submit(c, "A").json()["id"]
        r = c.get("/v1/tasks", params={"after":tid}, headers=owner_env.auth("B"))
        assert r.status_code == 404

def test_tb05_new_work_offline_is_rejected(owner_env):
    backend = owner_env.new_backend()
    backend.offline.set()
    with owner_env.client(backend=backend) as c:
        assert owner_env.submit(c, "A", request_key="new").status_code == 503
        assert c.get("/v1/tasks", headers=owner_env.auth("A")).json()["data"] == []

def test_tb05_completed_result_can_be_deleted_without_rerun(owner_env):
    backend = owner_env.new_backend()
    with owner_env.client(backend=backend, run_worker=True) as c:
        tid = owner_env.submit(c, "A", request_key="delete").json()["id"]
        done = owner_env.wait_task(c, tid, "A", lambda t: t["status"] == "completed")
        fid = done["result"]["file_id"]
        assert c.delete("/v1/files/"+fid, headers=owner_env.auth("A")).status_code == 200
        assert owner_env.submit(c, "A", request_key="delete").json()["id"] == tid
        assert c.get("/v1/files/"+fid+"/content", headers=owner_env.auth("A")).status_code == 404
        assert len(backend.jobs) == 1

def test_tb05_sync_disconnect_does_not_cancel_work(owner_env):
    backend = owner_env.new_backend(hold=True)
    with owner_env.client(backend=backend,run_worker=True) as c:
        c.portal.call(disconnecting_asgi_request,c.app,owner_env.auth("A"),
            {"model":"spark-image","prompt":"disconnect"},backend.started)
        rows = c.get("/v1/tasks",headers=owner_env.auth("A")).json()["data"]
        assert len(rows) == 1
        assert rows[0]["status"] in ("queued","running")
        backend.finish.set()
        done = owner_env.wait_task(c,rows[0]["id"],"A",lambda t:t["status"]=="completed")
        assert done["status"] == "completed"

```

- [ ] **Step 2: 执行反例，确认尚缺行为的失败而不是环境错误**

Run: `python -m pytest -q tests/test_tb05_server_resume.py`

尚未实现的边界必须出现对应断言失败；已经满足的反例作为回归保留。缺依赖/网络误连/测试未采集先修正测试环境，不能计作业务 red。

- [ ] **Step 3: 用最小改动满足反例，完成必要接线**

`tests/test_tb05_server_resume.py` 的核心内容：

```python
import asyncio
import json

async def disconnecting_asgi_request(app, headers, body, started):
    payload = json.dumps(body).encode()
    first = True
    sent = []
    async def receive():
        nonlocal first
        if first:
            first = False
            return {"type":"http.request", "body":payload, "more_body":False}
        await asyncio.to_thread(started.wait, 2.0)
        return {"type":"http.disconnect"}
    async def send(message):
        sent.append(message)
    scope = {"type":"http", "asgi":{"version":"3.0"}, "http_version":"1.1",
        "method":"POST", "scheme":"http", "path":"/v1/images/generations",
        "raw_path":b"/v1/images/generations", "query_string":b"",
        "headers":[(k.lower().encode(),v.encode()) for k,v in headers.items()] +
                  [(b"content-type",b"application/json")],
        "client":("test",1), "server":("testserver",80), "root_path":""}
    await app(scope, receive, send)
    return sent
```


另在指定上下文应用以下实际差异：

```diff
--- services/image_routes.py
+++ services/image_routes.py
@@ wait_result CancelledError handling
         except asyncio.CancelledError:
-            store.update(tid,status='cancelled')
-            if tid in active: active[tid].cancel()
             raise
```

- [ ] 把 disconnecting_asgi_request 放入本票测试，在 TestClient 生命周期内用 c.portal.call 运行；断开后通过本人列表找到同一 ID，backend.finish.set 后正常取图；对 sync generate/edit 各跑一例。
- [ ] 重启用同一持久 root 新建应用；queued 保留、running 明确 failed、completed 结果仍可读；测试检查任务/结果，不 mock recover。

- [ ] **Step 4: 按逐条验收映射验证，并记录原始证据**

| 本票验收条件 | 验证安排 |
| --- | --- |
| 1. 同步等待断开、查询超时和异步响应丢失不自动取消已接纳任务；同步等待到期保留 task_id 恢复信息。 | sync_disconnect_does_not_cancel_work；同步generate/edit各通过ASGI disconnect复现，不取消worker。 |
| 2. 同人幂等重放先返回已有任务，再判断是否能创建新工作；后端离线不阻止读取/重放已有任务和下载已保存图片。 | replay_works_when_image_backend_offline：已有tid、下载成功且后端jobs=1。 |
| 3. 提供只列本人任务的分页与状态筛选；网络响应丢失后可找回任务，未建立归属或跨人列表均不泄露信息。 | 本人分页/状态/limit测试及other_owner_cursor_is_not_visible；A/B列表无交叉。 |
| 4. 后端不可用时真正的新请求仍 503 且不新建任务；同一请求只发生一次推理。 | new_work_offline_is_rejected，列表仍为空；重放不建新工作。 |
| 5. 网关重启保留排队/结果，运行中任务按既有策略明确失败；已删除结果报不可用，不重跑模型。 | 同root重建app，queued保留/running失败/completed可取；已删结果404且jobs不增加。 |

Run: `python -m pytest --collect-only -q -k tb05_server_resume`

Run: `python -m pytest -q -k tb05_server_resume`

Run: `python -m pytest -q -k "tb05 or image_admission or unknown_submit_outcome or restart_marks_running_failed"`


独立演示：接纳任务后断开 HTTP 等待，完成后重连取图；停用图片后端后再列出本人任务、重放原请求并下载该结果。



- [ ] **Step 5: 文档、ADR 与证据同步**

将实际测试输出、受影响回归、失败与恢复步骤写入 docs/IMAGE-SERVICE.md；与当前计划对应的 AC 映射逐项填证据。没有实测的项保持未验收，不能只打勾。

- [ ] **Step 6: 独立提交边界 B**

提交范围：其余反例测试、守卫/兼容接线、有效文档；保持本票在前置完成后独立可演示。

```bash
python - <<'PY'
from pathlib import Path
import subprocess
candidates = ["services/gateway.py","services/image_routes.py","services/store.py","tests/test_tb05_server_resume.py","docs/IMAGE-SERVICE.md"]
paths = [p for p in candidates if Path(p).is_file()]
subprocess.run(["git", "add", "--", *paths], check=True)
PY
git commit -m "test(image): t05 boundaries and recovery"
```

## Rollback / compatibility strategy

保留新增任务与幂等映射，暂停新接单后回退到 owner 感知版本；已接纳任务仍可查询取图。不得通过恢复“断线即取消”处理不确定任务。

维护过程先停止新工作并保全新增写入；对运行图片定向停止且确认后端空闲。不能回退成跨用户共享访问、关闭保护器或盲目重跑。

## Out of scope

不做客户端自动请求编号/本地日志；不改取消清理、真实进度或资源准入；不保证 GPU 断点续算。

## Verification environment

以下 python 指令在受支持的工程虚拟环境执行。原工作区可用 .venv/bin/python；Windows 使用对应 .venv\\Scripts\\python.exe。新测试尚未创建，未采集到测试不算通过；本轮仅编写计划，不冒充 red/green 或实机验收已执行。


## Self-review and execution handoff

- [x] 每个本票验收条件已映射到上表；父规格归属：AC-08、AC-09、AC-13、AC-17。
- [x] 第一条失败原因与最小实现明确；状态反例为测试代码/实际演示，不只保留图。
- [x] 新签名来自共享契约，当前尚未实现的接口由明确前置/本票交付。
- [x] 边界 A/B 各自带测试与文档；回退不会丢新数据或恢复共享读取。
- [ ] 后续执行者运行 red/green、受影响回归与所需实机验收，填写实际证据后再声明完成。

本次只批准编写和发布计划，不启动产品实现。执行时由用户选择原生或子代理方式；未取得执行授权前不启动实现/部署。
