# T09 安全开工：释放可确认、预算足够才加载下一模型 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用户连续生成/编辑时，服务先确认旧模型释放；内存不足则显示资源等待，无法确认安全则明确失败或降级，不冒险开工。

**Architecture:** Consumes: T08 ResourceSample/release_epoch 与 T07 终态/阶段。Produces: MemoryBudget、AdmissionDecision、admit 与 released(samples,after_epoch,stable_window)->bool；正值 max_age/stable_window/wait_timeout 配置；未签署/失效 profile 默认禁用。 create_app 增加 resource_sampler、memory_budgets、resource_settings、image_runtime_hash 四个 keyword-only 注入点，默认加载真实观测与配置；只在测试 fixture 提供合成值。 先读共享执行契约并保留既有兼容边界；本票只交付确认的纵向行为，不扩展为通用重构。

**Tech Stack:** Python、FastAPI、SQLite、httpx、Pillow、stdio MCP；固定 ComfyUI 0.33.2；平台专属脚本按本票列出的操作系统执行。

**Spec:** [父规格 #1](https://github.com/Zeming-Yuan/Agent-/issues/1)；[完整规格](../../specs/2026-11-14-image-service-reliability-and-multiuser.md)；[共享执行契约](2026-11-14-image-execution-contract.md)。执行者必须同时读取三者。

**Ticket:** T09；Blocked by：T08。依赖 T08 的有效资源与驻留证据；共用同一个串行执行控制权。

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

1. free HTTP 成功但 epoch 未变：不能加载 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
2. 采样陈旧/来自未来/缺失：不能按零驻留放行 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
3. 系统够而 cgroup 不够：同样拒绝 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
4. 预算与运行时不符或失效：profile 关闭 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
5. 等待超限/用户取消：终态明确且不遗留 GPU 工作 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。

---

## File structure and interfaces

- Create: services/image_resources.py — 资源包络/准入/释放证明
- Modify: services/images.py — 切换控制权、等待、超时与准入
- Modify: services/store.py / services/gateway.py — 阻塞原因与健康降级
- Modify: deploy/run-image.sh — 仅加载已验证资源配置
- Create: tests/test_tb09_safe_admission.py
- Modify: OPERATIONS.md / docs/adr/0002-image-resource-admission.md
- Modify: tests/conftest.py — 为既有集成测试注入有效合成资源与包络

- Modify: docs/superpowers/plans/2026-11-14-image-09-safe-admission.md — 本票文档/ADR/实际测量记录同步

**Consumes / Produces:** Consumes: T08 ResourceSample/release_epoch 与 T07 终态/阶段。Produces: MemoryBudget、AdmissionDecision、admit 与 released(samples,after_epoch,stable_window)->bool；正值 max_age/stable_window/wait_timeout 配置；未签署/失效 profile 默认禁用。 create_app 增加 resource_sampler、memory_budgets、resource_settings、image_runtime_hash 四个 keyword-only 注入点，默认加载真实观测与配置；只在测试 fixture 提供合成值。

## Task 1: 首条用户反例与最小纵向实现

**Files:** 使用上面列出的本票实现文件；首条测试写入 `tests/test_tb09_safe_admission.py`。本任务最小实现核心位于 `services/image_resources.py`。

**Interfaces:** 消费上述输入，产出本票外部行为；新公共签名以 Architecture/共享契约为准，不另起别名。

- [ ] **Step 1: 写第一条失败测试**

```python
from services.image_telemetry import ResourceSample
from services.image_resources import MemoryBudget, admit

def test_tb09_low_memory_does_not_start_work():
    gib = 1024**3
    sample = ResourceSample(25*gib,50*gib,10.0,frozenset(),(),2)
    budget = MemoryBudget(10*gib,2*gib,20*gib,100.0,"runtime")
    decision = admit(sample,budget,now=10.0,runtime_hash="runtime",released=True,max_age=1.0)
    assert not decision.allowed
    assert decision.reason == "system_memory"
```

- [ ] **Step 2: 运行并确认预期失败原因**

Run: `python -m pytest -q tests/test_tb09_safe_admission.py`

Expected: 当前没有任务预算/ResourceSample 准入，只以 20GiB 静态比较；25GiB 会启动 10GiB 增量工作。新模块首次缺失，集成后必须由后端未收到 /prompt 的断言验证，不止验证 policy 返回值。 这是执行前预期，不是本轮已取得的测试结果。

- [ ] **Step 3: 最小实现，先让这一条完整路径可工作**

在 `services/image_resources.py` 应用以下核心，按该文件职责接入真实路由/存储，不替换真实业务层为 mock：

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class MemoryBudget:
    peak_increment_bytes: int
    margin_bytes: int
    reserve_bytes: int
    valid_until: float
    runtime_hash: str

@dataclass(frozen=True)
class AdmissionDecision:
    allowed: bool
    reason: str

def admit(sample,budget,*,now,runtime_hash,released,max_age):
    if sample is None or budget is None: return AdmissionDecision(False,"missing_evidence")
    if not released: return AdmissionDecision(False,"release_unconfirmed")
    if max_age <= 0 or not 0 <= now-sample.observed_at <= max_age:
        return AdmissionDecision(False,"stale_sample")
    if budget.valid_until <= now or budget.runtime_hash != runtime_hash:
        return AdmissionDecision(False,"invalid_budget")
    if budget.reserve_bytes < 20*1024**3 or budget.peak_increment_bytes < 0 or budget.margin_bytes < 0:
        return AdmissionDecision(False,"invalid_budget")
    need = budget.peak_increment_bytes + budget.margin_bytes
    if sample.available_bytes < need + budget.reserve_bytes:
        return AdmissionDecision(False,"system_memory")
    if sample.cgroup_headroom_bytes < need:
        return AdmissionDecision(False,"container_memory")
    return AdmissionDecision(True,"ready")
```

- [ ] 释放证明还需 T08 的完整引用清理/GC 结束信号与采样连续性；released 的列表必须由连续观测窗口生成，存在空洞则重置，不能把两条稀疏采样当稳定。
- [ ] 将 cold profile 切换放在现有唯一 worker 控制权内：停止确认→请求 free→等 release_epoch/引用证据→连续稳定窗口→admit→立即二次读取再加载。hot profile 用同基线实测增量，不重复扣已驻留字节。
- [ ] queued 的等待资源任务记录 blocked_reason，按正值 wait_timeout 计独立等待时钟；使用可取消 Event.wait/有界轮询，在模型开工时才开始实际推理超时。

- [ ] **Step 4: 运行首条测试和受影响既有回归**

Run: `python -m pytest -q tests/test_tb09_safe_admission.py`

Run: `python -m pytest -q -k "tb09 or tb07 or unknown_submit_outcome or unavailable_backend_rejects"`

Expected: 所选测试采集非零、断言通过；任何 HTTP/后端替身错误都解释，不能用 deselect/skip 当完成。

- [ ] **Step 5: 同步文档/ADR**

- [ ] OPERATIONS.md：资源包络、配置失效、等待上限与人工恢复
- [ ] docs/adr/0002-image-resource-admission.md：统一内存、增量基线、release epoch 和 fail-closed 决策

- [ ] **Step 6: 独立提交边界 A**

提交范围：首个外部行为、测试和必要文档；不夹带下一票迁移。Git checkout 中选择实际改动文件后执行：

```bash
python - <<'PY'
from pathlib import Path
import subprocess
candidates = ["services/image_resources.py","services/images.py","services/store.py","services/gateway.py","deploy/run-image.sh","tests/test_tb09_safe_admission.py","OPERATIONS.md","docs/adr/0002-image-resource-admission.md","tests/conftest.py","docs/superpowers/plans/2026-11-14-image-09-safe-admission.md"]
paths = [p for p in candidates if Path(p).is_file()]
subprocess.run(["git", "add", "--", *paths], check=True)
PY
git commit -m "feat(image): t09 vertical core"
```

非 Git 产品目录使用逐任务审查快照与 SHA256 变更清单；不在此处初始化或推送整个工作区。

## Task 2: 状态反例、完整验收与恢复边界

**Files:** `tests/test_tb09_safe_admission.py`、上面列出的责任模块、文档；新增核心位于 `services/image_resources.py`。

**Interfaces:** 延续 Task 1 的命名/字段/返回值；所有异常路径仍以 owner 隔离和同一任务身份为边界。

- [ ] **Step 1: 把 Review Focus 反例写成具体测试**

以下代码与 Task 1 的测试置于同一测试模块，保留该模块已经定义的 import/帮助函数；不是只画状态图：

```python
import pytest
from services.image_telemetry import ResourceSample
from services.image_resources import MemoryBudget, admit

@pytest.mark.parametrize("now,released,headroom,runtime,expected",[
    (10.0,False,50,"runtime","release_unconfirmed"),
    (20.0,True,50,"runtime","stale_sample"),
    (9.0,True,50,"runtime","stale_sample"),
    (10.0,True,1,"runtime","container_memory"),
    (10.0,True,50,"different","invalid_budget"),
])
def test_tb09_resource_counterexamples(now,released,headroom,runtime,expected):
    gib = 1024**3
    sample = ResourceSample(60*gib,headroom*gib,10.0,frozenset(),(),2)
    budget = MemoryBudget(10*gib,2*gib,20*gib,100.0,"runtime")
    result = admit(sample,budget,now=now,runtime_hash=runtime,released=released,max_age=1.0)
    assert not result.allowed and result.reason == expected
```

- [ ] **Step 2: 执行反例，确认尚缺行为的失败而不是环境错误**

Run: `python -m pytest -q tests/test_tb09_safe_admission.py`

尚未实现的边界必须出现对应断言失败；已经满足的反例作为回归保留。缺依赖/网络误连/测试未采集先修正测试环境，不能计作业务 red。

- [ ] **Step 3: 用最小改动满足反例，完成必要接线**

`services/image_resources.py` 的核心内容：

```python
def released(samples,after_epoch,stable_window):
    if not samples or stable_window <= 0:
        return False
    if samples[-1].observed_at-samples[0].observed_at < stable_window:
        return False
    for sample in samples:
        if sample.release_epoch <= after_epoch:
            return False
        if sample.resident_profiles is None or sample.running_prompts is None:
            return False
        if sample.resident_profiles or sample.running_prompts:
            return False
    return all(a.observed_at < b.observed_at for a,b in zip(samples,samples[1:]))
```


- [ ] 将 synthetic 样本通过测试依赖注入送入真实网关/worker；对每个反例验证后端 jobs 长度不增加、MCP 显示原因，资源恢复则原任务 ID 开工。
- [ ] 只接受带 runtime_hash/标定证据引用的资源配置；本票单测数值不是生产预算。允许受控标定仅在容器硬上界与系统余量能证明初始安全时进行，不增加跳过准入的开关。
- [ ] 更新 owner_env：ImageBackend /free 实际完成后递增 release_epoch 并清 resident_profiles；/prompt 记驻留 profile，history 完成仅清 running。resource_sampler 返回实时 fixture 事件与合成 80GiB/60GiB 余量，budget 使用测试 10GiB+2GiB、reserve20GiB、hash='fixture'，stable_window=.05、max_age=1、wait_timeout=1。这些值只在临时测试夹具，不写生产默认配置；确保 T03/T05/T07 全链路回归仍经过真实准入。

- [ ] **Step 4: 按逐条验收映射验证，并记录原始证据**

| 本票验收条件 | 验证安排 |
| --- | --- |
| 1. 单一控制权覆盖停止、释放确认、加载、生成、保存及清理；释放 HTTP 成功、固定 sleep 或单次余量回升均不能单独放行。 | cancel/lifecycle集成＋worker控制权；free仅响应但epoch不变时后端jobs不增加。 |
| 2. 按有效 profile/输入包络的新增峰值、保守裕量、20GiB 余量和容器可用空间共同判断；预算缺失/过期、采样失效或旧任务未停时不启动新工作。 | low_memory_does_not_start_work及resource_counterexamples；额外覆盖缺budget/过期/缺采样/容器边界。 |
| 3. 等待资源仍是 queued 并解释原因，支持显式取消；开工前立即复查，等待超限明确失败；排队/等待与实际推理时钟分离。 | 受控时钟推进等待上限、queued取消、资源恢复后原tid开工；非永久排队。 |
| 4. 旧/新 profile 以及 fast/原版编辑边界可验证；取消后回切不残留 LoRA 或孤儿推理。 | fast→standard→generate集成事件/驻留证据，取消后无LoRA残留或孤儿prompt。 |
| 5. 释放失败/提交未知时健康降级、新建工作 503；已有记录与结果可恢复；禁止无限自动加载重试。 | 失败/未知状态health503；T05离线历史结果恢复回归。 |
| 6. 默认生产不开启未标定 profile；受控标定只能在配置了有证据的安全起始边界后进行，不能跳过准入或降低保护器。 | 配置缺有效证据/缺正值窗口则拒绝启用；合成测试预算不得进入生产文件。 |

Run: `python -m pytest --collect-only -q -k tb09_safe_admission`

Run: `python -m pytest -q -k tb09_safe_admission`

Run: `python -m pytest -q -k "tb09 or tb07 or unknown_submit_outcome or unavailable_backend_rejects"`


独立演示：通过 MCP/HTTPS 提交任务，注入预算不足、虚假释放成功、采样失效和容器余量不足；证明后端不启动新工作，恢复有效条件后原任务可继续。



- [ ] **Step 5: 文档、ADR 与证据同步**

将实际测试输出、受影响回归、失败与恢复步骤写入 OPERATIONS.md；与当前计划对应的 AC 映射逐项填证据。没有实测的项保持未验收，不能只打勾。

- [ ] **Step 6: 独立提交边界 B**

提交范围：其余反例测试、守卫/兼容接线、有效文档；保持本票在前置完成后独立可演示。

```bash
python - <<'PY'
from pathlib import Path
import subprocess
candidates = ["services/image_resources.py","services/images.py","services/store.py","services/gateway.py","deploy/run-image.sh","tests/test_tb09_safe_admission.py","OPERATIONS.md","docs/adr/0002-image-resource-admission.md","tests/conftest.py","docs/superpowers/plans/2026-11-14-image-09-safe-admission.md"]
paths = [p for p in candidates if Path(p).is_file()]
subprocess.run(["git", "add", "--", *paths], check=True)
PY
git commit -m "test(image): t09 boundaries and recovery"
```

## Rollback / compatibility strategy

关闭新接单并将 profile 置为未启用，保留队列与诊断证据；人工确认旧工作停止后恢复已验证配置。不得回退为只靠 20GiB 静态检查强行执行。

维护过程先停止新工作并保全新增写入；对运行图片定向停止且确认后端空闲。不能回退成跨用户共享访问、关闭保护器或盲目重跑。

## Out of scope

本票不凭空决定生产预算数字；不扩大并发、不更换模型、不做个人配额；真实包络启用由后续标定票完成。

## Verification environment

以下 python 指令在受支持的工程虚拟环境执行。原工作区可用 .venv/bin/python；Windows 使用对应 .venv\\Scripts\\python.exe。新测试尚未创建，未采集到测试不算通过；本轮仅编写计划，不冒充 red/green 或实机验收已执行。

## Measurement baseline and result audit

- 应用 [测量契约](2026-11-14-image-measurement-contract.md)，修改前审核 baseline，完成后执行第11步结果核查。
- 本轮实际 baseline：**not_run**；没有本轮性能/内存标定原始结果，不能报告速度提升、回归或安全参数已成立。
- 现有历史脚本与原始位置、计时边界错误、固定幂等/no-op风险见测量契约；历史数字不作为当前 before。
- 负载/缓存/并发/样本、host/runtime、输出验证、错误计数和复测命令必须写入实际执行记录；比较设置至少每侧5次交替，安全闭环每拟启用profile至少3轮。
- 原始结果存调用者私有唯一 run 目录；报告队列/加载/推理/保存/下载与端到端时间，状态不全则 inconclusive。

## Self-review and execution handoff

- [x] 每个本票验收条件已映射到上表；父规格归属：AC-03、AC-04、AC-05、AC-17、AC-18。
- [x] 第一条失败原因与最小实现明确；状态反例为测试代码/实际演示，不只保留图。
- [x] 新签名来自共享契约，当前尚未实现的接口由明确前置/本票交付。
- [x] 边界 A/B 各自带测试与文档；回退不会丢新数据或恢复共享读取。
- [ ] 后续执行者运行 red/green、受影响回归与所需实机验收，填写实际证据后再声明完成。

本次只批准编写和发布计划，不启动产品实现。执行时由用户选择原生或子代理方式；未取得执行授权前不启动实现/部署。

## 预算有效期的时钟约定

部署配置持久化 UTC expires_at；加载时换算为本次启动的 monotonic 截止：valid_until = monotonic_now + max(0, expires_at - utc_now)。MemoryBudget.valid_until 仅为内存对象，不将单调时钟值写回持久配置；重启后重新换算，过期配置保持禁用。测试中的 now/valid_until 是同一单调时钟域。
