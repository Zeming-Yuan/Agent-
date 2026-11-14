# T07 真实阶段与取消：确认保存或停止后才报告终态 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用户在工具中看到真实的加载、生成、保存与取消清理阶段；取消自己的任务后，确认后台停止才显示完成取消并启动下一单。

**Architecture:** Consumes: T06 的稳定任务恢复、owner 和桥接输出。Produces: task_runtime 字段、Store.transition 的执行契约；apply_event(task:dict,event:dict,*,backend_stopped=False,result_saved=False)->dict（services.task_lifecycle）。status 保持既有五态，stage 与 step/steps 为额外字段。 ComfyEventStream(url:str, client_id:str) 的 async events() 产出原始事件字典；normalize_event(event:dict, prompt_id:str, active_node:str|None)->dict|None 只接收本任务事件。 create_app 新增 event_stream_factory 参数，默认真实连接器；测试注入 ImageBackend.events 异步消息迭代器。 先读共享执行契约并保留既有兼容边界；本票只交付确认的纵向行为，不扩展为通用重构。

**Tech Stack:** Python、FastAPI、SQLite、httpx、Pillow、stdio MCP；固定 ComfyUI 0.33.2；平台专属脚本按本票列出的操作系统执行。

**Spec:** [父规格 #1](https://github.com/Zeming-Yuan/Agent-/issues/1)；[完整规格](../../specs/2026-11-14-image-service-reliability-and-multiuser.md)；[共享执行契约](2026-11-14-image-execution-contract.md)。执行者必须同时读取三者。

**Ticket:** T07；Blocked by：T06。与 T06 共用桥接及任务终态；按用户要求串行整合，避免恢复与取消语义同时改写。

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

1. 取消后迟到成功：不能 completed 覆盖 cancelled → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
2. 提交未返回即取消：等待确认，定向停止 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
3. 保存未持久化：不能提前 completed → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
4. 重复/乱序事件：阶段与终态不倒退 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
5. 取消失败/结果未知：阻塞调度并保持可诊断 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。

---

## File structure and interfaces

- Create: services/task_lifecycle.py — 状态事件与终态规则
- Create: services/comfy_events.py — 固定版本 /ws 事件归属及节点阶段映射
- Modify: services/store.py — task_runtime 旁表和 CAS transition
- Modify: services/images.py / services/image_routes.py / services/gateway.py — 阶段与取消清理
- Modify: client/spark_image_tools.py — 真实阶段输出
- Create: tests/test_tb07_lifecycle.py
- Modify: docs/IMAGE-SERVICE.md
- Modify: deploy/gateway-requirements.lock — 固定 websockets==16.0（采用现有图片运行时已锁版本）
- Modify: tests/conftest.py — 注入受控事件流，禁止测试连接真实后端 WebSocket

- Modify: OPERATIONS.md — 本票文档/ADR/实际测量记录同步

**Consumes / Produces:** Consumes: T06 的稳定任务恢复、owner 和桥接输出。Produces: task_runtime 字段、Store.transition 的执行契约；apply_event(task:dict,event:dict,*,backend_stopped=False,result_saved=False)->dict（services.task_lifecycle）。status 保持既有五态，stage 与 step/steps 为额外字段。 ComfyEventStream(url:str, client_id:str) 的 async events() 产出原始事件字典；normalize_event(event:dict, prompt_id:str, active_node:str|None)->dict|None 只接收本任务事件。 create_app 新增 event_stream_factory 参数，默认真实连接器；测试注入 ImageBackend.events 异步消息迭代器。

## Task 1: 首条用户反例与最小纵向实现

**Files:** 使用上面列出的本票实现文件；首条测试写入 `tests/test_tb07_lifecycle.py`。本任务最小实现核心位于 `services/task_lifecycle.py`。

**Interfaces:** 消费上述输入，产出本票外部行为；新公共签名以 Architecture/共享契约为准，不另起别名。

- [ ] **Step 1: 写第一条失败测试**

```python
def test_tb07_cancel_waits_until_backend_stopped(owner_env):
    backend = owner_env.new_backend(hold=True, hold_stop=True)
    with owner_env.client(backend=backend, run_worker=True) as c:
        tid = owner_env.submit(c,"A").json()["id"]
        assert backend.started.wait(2)
        r = c.post("/v1/tasks/"+tid+"/cancel",headers=owner_env.auth("A"))
        assert r.json()["status"] == "running"
        assert r.json()["stage"] == "cancelling"
        backend.release_stop.set()
        done = owner_env.wait_task(c,tid,"A",lambda t:t["status"]=="cancelled")
        assert done["status"] == "cancelled"
```

- [ ] **Step 2: 运行并确认预期失败原因**

Run: `python -m pytest -q tests/test_tb07_lifecycle.py`

Expected: 当前取消接口先写 cancelled，清理尚未结束即返回；因此期望 running/cancelling 会失败。不能把后端 mock 提前清空来消除该反例。 这是执行前预期，不是本轮已取得的测试结果。

- [ ] **Step 3: 最小实现，先让这一条完整路径可工作**

在 `services/task_lifecycle.py` 应用以下核心，按该文件职责接入真实路由/存储，不替换真实业务层为 mock：

```python
TERMINAL = {"completed","failed","cancelled"}

def apply_event(task, event, *, backend_stopped=False, result_saved=False):
    out = dict(task)
    if task["status"] in TERMINAL or event["seq"] <= task.get("stage_seq",0):
        return out
    kind = event["type"]
    if kind == "cancel_requested":
        out["cancel_requested"] = True
        if task["status"] == "queued":
            out.update(status="cancelled",stage="cancelled")
        else:
            out.update(status="running",stage="cancelling")
    elif kind == "backend_stopped" and task.get("cancel_requested"):
        if backend_stopped:
            out.update(status="cancelled",stage="cancelled")
    elif kind == "save_complete":
        if result_saved and not task.get("cancel_requested"):
            out.update(status="completed",stage="completed",result=event["result"])
    elif kind == "stage" and not task.get("cancel_requested"):
        out["stage"] = event["stage"]
    out["stage_seq"] = event["seq"]
    return out
```

- [ ] 在 /prompt 前连接 /ws?clientId=<task_id>；固定 websockets==16.0（图片锁文件已存在同版本），连接器隔离在 services/comfy_events.py，单测注入消息迭代器。executing/progress/execution_error 按规范后端 prompt_id 和当前 client_id 关联；无可证明归属事件只保留最后阶段，不猜测。
- [ ] 在现有图片固定节点执行事件上映射 loading/generating/saving；没有有效采样总量时 step/steps 为空，不把旧 progress=.1 展示为百分比。
- [ ] task_runtime 旁表与 tasks 的 status/result 更新在一个 BEGIN IMMEDIATE 中 CAS，补齐 stage_started_at、stage_updated_at、blocked_reason；相同阶段不重置开始时间，输出以 seq 排序。
- [ ] 运行取消只登记请求并 active.cancel；shield 后端提交结果确认、定向停止与清理，结束前 worker 不选择下一单。保存成功也必须经过 finally 清理再释放控制权。

- [ ] **Step 4: 运行首条测试和受影响既有回归**

Run: `python -m pytest -q tests/test_tb07_lifecycle.py`

Run: `python -m pytest -q -k "tb07 or cancelling_running_image or unknown_submit_outcome or image_submission_uses_uuid"`

Expected: 所选测试采集非零、断言通过；任何 HTTP/后端替身错误都解释，不能用 deselect/skip 当完成。

- [ ] **Step 5: 同步文档/ADR**

- [ ] docs/IMAGE-SERVICE.md：stage/step/seq、终态与显式取消语义
- [ ] OPERATIONS.md：未知提交/停止失败的隔离与人工恢复

- [ ] **Step 6: 独立提交边界 A**

提交范围：首个外部行为、测试和必要文档；不夹带下一票迁移。Git checkout 中选择实际改动文件后执行：

```bash
python - <<'PY'
from pathlib import Path
import subprocess
candidates = ["services/task_lifecycle.py","services/comfy_events.py","services/store.py","services/images.py","services/image_routes.py","services/gateway.py","client/spark_image_tools.py","tests/test_tb07_lifecycle.py","docs/IMAGE-SERVICE.md","deploy/gateway-requirements.lock","tests/conftest.py","OPERATIONS.md"]
paths = [p for p in candidates if Path(p).is_file()]
subprocess.run(["git", "add", "--", *paths], check=True)
PY
git commit -m "feat(image): t07 vertical core"
```

非 Git 产品目录使用逐任务审查快照与 SHA256 变更清单；不在此处初始化或推送整个工作区。

## Task 2: 状态反例、完整验收与恢复边界

**Files:** `tests/test_tb07_lifecycle.py`、上面列出的责任模块、文档；新增核心位于 `services/store.py`。

**Interfaces:** 延续 Task 1 的命名/字段/返回值；所有异常路径仍以 owner 隔离和同一任务身份为边界。

- [ ] **Step 1: 把 Review Focus 反例写成具体测试**

以下代码与 Task 1 的测试置于同一测试模块，保留该模块已经定义的 import/帮助函数；不是只画状态图：

```python
import pytest
from services.task_lifecycle import apply_event

@pytest.mark.parametrize("status,cancelled,event,stopped,saved,expected",[
    ("cancelled",True,{"type":"save_complete","seq":2,"result":{}},True,True,"cancelled"),
    ("running",True,{"type":"backend_stopped","seq":2},False,False,"running"),
    ("running",True,{"type":"backend_stopped","seq":2},True,False,"cancelled"),
    ("running",False,{"type":"save_complete","seq":2,"result":{}},False,False,"running"),
    ("running",False,{"type":"stage","seq":0,"stage":"loading"},False,False,"running"),
])
def test_tb07_state_counterexamples(status,cancelled,event,stopped,saved,expected):
    task = {"status":status,"stage":"saving","stage_seq":1,"cancel_requested":cancelled}
    out = apply_event(task,event,backend_stopped=stopped,result_saved=saved)
    assert out["status"] == expected
    if event["seq"] <= task["stage_seq"]:
        assert out == task
```

- [ ] **Step 2: 执行反例，确认尚缺行为的失败而不是环境错误**

Run: `python -m pytest -q tests/test_tb07_lifecycle.py`

尚未实现的边界必须出现对应断言失败；已经满足的反例作为回归保留。缺依赖/网络误连/测试未采集先修正测试环境，不能计作业务 red。

- [ ] **Step 3: 用最小改动满足反例，完成必要接线**

`services/store.py` 的核心内容：

```python
import json
from fastapi import HTTPException

def transition_tx(db, tid, *, status, stage, expected_seq, result=None, error=None):
    row = db.execute("SELECT status FROM tasks WHERE id=?", (tid,)).fetchone()
    if row is None:
        raise HTTPException(404,"Object not found")
    if row["status"] in {"completed","failed","cancelled"}:
        return False
    changed = db.execute("""UPDATE task_runtime SET stage=?,stage_seq=stage_seq+1
        WHERE task_id=? AND stage_seq=?""", (stage,tid,expected_seq)).rowcount
    if not changed:
        return False
    db.execute("UPDATE tasks SET status=?,result=?,error=? WHERE id=?",
               (status,json.dumps(result) if result is not None else None,error,tid))
    return True
```


- [ ] 把 queued→cancelled、running→cancelling→cancelled、saving→completed，以及 unknown_submit→failed/health degraded 的反例加入真实 HTTP/后端测试；模型图不是验收产物。
- [ ] 复用现有 test_image_cancel/test_image_uncertain，增加下一单 /prompt 在 release_stop 前未发生的后端计数断言。
- [ ] 为 owner_env 明确注入事件流工厂；默认夹具 events_to_emit=[]，async events() 逐条 yield 已安排消息。真实 WebSocket 连接器在集成协议测试中单独启动本地假 WS 服务验证，不让普通单测访问真实端口。

- [ ] **Step 4: 按逐条验收映射验证，并记录原始证据**

| 本票验收条件 | 验证安排 |
| --- | --- |
| 1. 保留既有生命周期状态，新增正交阶段、阶段开始时间、最近有效更新时间与原因；没有可靠进度时显示阶段与等待时间，不伪造百分比或 ETA。 | 真实MCP阶段输出与late/duplicate seq反例；无step总量不显示百分比。 |
| 2. 可靠采样步数归属正确任务，仅表示生成阶段；迟到/重复/重连事件不使阶段倒退或覆盖终态。 | state_counterexamples参数化＋prompt_id归属事件测试，重连旧事件不覆盖。 |
| 3. 取消排队任务可直接收敛；运行中先显示取消清理，定向停止并确认后端不持有任务、清理完成后才报告 cancelled。 | cancel_waits_until_backend_stopped，释放stop事件前保持running/cancelling。 |
| 4. 串行控制权覆盖上一单停止与清理；下一单不与孤儿工作并行。完成/取消竞态只产生一个稳定终态。 | 现有取消/未知提交测试扩展下一单/prompt计数；完成/取消竞争只一终态。 |
| 5. 图片完整保存且可鉴权读取后才 completed；保存失败报告错误，不提前成功；查询/工具退出不被当作取消。 | save_not_durable反例＋真实文件提交失败；GET结果可读取后才completed。 |
| 6. 提交结果未知或停止失败时健康降级、新工作 503；已接纳任务和结果仍可查询，不尝试盲目重跑。 | unknown_submit_outcome回归：health503、新工作拒绝、旧记录可查询。 |

Run: `python -m pytest --collect-only -q -k tb07_lifecycle`

Run: `python -m pytest -q -k tb07_lifecycle`

Run: `python -m pytest -q -k "tb07 or cancelling_running_image or unknown_submit_outcome or image_submission_uses_uuid"`


独立演示：用慢加载/慢保存后端通过 stdio MCP 观察阶段；在提交响应未返回时取消，证明下一单等到旧工作实际停止再启动。



- [ ] **Step 5: 文档、ADR 与证据同步**

将实际测试输出、受影响回归、失败与恢复步骤写入 docs/IMAGE-SERVICE.md；与当前计划对应的 AC 映射逐项填证据。没有实测的项保持未验收，不能只打勾。

- [ ] **Step 6: 独立提交边界 B**

提交范围：其余反例测试、守卫/兼容接线、有效文档；保持本票在前置完成后独立可演示。

```bash
python - <<'PY'
from pathlib import Path
import subprocess
candidates = ["services/task_lifecycle.py","services/comfy_events.py","services/store.py","services/images.py","services/image_routes.py","services/gateway.py","client/spark_image_tools.py","tests/test_tb07_lifecycle.py","docs/IMAGE-SERVICE.md","deploy/gateway-requirements.lock","tests/conftest.py","OPERATIONS.md"]
paths = [p for p in candidates if Path(p).is_file()]
subprocess.run(["git", "add", "--", *paths], check=True)
PY
git commit -m "test(image): t07 boundaries and recovery"
```

## Rollback / compatibility strategy

可关闭新阶段展示并保留持久事件；出现异常时暂停图片调度、定向清理并人工确认恢复。不能回退到提前 cancelled 或放行孤儿工作。

维护过程先停止新工作并保全新增写入；对运行图片定向停止且确认后端空闲。不能回退成跨用户共享访问、关闭保护器或盲目重跑。

## Out of scope

不承诺模型已真正释放；不做按任务内存准入或公平队列数量；不新增界面或个人配额。

## Verification environment

以下 python 指令在受支持的工程虚拟环境执行。原工作区可用 .venv/bin/python；Windows 使用对应 .venv\\Scripts\\python.exe。新测试尚未创建，未采集到测试不算通过；本轮仅编写计划，不冒充 red/green 或实机验收已执行。


## Self-review and execution handoff

- [x] 每个本票验收条件已映射到上表；父规格归属：AC-06、AC-16、AC-17。
- [x] 第一条失败原因与最小实现明确；状态反例为测试代码/实际演示，不只保留图。
- [x] 新签名来自共享契约，当前尚未实现的接口由明确前置/本票交付。
- [x] 边界 A/B 各自带测试与文档；回退不会丢新数据或恢复共享读取。
- [ ] 后续执行者运行 red/green、受影响回归与所需实机验收，填写实际证据后再声明完成。

本次只批准编写和发布计划，不启动产品实现。执行时由用户选择原生或子代理方式；未取得执行授权前不启动实现/部署。

## 固定版本事件适配器的最小内容

写入 services/comfy_events.py；字段已核对当前固定后端的 executing/progress 事件。断流只终止进度观察，不取消图片任务。

```python
import json
from urllib.parse import urlencode, urlsplit, urlunsplit
from websockets.asyncio.client import connect

class ComfyEventStream:
    def __init__(self,url,client_id):
        base=urlsplit(url)
        scheme={"http":"ws","https":"wss","ws":"ws","wss":"wss"}.get(base.scheme)
        if scheme is None: raise ValueError("HTTP(S)/WS(S) backend URL required")
        self.url=urlunsplit((scheme,base.netloc,base.path.rstrip("/")+"/ws",
                             urlencode({"clientId":client_id}),""))
    async def events(self):
        async with connect(self.url,open_timeout=5,close_timeout=5) as socket:
            async for raw in socket:
                if isinstance(raw,str):
                    event=json.loads(raw)
                    if isinstance(event,dict):
                        yield event

def normalize_event(event,prompt_id,active_node):
    data=event.get("data",{})
    if data.get("prompt_id") != prompt_id:
        return None
    kind=event.get("type")
    if kind=="executing":
        node=data.get("node")
        if node is None: return None
        stage="saving" if str(node)=="9" else "generating" if str(node) in {"7","8"} else "loading"
        return {"stage":stage,"node":str(node)}
    if kind=="progress" and str(data.get("node",active_node))=="7":
        value,total=data.get("value"),data.get("max")
        if type(value) is int and type(total) is int and 0<=value<=total and total>0:
            return {"stage":"generating","step":value,"steps":total,"node":"7"}
    return None
```

```python
from services.comfy_events import normalize_event

def test_tb07_other_prompt_and_invalid_steps_are_ignored():
    assert normalize_event({"type":"executing","data":{"prompt_id":"other","node":"9"}},"mine",None) is None
    assert normalize_event({"type":"progress","data":{"prompt_id":"mine","node":"7","value":5,"max":4}},"mine","7") is None
    assert normalize_event({"type":"progress","data":{"prompt_id":"mine","node":"7","value":2,"max":4}},"mine","7")["step"] == 2
```
