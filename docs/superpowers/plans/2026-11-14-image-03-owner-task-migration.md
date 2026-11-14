# T03 迁移任务链路：个人 Key 可生成、编辑、取图与轮换 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 受控环境中两个人各自提交并完成图片任务，只能访问自己的任务与结果；个人 Key 可发放、撤销和轮换。

**Architecture:** Consumes: T02 文件隔离与 T01 KeyRegistry。Produces: Store.task(tid,*,owner)、Store.worker_task(tid)、Store.submit(kind,fid,options,idem,*,owner)；GET /v1/me；task_requests 联合主键；CLI issue/revoke；保持原模型参数与结果形状。 先读共享执行契约并保留既有兼容边界；本票只交付确认的纵向行为，不扩展为通用重构。

**Tech Stack:** Python、FastAPI、SQLite、httpx、Pillow、stdio MCP；固定 ComfyUI 0.33.2；平台专属脚本按本票列出的操作系统执行。

**Spec:** [父规格 #1](https://github.com/Zeming-Yuan/Agent-/issues/1)；[完整规格](../../specs/2026-11-14-image-service-reliability-and-multiuser.md)；[共享执行契约](2026-11-14-image-execution-contract.md)。执行者必须同时读取三者。

**Ticket:** T03；Blocked by：T02。任务归属和结果取回必须基于 T02 已隔离的素材链路；继续串行迁移共享任务库。

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

1. 同 owner 同键不同内容：409 而非新推理 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
2. 跨 owner 同键：独立任务与结果 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
3. 随机参考图 ID 改变：相同素材重试仍命中 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
4. Key 撤销/轮换：撤销 401、新 Key 保留 owner → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
5. 媒体 worker/结果保存：不能漏传 owner 形成共享漏洞 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。

---

## File structure and interfaces

- Modify: services/store.py — 本人任务、worker_task、scoped submit
- Modify: services/gateway.py / services/image_routes.py — owner 与幂等接入
- Modify: services/images.py / services/media.py — 结果与素材 owner 一致
- Modify: services/identity.py — 私有文件发放/撤销 CLI
- Create: tests/test_tb03_owner_tasks.py
- Modify: docs/IMAGE-SERVICE.md / OPERATIONS.md

**Consumes / Produces:** Consumes: T02 文件隔离与 T01 KeyRegistry。Produces: Store.task(tid,*,owner)、Store.worker_task(tid)、Store.submit(kind,fid,options,idem,*,owner)；GET /v1/me；task_requests 联合主键；CLI issue/revoke；保持原模型参数与结果形状。

## Task 1: 首条用户反例与最小纵向实现

**Files:** 使用上面列出的本票实现文件；首条测试写入 `tests/test_tb03_owner_tasks.py`。本任务最小实现核心位于 `services/store.py`。

**Interfaces:** 消费上述输入，产出本票外部行为；新公共签名以 Architecture/共享契约为准，不另起别名。

- [ ] **Step 1: 写第一条失败测试**

```python
def test_tb03_same_request_key_does_not_cross_owners(owner_env):
    with owner_env.client() as c:
        a = owner_env.submit(c, "A", request_key="same").json()
        b = owner_env.submit(c, "B", request_key="same").json()
        assert a["id"] != b["id"]
        assert c.get("/v1/tasks/" + a["id"], headers=owner_env.auth("B")).status_code == 404
        again = owner_env.submit(c, "A", request_key="same").json()
        assert again["id"] == a["id"]
```

- [ ] **Step 2: 运行并确认预期失败原因**

Run: `python -m pytest -q tests/test_tb03_owner_tasks.py`

Expected: T02 后任务仍使用全局 idem UNIQUE / 全局查询；A/B 的相同请求键会复用同一任务或返回冲突，无法得到两个独立 ID。 这是执行前预期，不是本轮已取得的测试结果。

- [ ] **Step 3: 最小实现，先让这一条完整路径可工作**

在 `services/store.py` 应用以下核心，按该文件职责接入真实路由/存储，不替换真实业务层为 mock：

```python
import hashlib
import json

def business_fingerprint(kind, options, material_digests):
    canonical = dict(options)
    canonical.pop("image_ids", None)
    canonical.pop("foreground_file_id", None)
    payload = [kind, canonical, list(material_digests)]
    return hashlib.sha256(json.dumps(payload, sort_keys=True,
        ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
```

- [ ] 创建 task_requests 旁表；在 BEGIN IMMEDIATE 内校验素材归属、查联合幂等映射、检查全局容量、插入任务和归属；重复请求先返回，非 legacy 的旧 idem 列写 NULL。
- [ ] 对素材用打开文件流的 SHA256 生成 material_digests，保持参考图顺序；同步 multipart 和异步引用走相同指纹规则。
- [ ] 用户 HTTP 任务路径全部传 owner；worker_task 只供可信 worker，返回 owner 后传给所有结果落库、前景读取和临时清理调用。

- [ ] **Step 4: 运行首条测试和受影响既有回归**

Run: `python -m pytest -q tests/test_tb03_owner_tasks.py`

Run: `python -m pytest -q -k "tb03 or image_task_validation_idempotency or edit_retry_with_idempotency or auth_rejections"`

Expected: 所选测试采集非零、断言通过；任何 HTTP/后端替身错误都解释，不能用 deselect/skip 当完成。

- [ ] **Step 5: 同步文档/ADR**

- [ ] OPERATIONS.md：Key 发放、撤销、轮换和遗失恢复
- [ ] docs/IMAGE-SERVICE.md：owner 范围幂等与 GET /v1/me
- [ ] docs/adr/0001-owner-scoped-storage.md：记录全部调用方迁移清单

- [ ] **Step 6: 独立提交边界 A**

提交范围：首个外部行为、测试和必要文档；不夹带下一票迁移。Git checkout 中选择实际改动文件后执行：

```bash
git add -- services/store.py services/gateway.py services/image_routes.py services/images.py services/media.py services/identity.py tests/test_tb03_owner_tasks.py docs/IMAGE-SERVICE.md OPERATIONS.md
git commit -m "feat(image): t03 vertical core"
```

非 Git 产品目录使用逐任务审查快照与 SHA256 变更清单；不在此处初始化或推送整个工作区。

## Task 2: 状态反例、完整验收与恢复边界

**Files:** `tests/test_tb03_owner_tasks.py`、上面列出的责任模块、文档；新增核心位于 `services/identity.py`。

**Interfaces:** 延续 Task 1 的命名/字段/返回值；所有异常路径仍以 owner 隔离和同一任务身份为边界。

- [ ] **Step 1: 把 Review Focus 反例写成具体测试**

以下代码与 Task 1 的测试置于同一测试模块，保留该模块已经定义的 import/帮助函数；不是只画状态图：

```python
def test_tb03_changed_payload_conflicts(owner_env):
    with owner_env.client() as c:
        first = owner_env.submit(c, "A", request_key="one", prompt="red")
        assert first.status_code == 202
        assert owner_env.submit(c, "A", request_key="one", prompt="blue").status_code == 409

def test_tb03_rotated_key_retains_owner(owner_env):
    with owner_env.client() as c:
        tid = owner_env.submit(c, "A").json()["id"]
        new_key = owner_env.registry.issue("A")
        old = owner_env.registry.resolve(owner_env.keys["A"])
        owner_env.registry.revoke(old.key_id)
        assert c.get("/v1/tasks/"+tid, headers=owner_env.auth("A")).status_code == 401
        assert c.get("/v1/tasks/"+tid, headers={"Authorization":"Bearer "+new_key}).status_code == 200

def test_tb03_different_upload_ids_same_material_replay(owner_env):
    with owner_env.client() as c:
        a = owner_env.upload(c, "A")
        b = owner_env.upload(c, "A")
        one = owner_env.submit(c, "A", kind="image_edit", request_key="edit", image_ids=[a])
        two = owner_env.submit(c, "A", kind="image_edit", request_key="edit", image_ids=[b])
        assert one.status_code == two.status_code == 202
        assert one.json()["id"] == two.json()["id"]

def test_tb03_worker_result_stays_private(owner_env):
    backend = owner_env.new_backend()
    with owner_env.client(backend=backend,run_worker=True) as c:
        fid = owner_env.upload(c,"A")
        tid = owner_env.submit(c,"A",kind="image_edit",image_ids=[fid]).json()["id"]
        done = owner_env.wait_task(c,tid,"A",lambda t:t["status"]=="completed")
        result = done["result"]["file_id"]
        assert c.get("/v1/files/"+result+"/content",headers=owner_env.auth("A")).status_code == 200
        assert c.get("/v1/files/"+result+"/content",headers=owner_env.auth("B")).status_code == 404
        assert c.post("/v1/tasks/"+tid+"/cancel",headers=owner_env.auth("B")).status_code == 404

```

- [ ] **Step 2: 执行反例，确认尚缺行为的失败而不是环境错误**

Run: `python -m pytest -q tests/test_tb03_owner_tasks.py`

尚未实现的边界必须出现对应断言失败；已经满足的反例作为回归保留。缺依赖/网络误连/测试未采集先修正测试环境，不能计作业务 red。

- [ ] **Step 3: 用最小改动满足反例，完成必要接线**

`services/identity.py` 的核心内容：

```python
import os

def issue_to_file(registry, owner, target):
    raw = registry.issue(owner)
    principal = registry.resolve(raw)
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(raw + "\n")
    except BaseException:
        registry.revoke(principal.key_id)
        raise
    return principal.key_id
```


- [ ] GET /v1/me 只返回当前稳定 owner；CLI 使用 issue_to_file 独占写私有文件，不把原始凭证打印进日志。
- [ ] 在真实 worker + 外部图片后端替身运行 A/B 的生成、编辑、取图、跨人取消/下载拒绝；不手动置 completed。

- [ ] **Step 4: 按逐条验收映射验证，并记录原始证据**

| 本票验收条件 | 验证安排 |
| --- | --- |
| 1. 提供可复现的个人 Key 发放/撤销/轮换方式，服务器只持久化可校验摘要与 owner 映射，日志不含原始 Key。 | KeyRegistry/issue_to_file 测试：摘要无raw、输出私有、失败撤销；CLI撤销/轮换实测。 |
| 2. A/B 分别完成生成、编辑与取图；任务查询、取消、结果下载及既有非图片媒体入口均按 owner 隔离，跨人返回一致 404。 | worker_result_stays_private＋A/B真实worker生成/编辑/跨人查询取消下载矩阵。 |
| 3. 同人同键同业务输入复用任务；同人同键不同输入 409；不同 owner 使用同一幂等键互不冲突；编辑重试不受临时素材 ID 变化干扰。 | same_request_key_does_not_cross_owners、changed_payload_conflicts、different_upload_ids_same_material_replay。 |
| 4. 同一 owner 的轮换 Key 可继续访问原任务；撤销或未知 Key 返回 401；客户端不能伪造归属。 | rotated_key_retains_owner，撤销401且新Key访问原tid成功；伪造归属422。 |
| 5. 任务和结果、参考素材及清理的 owner 一致；所有调用方迁移到显式归属接口，但仍保留 expand 兼容表示。 | 图片/媒体调用方清单＋真实worker结果隔离；禁止手工置completed。 |
| 6. 保留全局队列边界与幂等重试不额外占位的行为；生产多身份开放仍等待 contract 迁移门禁。 | 4单满载与本人幂等重放，检查重复请求不消耗第五个位置；保持staging门禁。 |

Run: `python -m pytest --collect-only -q -k tb03_owner_tasks`

Run: `python -m pytest -q -k tb03_owner_tasks`

Run: `python -m pytest -q -k "tb03 or image_task_validation_idempotency or edit_retry_with_idempotency or auth_rejections"`


独立演示：A/B 各通过 MCP/HTTPS 完成一次生成和编辑；交叉查询与取消失败；轮换 A 的 Key 后仍取得同一张图。



- [ ] **Step 5: 文档、ADR 与证据同步**

将实际测试输出、受影响回归、失败与恢复步骤写入 OPERATIONS.md；与当前计划对应的 AC 映射逐项填证据。没有实测的项保持未验收，不能只打勾。

- [ ] **Step 6: 独立提交边界 B**

提交范围：其余反例测试、守卫/兼容接线、有效文档；保持本票在前置完成后独立可演示。

```bash
git add -- services/store.py services/gateway.py services/image_routes.py services/images.py services/media.py services/identity.py tests/test_tb03_owner_tasks.py docs/IMAGE-SERVICE.md OPERATIONS.md
git commit -m "test(image): t03 boundaries and recovery"
```

## Rollback / compatibility strategy

撤销受控测试 Key，关闭多身份接入；保留已写数据与归属映射，使用 owner 感知的兼容版本恢复。不得部署会把新用户任务当作公共任务的旧逻辑。

维护过程先停止新工作并保全新增写入；对运行图片定向停止且确认后端空闲。不能回退成跨用户共享访问、关闭保护器或盲目重跑。

## Out of scope

不做客户端持久恢复、断线语义调整、队列公平性、个人配额或完整管理后台。

## Verification environment

以下 python 指令在受支持的工程虚拟环境执行。原工作区可用 .venv/bin/python；Windows 使用对应 .venv\\Scripts\\python.exe。新测试尚未创建，未采集到测试不算通过；本轮仅编写计划，不冒充 red/green 或实机验收已执行。


## Self-review and execution handoff

- [x] 每个本票验收条件已映射到上表；父规格归属：AC-11、AC-12、AC-13、AC-15、AC-20。
- [x] 第一条失败原因与最小实现明确；状态反例为测试代码/实际演示，不只保留图。
- [x] 新签名来自共享契约，当前尚未实现的接口由明确前置/本票交付。
- [x] 边界 A/B 各自带测试与文档；回退不会丢新数据或恢复共享读取。
- [ ] 后续执行者运行 red/green、受影响回归与所需实机验收，填写实际证据后再声明完成。

本次只批准编写和发布计划，不启动产品实现。执行时由用户选择原生或子代理方式；未取得执行授权前不启动实现/部署。
