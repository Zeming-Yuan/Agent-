# T02 迁移素材链路：两个测试身份的文件互不可见 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在受控测试接入中，A/B 使用不同 Key 上传相同素材，各自能读取和删除自己的文件，无法查看或引用对方素材。

**Architecture:** Consumes: T01 Principal/require_owner/owner_env。Produces: Store.file/path/add_file/save_generated/delete_file 的 keyword-only owner（过渡期仅旧入口允许 legacy 默认）；所有用户文件路径先 require_owner，再接触文件系统。 先读共享执行契约并保留既有兼容边界；本票只交付确认的纵向行为，不扩展为通用重构。

**Tech Stack:** Python、FastAPI、SQLite、httpx、Pillow、stdio MCP；固定 ComfyUI 0.33.2；平台专属脚本按本票列出的操作系统执行。

**Spec:** [父规格 #1](https://github.com/Zeming-Yuan/Agent-/issues/1)；[完整规格](../../specs/2026-11-14-image-service-reliability-and-multiuser.md)；[共享执行契约](2026-11-14-image-execution-contract.md)。执行者必须同时读取三者。

**Ticket:** T02；Blocked by：T01。依赖 T01 的稳定身份及兼容结构；串行迁移同一文件库。

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

1. 跨人 ID 与未知 ID：状态和错误体一致 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
2. 相同图片内容：不能跨 owner 复用可探测对象 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
3. 前景与编辑参考：归属检查必须在入队前 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
4. 并发失败清理：不能删别人的素材 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
5. 仍被本人排队任务引用：删除应为 409 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。

---

## File structure and interfaces

- Modify: services/store.py — 文件方法增加 owner 并写归属
- Modify: services/gateway.py — 上传/取图/删除传递请求身份
- Modify: services/image_routes.py — 素材去重、编辑引用与清理归属
- Modify: services/media.py / services/images.py — 仅必要的文件读取调用适配
- Create: tests/test_tb02_owner_files.py
- Modify: docs/IMAGE-SERVICE.md

**Consumes / Produces:** Consumes: T01 Principal/require_owner/owner_env。Produces: Store.file/path/add_file/save_generated/delete_file 的 keyword-only owner（过渡期仅旧入口允许 legacy 默认）；所有用户文件路径先 require_owner，再接触文件系统。

## Task 1: 首条用户反例与最小纵向实现

**Files:** 使用上面列出的本票实现文件；首条测试写入 `tests/test_tb02_owner_files.py`。本任务最小实现核心位于 `services/store.py`。

**Interfaces:** 消费上述输入，产出本票外部行为；新公共签名以 Architecture/共享契约为准，不另起别名。

- [ ] **Step 1: 写第一条失败测试**

```python
def test_tb02_other_owner_cannot_download(owner_env):
    with owner_env.client() as c:
        fid = owner_env.upload(c, "A")
        assert c.get(f"/v1/files/{fid}/content", headers=owner_env.auth("A")).status_code == 200
        foreign = c.get(f"/v1/files/{fid}/content", headers=owner_env.auth("B"))
        absent = c.get("/v1/files/file-" + "f"*32 + "/content", headers=owner_env.auth("B"))
        assert foreign.status_code == absent.status_code == 404
        assert foreign.json() == absent.json()
```

- [ ] **Step 2: 运行并确认预期失败原因**

Run: `python -m pytest -q tests/test_tb02_owner_files.py`

Expected: T01 已允许受控 staging 身份但文件查询仍全局；跨人下载返回 200，或不存在与越权错误体不同，第一断言应失败。 这是执行前预期，不是本轮已取得的测试结果。

- [ ] **Step 3: 最小实现，先让这一条完整路径可工作**

在 `services/store.py` 应用以下核心，按该文件职责接入真实路由/存储，不替换真实业务层为 mock：

```python
from fastapi import HTTPException
from services.ownership import require_owner

def owned_file(store, fid, owner):
    with store.connect() as db:
        require_owner(db, "file", fid, owner)
        row = db.execute("SELECT * FROM files WHERE id=?", (fid,)).fetchone()
    if row is None:
        raise HTTPException(404, "Object not found")
    return dict(row)
```

- [ ] 在创建文件和 object_owners 写入之间使用同一个 BEGIN IMMEDIATE；失败时回收本次独占新文件，不能删除已有对象。
- [ ] 在上传、下载、删除及同步编辑自动上传处使用 request.state.principal.owner；同 owner 的内容去重使用 (owner,digest) 索引和随机不透明 file_id。

- [ ] **Step 4: 运行首条测试和受影响既有回归**

Run: `python -m pytest -q tests/test_tb02_owner_files.py`

Run: `python -m pytest -q -k "tb02 or upload_quota_is_atomic or rejected_edit_releases_only_new_unreferenced_uploads or edit_references_cannot_be_deleted"`

Expected: 所选测试采集非零、断言通过；任何 HTTP/后端替身错误都解释，不能用 deselect/skip 当完成。

- [ ] **Step 5: 同步文档/ADR**

- [ ] docs/IMAGE-SERVICE.md：跨人 404、本人在用素材 409
- [ ] docs/adr/0001-owner-scoped-storage.md：补充素材内容去重的 owner 边界

- [ ] **Step 6: 独立提交边界 A**

提交范围：首个外部行为、测试和必要文档；不夹带下一票迁移。Git checkout 中选择实际改动文件后执行：

```bash
python - <<'PY'
from pathlib import Path
import subprocess
candidates = ["services/store.py","services/gateway.py","services/image_routes.py","services/media.py","services/images.py","tests/test_tb02_owner_files.py","docs/IMAGE-SERVICE.md"]
paths = [p for p in candidates if Path(p).is_file()]
subprocess.run(["git", "add", "--", *paths], check=True)
PY
git commit -m "feat(image): t02 vertical core"
```

非 Git 产品目录使用逐任务审查快照与 SHA256 变更清单；不在此处初始化或推送整个工作区。

## Task 2: 状态反例、完整验收与恢复边界

**Files:** `tests/test_tb02_owner_files.py`、上面列出的责任模块、文档；新增核心位于 `services/image_routes.py`。

**Interfaces:** 延续 Task 1 的命名/字段/返回值；所有异常路径仍以 owner 隔离和同一任务身份为边界。

- [ ] **Step 1: 把 Review Focus 反例写成具体测试**

以下代码与 Task 1 的测试置于同一测试模块，保留该模块已经定义的 import/帮助函数；不是只画状态图：

```python
import pytest

@pytest.mark.parametrize("kind,field", [("image_edit", "image_ids"), ("image_generate", "foreground_file_id")])
def test_tb02_foreign_reference_rejected_before_enqueue(owner_env, kind, field):
    with owner_env.client() as c:
        fid = owner_env.upload(c, "A")
        value = [fid] if field == "image_ids" else fid
        r = owner_env.submit(c, "B", kind=kind, **{field: value})
        assert r.status_code == 404
        assert c.delete(f"/v1/files/{fid}", headers=owner_env.auth("B")).status_code == 404
        assert c.get(f"/v1/files/{fid}/content", headers=owner_env.auth("A")).status_code == 200

def test_tb02_same_bytes_are_independent_objects(owner_env):
    with owner_env.client() as c:
        a = owner_env.upload(c, "A")
        b = owner_env.upload(c, "B")
        assert a != b
        assert c.delete(f"/v1/files/{b}", headers=owner_env.auth("B")).status_code == 200
        assert c.get(f"/v1/files/{a}/content", headers=owner_env.auth("A")).status_code == 200

def test_tb02_own_pending_reference_is_protected(owner_env):
    with owner_env.client() as c:
        fid = owner_env.upload(c, "A")
        assert owner_env.submit(c, "A", kind="image_edit", image_ids=[fid]).status_code == 202
        assert c.delete(f"/v1/files/{fid}", headers=owner_env.auth("A")).status_code == 409

def test_tb02_failed_edit_keeps_other_owners_file(owner_env):
    with owner_env.client() as c:
        fid = owner_env.upload(c,"A")
        data = c.get("/v1/files/"+fid+"/content",headers=owner_env.auth("A")).content
        for n in range(4):
            assert owner_env.submit(c,"A",request_key="full-"+str(n)).status_code == 202
        failed = c.post("/v1/images/edits",headers=owner_env.auth("B"),
            data={"prompt":"edit"},files={"image":("x.png",data,"image/png")})
        assert failed.status_code == 429
        assert c.get("/v1/files/"+fid+"/content",headers=owner_env.auth("A")).content == data

```

- [ ] **Step 2: 执行反例，确认尚缺行为的失败而不是环境错误**

Run: `python -m pytest -q tests/test_tb02_owner_files.py`

尚未实现的边界必须出现对应断言失败；已经满足的反例作为回归保留。缺依赖/网络误连/测试未采集先修正测试环境，不能计作业务 red。

- [ ] **Step 3: 用最小改动满足反例，完成必要接线**

`services/image_routes.py` 的核心内容：

```python
import hashlib
import uuid

def reference_identity(owner, data):
    # The digest is lookup metadata within an owner, never a global file ID.
    return owner, hashlib.sha256(data).hexdigest()

def new_reference_id():
    return "file-" + uuid.uuid4().hex
```


- [ ] 先验证所有 image_ids/foreground_file_id 的归属，再触发后端可用性检查和任务接纳；既有媒体 file_id 同样检查。
- [ ] 保持 staged 多身份只在受控环境；T03 完成任务迁移前不开放生产多身份。

- [ ] **Step 4: 按逐条验收映射验证，并记录原始证据**

| 本票验收条件 | 验证安排 |
| --- | --- |
| 1. 在测试部署使用两个明确 owner 的 Key；生产多用户总开关保持关闭，旧共享入口仍只属于 legacy。 | legacy/staging 配置测试；确认 production legacy 对其他 owner 返回401。 |
| 2. 覆盖上传、鉴权下载、删除、同步编辑自动上传、image_ids、透明前景和既有媒体文件引用；跨人对象与不存在对象均返回一致 404。 | test_tb02_other_owner_cannot_download、foreign_reference 参数化和本人在用删除409。 |
| 3. 相同图片内容的去重限制在本人范围，不能通过内容哈希、文件 ID 或错误信息探测别人的素材。 | same_bytes_are_independent_objects，B 删除后 A 内容字节不变。 |
| 4. 当前用户的文件链路可完成上传→引用→取回；跨人引用在入队前被拒绝，不生成后台任务或泄露文件名。 | foreign_reference 在入队前404；通过后端 jobs 计数为0核对。 |
| 5. 并发上传、失败清理和在用文件保护不删除别人的文件，保留既有全局原子容量检查。 | failed_edit_keeps_other_owners_file＋并发上传/回收既有回归，核对 A 的原字节。 |

Run: `python -m pytest --collect-only -q -k tb02_owner_files`

Run: `python -m pytest -q -k tb02_owner_files`

Run: `python -m pytest -q -k "tb02 or upload_quota_is_atomic or rejected_edit_releases_only_new_unreferenced_uploads or edit_references_cannot_be_deleted"`


独立演示：用两组测试 Key 上传同一 PNG；演示本人下载成功、互相读/删/作为编辑或前景引用均 404，测试期间不开放生产多身份。



- [ ] **Step 5: 文档、ADR 与证据同步**

将实际测试输出、受影响回归、失败与恢复步骤写入 docs/IMAGE-SERVICE.md；与当前计划对应的 AC 映射逐项填证据。没有实测的项保持未验收，不能只打勾。

- [ ] **Step 6: 独立提交边界 B**

提交范围：其余反例测试、守卫/兼容接线、有效文档；保持本票在前置完成后独立可演示。

```bash
python - <<'PY'
from pathlib import Path
import subprocess
candidates = ["services/store.py","services/gateway.py","services/image_routes.py","services/media.py","services/images.py","tests/test_tb02_owner_files.py","docs/IMAGE-SERVICE.md"]
paths = [p for p in candidates if Path(p).is_file()]
subprocess.run(["git", "add", "--", *paths], check=True)
PY
git commit -m "test(image): t02 boundaries and recovery"
```

## Rollback / compatibility strategy

关闭受控多身份入口，保留已写 owner 与文件归属检查；维护期间仅服务 legacy 自有数据。不得将含多个 owner 的文件库直接交给 T01 之前的全库可读实现，测试 owner 数据须继续不可见。

维护过程先停止新工作并保全新增写入；对运行图片定向停止且确认后端空闲。不能回退成跨用户共享访问、关闭保护器或盲目重跑。

## Out of scope

不启用完整多用户任务访问；不做任务列表、客户端恢复、公平排队或个人存储配额。

## Verification environment

以下 python 指令在受支持的工程虚拟环境执行。原工作区可用 .venv/bin/python；Windows 使用对应 .venv\\Scripts\\python.exe。新测试尚未创建，未采集到测试不算通过；本轮仅编写计划，不冒充 red/green 或实机验收已执行。


## Self-review and execution handoff

- [x] 每个本票验收条件已映射到上表；父规格归属：AC-11、AC-15、AC-20。
- [x] 第一条失败原因与最小实现明确；状态反例为测试代码/实际演示，不只保留图。
- [x] 新签名来自共享契约，当前尚未实现的接口由明确前置/本票交付。
- [x] 边界 A/B 各自带测试与文档；回退不会丢新数据或恢复共享读取。
- [ ] 后续执行者运行 red/green、受影响回归与所需实机验收，填写实际证据后再声明完成。

本次只批准编写和发布计划，不启动产品实现。执行时由用户选择原生或子代理方式；未取得执行授权前不启动实现/部署。
