# T10 公平轮转：已接纳用户不被持续插队并看到前方单数 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A/B 已接纳的任务按 owner 轮转，每人内部顺序稳定；用户看到与当前公平排程一致的动态前方单数。

**Architecture:** Consumes: T09 可执行判断与独占执行权、T07 稳定阶段。Produces: choose_next(heads,last_owner)->str|None；Store.claim_image_task(resource_view)->dict|None 原子保存 cursor 与 running/claim；queue_ahead:int|None，仅当前公平快照，不含他人详情。 先读共享执行契约并保留既有兼容边界；本票只交付确认的纵向行为，不扩展为通用重构。

**Tech Stack:** Python、FastAPI、SQLite、httpx、Pillow、stdio MCP；固定 ComfyUI 0.33.2；平台专属脚本按本票列出的操作系统执行。

**Spec:** [父规格 #1](https://github.com/Zeming-Yuan/Agent-/issues/1)；[完整规格](../../specs/2026-11-14-image-service-reliability-and-multiuser.md)；[共享执行契约](2026-11-14-image-execution-contract.md)。执行者必须同时读取三者。

**Ticket:** T10；Blocked by：T09。需要 T09 明确可执行/资源等待与控制权释放语义；共享调度状态串行整合。

**Plan status:** 2026-11-15 按用户确认离线执行单票；原产品非 Git，受控源码 checkout 为 /home/clusteradmin/.codex/workspaces/agent-mm-issue-8-20261115，分支 feat/issue-11-fair-queue，固定基线 5e64eb080341a28b35e912e52e8273e16e2fbcd2。切片 A 为 471acb1，95 项受影响验证；切片 B 包含审查发现的 RED/GREEN 修复、重启/取消/并发/满载/资源等待及真实 stdio+本地 TLS 测试。完整证据、实际命令与验收映射见 evidence/issue-11/acceptance.md；最终独立复审与选择性交付结果在该文件持续记录。#10 OPEN、实机与双端 Harness 未验收。下文未实施/预期描述保留为原计划历史，不作为实测结论。

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

1. 同时间入队：本人顺序按持久 enqueue_seq → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
2. 资源阻塞队首：不能越过同人队首 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
3. 取消/重启：cursor 不归零制造插队 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
4. 新用户到达：只能改变快照，不承诺固定 ETA → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
5. 全局满载：仍 429，不能偷加个人限制 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。

---

## File structure and interfaces

- Create: services/image_queue.py — 轮转选择及快照模拟
- Modify: services/store.py — 原子 claim 与持久 cursor
- Modify: services/images.py — 使用可执行 owner 队首
- Modify: services/gateway.py / client/spark_image_tools.py — queue_ahead 输出
- Create: tests/test_tb10_fair_queue.py
- Modify: docs/IMAGE-SERVICE.md

- Modify: OPERATIONS.md — 本票文档/ADR/实际测量记录同步
- Modify: docs/superpowers/plans/2026-11-14-image-10-fair-queue.md — 本票文档/ADR/实际测量记录同步

**Consumes / Produces:** Consumes: T09 可执行判断与独占执行权、T07 稳定阶段。Produces: choose_next(heads,last_owner)->str|None；Store.claim_image_task(resource_view)->dict|None 原子保存 cursor 与 running/claim；queue_ahead:int|None，仅当前公平快照，不含他人详情。

## Task 1: 首条用户反例与最小纵向实现

**Files:** 使用上面列出的本票实现文件；首条测试写入 `tests/test_tb10_fair_queue.py`。本任务最小实现核心位于 `services/image_queue.py`。

**Interfaces:** 消费上述输入，产出本票外部行为；新公共签名以 Architecture/共享契约为准，不另起别名。

- [ ] **Step 1: 写第一条失败测试**

```python
from services.image_queue import choose_next

def test_tb10_owner_gets_turn_before_repeat_submitter():
    heads = [{"id":"A1","owner":"A","eligible":True},
             {"id":"B1","owner":"B","eligible":True}]
    assert choose_next(heads,None) == "A1"
    heads[0]["id"] = "A2"
    assert choose_next(heads,"A") == "B1"
```

- [ ] **Step 2: 运行并确认预期失败原因**

Run: `python -m pytest -q tests/test_tb10_fair_queue.py`

Expected: 当前 Store.next_task 按全局 created/rowid FIFO，A1/A2 先到会连续执行；尚无按 owner 轮转选择。先补 selector 测试，再用真实 HTTP 后端记录验证 B1 不被 A2 插队。 这是执行前预期，不是本轮已取得的测试结果。

- [ ] **Step 3: 最小实现，先让这一条完整路径可工作**

在 `services/image_queue.py` 应用以下核心，按该文件职责接入真实路由/存储，不替换真实业务层为 mock：

```python
def choose_next(heads,last_owner):
    by_owner = {h["owner"]:h for h in heads}
    owners = sorted(by_owner)
    ordered = [o for o in owners if last_owner is None or o > last_owner]
    ordered += [o for o in owners if last_owner is not None and o <= last_owner]
    for owner in ordered:
        row = by_owner[owner]
        if row["eligible"]:
            return row["id"]
    return None
```

- [ ] 创建持久 enqueue_seq 与 singleton last_owner 旁表；同一事务选 owner 队首、校验 queued、写 claim/running 与 cursor，失败不提前移动 cursor。
- [ ] 资源视图只读 T09 有效判断，不为估算队列调用模型加载；阻塞 owner 保留队首且不越过本人队首。若目标不可执行，queue_ahead=null 并显示等待原因。
- [ ] snapshot 与实际 claim 共用 choose_next 规则，排除非图片任务；当前 running/cancelling/cleanup 占用只计一次，不能因为用户状态变化重复计数。

- [ ] **Step 4: 运行首条测试和受影响既有回归**

Run: `python -m pytest -q tests/test_tb10_fair_queue.py`

Run: `python -m pytest -q -k "tb10 or tb09 or bounded_task_queue or image_task_validation"`

Expected: 所选测试采集非零、断言通过；任何 HTTP/后端替身错误都解释，不能用 deselect/skip 当完成。

- [ ] **Step 5: 同步文档/ADR**

- [ ] docs/IMAGE-SERVICE.md：动态 queue_ahead、资源等待与公平范围
- [ ] OPERATIONS.md：cursor 恢复及多人模式降级边界

- [ ] **Step 6: 独立提交边界 A**

提交范围：首个外部行为、测试和必要文档；不夹带下一票迁移。Git checkout 中选择实际改动文件后执行：

```bash
python - <<'PY'
from pathlib import Path
import subprocess
candidates = ["services/image_queue.py","services/store.py","services/images.py","services/gateway.py","client/spark_image_tools.py","tests/test_tb10_fair_queue.py","docs/IMAGE-SERVICE.md","OPERATIONS.md","docs/superpowers/plans/2026-11-14-image-10-fair-queue.md"]
paths = [p for p in candidates if Path(p).is_file()]
subprocess.run(["git", "add", "--", *paths], check=True)
PY
git commit -m "feat(image): t10 vertical core"
```

非 Git 产品目录使用逐任务审查快照与 SHA256 变更清单；不在此处初始化或推送整个工作区。

## Task 2: 状态反例、完整验收与恢复边界

**Files:** `tests/test_tb10_fair_queue.py`、上面列出的责任模块、文档；新增核心位于 `services/image_queue.py`。

**Interfaces:** 延续 Task 1 的命名/字段/返回值；所有异常路径仍以 owner 隔离和同一任务身份为边界。

- [ ] **Step 1: 把 Review Focus 反例写成具体测试**

以下代码与 Task 1 的测试置于同一测试模块，保留该模块已经定义的 import/帮助函数；不是只画状态图：

```python
import pytest
from services.image_queue import choose_next

@pytest.mark.parametrize("last,a_ok,b_ok,expected",[
    ("A",True,True,"B1"),("B",True,True,"A1"),
    ("A",True,False,"A1"),("B",False,True,"B1"),
    ("A",False,False,None),
])
def test_tb10_round_robin_counterexamples(last,a_ok,b_ok,expected):
    heads = [{"id":"A1","owner":"A","eligible":a_ok},
             {"id":"B1","owner":"B","eligible":b_ok}]
    assert choose_next(heads,last) == expected

def test_tb10_global_capacity_is_not_personal_quota(owner_env):
    with owner_env.client() as c:
        for n in range(4):
            assert owner_env.submit(c,"A",request_key=str(n)).status_code == 202
        assert owner_env.submit(c,"B").status_code == 429
        assert owner_env.submit(c,"A",request_key="0").status_code == 202
```

- [ ] **Step 2: 执行反例，确认尚缺行为的失败而不是环境错误**

Run: `python -m pytest -q tests/test_tb10_fair_queue.py`

尚未实现的边界必须出现对应断言失败；已经满足的反例作为回归保留。缺依赖/网络误连/测试未采集先修正测试环境，不能计作业务 red。

- [ ] **Step 3: 用最小改动满足反例，完成必要接线**

`services/image_queue.py` 的核心内容：

```python
def queue_ahead(snapshot,target_id,last_owner,running_id=None):
    rows = [dict(r) for r in snapshot]
    ahead = 1 if running_id and running_id != target_id else 0
    if running_id == target_id: return 0
    while rows:
        heads = []
        for owner in sorted({r["owner"] for r in rows}):
            heads.append(min((r for r in rows if r["owner"]==owner),key=lambda r:r["enqueue_seq"]))
        chosen = choose_next(heads,last_owner)
        if chosen is None: return None
        row = next(r for r in rows if r["id"]==chosen)
        if chosen == target_id: return ahead
        rows.remove(row); ahead += 1; last_owner = row["owner"]
    return None
```


- [ ] 用外部 ImageBackend 控制 A1 完成再观察 B1、A2；重建应用使用同一数据库后继续验证 cursor，真实 HTTP 只返回本人的详情。
- [ ] 公平是任务轮次，不声称延迟变快。若比较 FIFO/轮转等待开销，按测量契约使用同一混合负载并交替至少 5 轮，不用两条不同缓存状态样本作结论。

- [ ] **Step 4: 按逐条验收映射验证，并记录原始证据**

| 本票验收条件 | 验证安排 |
| --- | --- |
| 1. 活跃且可执行 owner 按轮次服务，单个任务不抢占；同 owner FIFO；不因模型亲和性无限跳过别人。 | owner_gets_turn_before_repeat_submitter及真实后端A1→B1→A2顺序。 |
| 2. 某 owner 队首资源不足时保留位置，其他可执行 owner 可服务；不越过该 owner 队首；条件解除后下一可服务轮次获得机会。 | round_robin_counterexamples；阻塞owner保持本人队首、条件恢复下一轮服务。 |
| 3. 调度位置在重启、取消及同时间提交后稳定，持续提交者不能反复回队首造成饥饿。 | 同库重启与取消后cursor仍有效；同时间提交按enqueue_seq顺序。 |
| 4. queue_ahead 按当前公平快照计算并包含正在占用图片执行权的任务；不混入非图片媒体工作，不泄露他人详情，不承诺固定 ETA。 | queue_ahead快照与实际顺序比对；只返回本人详情，非图片任务不混入。 |
| 5. 全局队列已满仍按原边界 429 并给重试提示；已有幂等重放不多占位；不新增个人数量、次数、存储或速率限制。 | global_capacity_is_not_personal_quota，A可占现有4单、B满载429、原请求重放202。 |
| 6. 没有可执行 owner 时等待资源变化，不以忙循环反复加载/释放。 | 全部owner不可执行时没有新/prompt或反复/free；等资源事件再判断。 |

Run: `python -m pytest --collect-only -q -k tb10_fair_queue`

Run: `python -m pytest -q -k tb10_fair_queue`

Run: `python -m pytest -q -k "tb10 or tb09 or bounded_task_queue or image_task_validation"`


独立演示：在现有总容量内让 A 保持多任务、B 提交任务，观察轮转和双方 queue_ahead；取消、重启再验证顺序；单独验证满载明确拒绝。



- [ ] **Step 5: 文档、ADR 与证据同步**

将实际测试输出、受影响回归、失败与恢复步骤写入 docs/IMAGE-SERVICE.md；与当前计划对应的 AC 映射逐项填证据。没有实测的项保持未验收，不能只打勾。

- [ ] **Step 6: 独立提交边界 B**

提交范围：其余反例测试、守卫/兼容接线、有效文档；保持本票在前置完成后独立可演示。

```bash
python - <<'PY'
from pathlib import Path
import subprocess
candidates = ["services/image_queue.py","services/store.py","services/images.py","services/gateway.py","client/spark_image_tools.py","tests/test_tb10_fair_queue.py","docs/IMAGE-SERVICE.md","OPERATIONS.md","docs/superpowers/plans/2026-11-14-image-10-fair-queue.md"]
paths = [p for p in candidates if Path(p).is_file()]
subprocess.run(["git", "add", "--", *paths], check=True)
PY
git commit -m "test(image): t10 boundaries and recovery"
```

## Rollback / compatibility strategy

暂停调度并保存轮转位置/队列；修复前可只开放单 owner 的受控恢复，不能在多人模式悄悄退回可能持续插队的 FIFO。

维护过程先停止新工作并保全新增写入；对运行图片定向停止且确认后端空闲。不能回退成跨用户共享访问、关闭保护器或盲目重跑。

## Out of scope

不保证新用户一定进入已满队列；不做个人配额、任务抢占、GPU 时间公平或聊天调度公平。

## Verification environment

以下 python 指令在受支持的工程虚拟环境执行。原工作区可用 .venv/bin/python；Windows 使用对应 .venv\\Scripts\\python.exe。新测试尚未创建，未采集到测试不算通过；本轮仅编写计划，不冒充 red/green 或实机验收已执行。

## Measurement baseline and result audit

- 应用 [测量契约](2026-11-14-image-measurement-contract.md)，修改前审核 baseline，完成后执行第11步结果核查。
- 本轮实际 baseline：**not_run**；没有本轮性能/内存标定原始结果，不能报告速度提升、回归或安全参数已成立。
- 现有历史脚本与原始位置、计时边界错误、固定幂等/no-op风险见测量契约；历史数字不作为当前 before。
- 负载/缓存/并发/样本、host/runtime、输出验证、错误计数和复测命令必须写入实际执行记录；比较设置至少每侧5次交替，安全闭环每拟启用profile至少3轮。
- 原始结果存调用者私有唯一 run 目录；报告队列/加载/推理/保存/下载与端到端时间，状态不全则 inconclusive。

## Self-review and execution handoff

- [x] 每个本票验收条件已映射到上表；父规格归属：AC-06、AC-14、AC-15。
- [x] 第一条失败原因与最小实现明确；状态反例为测试代码/实际演示，不只保留图。
- [x] 新签名来自共享契约，当前尚未实现的接口由明确前置/本票交付。
- [x] 边界 A/B 各自带测试与文档；回退不会丢新数据或恢复共享读取。
- [ ] 后续执行者运行 red/green、受影响回归与所需实机验收，填写实际证据后再声明完成。

本次只批准编写和发布计划，不启动产品实现。执行时由用户选择原生或子代理方式；未取得执行授权前不启动实现/部署。


## 2026-11-15 执行差异

为保持 T07/T09 语义，claim 与游标原子提交，而 running/loading 仍仅在释放与资源证据通过后设置。新表只添加，不重建 tasks。资源等待复用现有 reducer；worker 生命周期内的只读监视结算未占用队首的等待上限，resource_ready 清除已恢复条件的等待时钟。必要释放不能被释放前容量阻止；已证明空闲但容量不足则保留 queued 并让出轮次。排位与 claim 共用轮转/队首规则，已知本次占用 prompt 精确关联，未知/孤儿仍保守。审查发现均写失败用例后最小修复。只运行修改相关检查，不运行完整门禁，依据用户明确范围。原目录不初始化 Git；受控源码独立提交后按预像校验选择性回送，并保全私有回退副本。

离线交付最终代码05f8ddc，Standards0/Spec0；28项专项、17个受影响文件393项通过，原产品目录同一393项复验通过。原目录保持非Git，预像保全、最终哈希与逐条验收见 evidence/issue-11/acceptance.md、sync-manifest.json。#11仍OPEN等待实机/双端验收，#10及父#1不改；未运行完整项目门禁。
