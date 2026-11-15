# T08 内存观测：一次创作可导出按阶段关联的完整曲线 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 维护者执行一条真实图片任务后，能取得系统、容器及模型生命周期的分口径曲线，判断峰值发生在哪个阶段。

**Architecture:** Consumes: T07 阶段事件；现有 benchmark_images 和固定 ComfyUI 0.33.2。Produces: ResourceSample、validate_run(record)->list[str]、summarize_run(record)->dict；observe CLI；私有 JSONL 原始记录。观测元数据包含 host_id/runtime_hash 和 release_epoch，不公开业务内容。 先读共享执行契约并保留既有兼容边界；本票只交付确认的纵向行为，不扩展为通用重构。

**Tech Stack:** Python、FastAPI、SQLite、httpx、Pillow、stdio MCP；固定 ComfyUI 0.33.2；平台专属脚本按本票列出的操作系统执行。

**Spec:** [父规格 #1](https://github.com/Zeming-Yuan/Agent-/issues/1)；[完整规格](../../specs/2026-11-14-image-service-reliability-and-multiuser.md)；[共享执行契约](2026-11-14-image-execution-contract.md)。执行者必须同时读取三者。

**Ticket:** T08；Blocked by：T07。T07 提供可靠阶段与任务终态，观测需要关联同一生命周期并继续串行修改图片 worker。

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

1. 重复运行固定幂等键：旧结果不能冒充新推理 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
2. 完成即停表：必须覆盖下载、校验与保存 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
3. 本机采样/远端推理：host 不匹配判无效 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
4. 失败/429/超时：必须计入分母而非成功统计 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
5. 假 PNG、空曲线、重复事件：不能计为有效测量 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。

---

## File structure and interfaces

- Modify: scripts/benchmark_images.py — import-safe CLI、唯一 run_id、计时至本地保存
- Create: scripts/image_measurement.py — 原始记录、校验与统计
- Create: services/image_telemetry.py — 5Hz 系统/容器采样与 ResourceSample
- Create: deploy/comfy_lifecycle_probe.py — 固定版本只读生命周期观测
- Modify: deploy/start-comfy.py / services/images.py — 安装观测及关联阶段
- Create: tests/test_tb08_memory_evidence.py
- Modify: OPERATIONS.md

- Modify: docs/superpowers/plans/2026-11-14-image-measurement-contract.md — 本票文档/ADR/实际测量记录同步
- Modify: docs/superpowers/plans/2026-11-14-image-08-memory-evidence.md — 本票文档/ADR/实际测量记录同步

**Consumes / Produces:** Consumes: T07 阶段事件；现有 benchmark_images 和固定 ComfyUI 0.33.2。Produces: ResourceSample、validate_run(record)->list[str]、summarize_run(record)->dict；observe CLI；私有 JSONL 原始记录。观测元数据包含 host_id/runtime_hash 和 release_epoch，不公开业务内容。

## Task 1: 首条用户反例与最小纵向实现

**Files:** 使用上面列出的本票实现文件；首条测试写入 `tests/test_tb08_memory_evidence.py`。本任务最小实现核心位于 `scripts/benchmark_images.py`。

**Interfaces:** 消费上述输入，产出本票外部行为；新公共签名以 Architecture/共享契约为准，不另起别名。

- [ ] **Step 1: 写第一条失败测试**

```python
import asyncio
import runpy

def test_tb08_import_does_not_start_image_work(monkeypatch):
    def reject_run(coro):
        coro.close()
        raise AssertionError("import invoked benchmark main")
    monkeypatch.setattr(asyncio,"run",reject_run)
    runpy.run_module("scripts.benchmark_images",run_name="benchmark_import_probe")
```

- [ ] **Step 2: 运行并确认预期失败原因**

Run: `python -m pytest -q tests/test_tb08_memory_evidence.py`

Expected: 当前脚本底部无 main guard，import 即 asyncio.run(main())；本测试在任何网络或私有配置读取前拦截 coroutine 并失败，绝不为跑失败测试发生产图片请求。 这是执行前预期，不是本轮已取得的测试结果。

- [ ] **Step 3: 最小实现，先让这一条完整路径可工作**

在 `scripts/benchmark_images.py` 应用以下核心，按该文件职责接入真实路由/存储，不替换真实业务层为 mock：

```python
# scripts/benchmark_images.py 的唯一 import-safety 改动
if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] 先单独提交 import main guard；之后所有测量参数解析只在 main 内，测试 import 不读取真实 Key、不访问网络。
- [ ] CLI 的 observe 使用新 uuid4 run_id，每个任务的请求键为 run_id+样本序号；日志关联后端规范 prompt_id 的唯一执行事件，重放旧任务/无执行样本标 invalid。
- [ ] 在同一客户端单调时钟记录 submit→completed→downloaded→decoded+fsync 保存，使用 PIL verify/load 验证输出；失败、超时、拒绝和重试各记原始事件和总尝试数，不能只统计成功样本。
- [ ] ResourceSample 以 0.2 秒周期采样图片执行节点 /proc/meminfo 和实际 cgroup memory.current/peak/max；若 sampler 与后端 host_id 不同则报告无效。记录读取失败和采样空洞，不填 0 冒充观测。

- [ ] **Step 4: 运行首条测试和受影响既有回归**

Run: `python -m pytest -q tests/test_tb08_memory_evidence.py`

Run: `python -m pytest -q -k "tb08 or same_image_model_keeps_weights or fast_editor_uses_acceleration"`

Expected: 所选测试采集非零、断言通过；任何 HTTP/后端替身错误都解释，不能用 deselect/skip 当完成。

- [ ] **Step 5: 同步文档/ADR**

- [ ] OPERATIONS.md：observe 命令、分口径曲线、采样缺失和运维访问限制
- [ ] docs/superpowers/plans/2026-11-14-image-measurement-contract.md：本轮脚本审计和后续 baseline/复测条件

- [ ] **Step 6: 独立提交边界 A**

提交范围：首个外部行为、测试和必要文档；不夹带下一票迁移。Git checkout 中选择实际改动文件后执行：

```bash
python - <<'PY'
from pathlib import Path
import subprocess
candidates = ["scripts/benchmark_images.py","scripts/image_measurement.py","services/image_telemetry.py","deploy/comfy_lifecycle_probe.py","deploy/start-comfy.py","services/images.py","tests/test_tb08_memory_evidence.py","OPERATIONS.md","docs/superpowers/plans/2026-11-14-image-measurement-contract.md","docs/superpowers/plans/2026-11-14-image-08-memory-evidence.md"]
paths = [p for p in candidates if Path(p).is_file()]
subprocess.run(["git", "add", "--", *paths], check=True)
PY
git commit -m "feat(image): t08 vertical core"
```

非 Git 产品目录使用逐任务审查快照与 SHA256 变更清单；不在此处初始化或推送整个工作区。

## Task 2: 状态反例、完整验收与恢复边界

**Files:** `tests/test_tb08_memory_evidence.py`、上面列出的责任模块、文档；新增核心位于 `scripts/image_measurement.py`。

**Interfaces:** 延续 Task 1 的命名/字段/返回值；所有异常路径仍以 owner 隔离和同一任务身份为边界。

- [ ] **Step 1: 把 Review Focus 反例写成具体测试**

以下代码与 Task 1 的测试置于同一测试模块，保留该模块已经定义的 import/帮助函数；不是只画状态图：

```python
import pytest
from scripts.image_measurement import validate_run, summarize_run

def good_run():
    return {"run_id":"run-1","request_id":"run-1-0","task_id":"task-a",
        "profile":"generate","runtime_hash":"hash","host_match":True,
        "backend_executions":1,"status":"completed","output_verified":True,
        "submitted_ns":0,"completed_ns":10000000,"downloaded_ns":15000000,
        "saved_ns":20000000,"memory_samples":[{"available_bytes":40*1024**3}],
        "guard_events":[]}

@pytest.mark.parametrize("field,value",[
    ("backend_executions",0),("host_match",False),("status","failed"),
    ("output_verified",False),("memory_samples",[]),
])
def test_tb08_invalid_work_is_not_a_perf_sample(field,value):
    row = good_run(); row[field] = value
    assert validate_run(row)

def test_tb08_e2e_includes_download_and_save():
    row = good_run()
    assert validate_run(row) == []
    assert summarize_run(row)["e2e_ms"] == 20
    assert summarize_run(row)["inference_wait_ms"] == 10
```

- [ ] **Step 2: 执行反例，确认尚缺行为的失败而不是环境错误**

Run: `python -m pytest -q tests/test_tb08_memory_evidence.py`

尚未实现的边界必须出现对应断言失败；已经满足的反例作为回归保留。缺依赖/网络误连/测试未采集先修正测试环境，不能计作业务 red。

- [ ] **Step 3: 用最小改动满足反例，完成必要接线**

`scripts/image_measurement.py` 的核心内容：

```python
def validate_run(record):
    errors = []
    for name in ("run_id","request_id","task_id","profile","runtime_hash"):
        if not record.get(name): errors.append(name)
    for name in ("host_match","output_verified"):
        if record.get(name) is not True: errors.append(name)
    if record.get("backend_executions") != 1: errors.append("backend_executions")
    if record.get("status") != "completed": errors.append("status")
    if not record.get("memory_samples"): errors.append("memory_samples")
    if record.get("guard_events"): errors.append("guard_events")
    times = [record.get(k) for k in ("submitted_ns","completed_ns","downloaded_ns","saved_ns")]
    if not all(type(v) is int for v in times) or times != sorted(times):
        errors.append("timeline")
    return errors

def summarize_run(record):
    errors = validate_run(record)
    if errors: raise ValueError(",".join(errors))
    return {"e2e_ms":(record["saved_ns"]-record["submitted_ns"])/1e6,
            "inference_wait_ms":(record["completed_ns"]-record["submitted_ns"])/1e6,
            "download_ms":(record["downloaded_ns"]-record["completed_ns"])/1e6,
            "save_ms":(record["saved_ns"]-record["downloaded_ns"])/1e6}
```


- [ ] 固定版本 /free 在 server.py 只 set_flag；main.py 的 worker 稍后处理 unload/free。probe 包装真实 unload_all_models/GC 结束及队列状态，在单调 release_epoch 上记录完成；快照含 current_loaded_models、缓存/驻留对象和分配器口径，不能只看列表为空。
- [ ] probe 由现有受控 start-comfy 启动器注入，不启用 custom/API nodes、不修改未知第三方源码；只读数据通过专用回环运维端口/私有文件读取。旧 profile 图/权重引用无法证明释放时写 None，并阻止后续安全准入。
- [ ] 报告原始 JSONL、版本/负载条件和读得出的最小余量/峰值；当前任务只完成测量方案，真实 baseline 留给受控执行，不能引用历史 20 样本作为新配置基线。

- [ ] **Step 4: 按逐条验收映射验证，并记录原始证据**

| 本票验收条件 | 验证安排 |
| --- | --- |
| 1. 切换/执行期间 MemAvailable 采样至少 5Hz，阶段边界打点；记录容器当前/峰值及可获得的模型驻留/分配器信号，缺失信号明确标记。 | 5Hz采样周期/空洞/读取失败的可控时钟测试；实机原始memory.jsonl与cgroup峰值。 |
| 2. 按任务、非敏感 owner 标识、profile 与输入规模关联；系统与 GPU 分配分口径，统一内存不重复计总量。 | host_match反例、时间口径和不同profile数据分组；公开报告脱敏审计。 |
| 3. 交付可复制运行的观测命令并输出曲线、最低余量、峰值、加载/释放耗时与稳定基线；不采集原始 Key、提示词或素材内容。 | e2e_includes_download_and_save＋observe CLI原始报告、PNG解码/大小/持久化校验。 |
| 4. 如无可靠旧 profile 释放信号，提供最小只读运维观测；明确区分释放请求受理与实际释放完成。 | free set_flag与真实worker处理之间注入停顿；release_epoch不提前增加，缺失观察为None。 |
| 5. 先以已有安全条件内的单任务验证完整采集；模型切换仅在能证明安全的受控条件下记录，不能为采样故意逼近保护阈值。 | 在安全起点跑observe并记录环境/曲线；没有本轮数据时报告not_run而非通过。 |

Run: `python -m pytest --collect-only -q -k tb08_memory_evidence`

Run: `python -m pytest -q -k tb08_memory_evidence`

Run: `python -m pytest -q -k "tb08 or same_image_model_keeps_weights or fast_editor_uses_acceleration"`

外部演示/复测命令（由本票或其前置提供）：

```bash
python -m scripts.benchmark_images --scenario observe --config "<维护者私有配置>" --report-dir "<私有验收目录>"
```

独立演示：用正常提交入口生成一张图片，导出同任务曲线并与阶段事件对齐；对缺失驻留信号的情况明确显示证据不足。



- [ ] **Step 5: 文档、ADR 与证据同步**

将实际测试输出、受影响回归、失败与恢复步骤写入 OPERATIONS.md；与当前计划对应的 AC 映射逐项填证据。没有实测的项保持未验收，不能只打勾。

- [ ] **Step 6: 独立提交边界 B**

提交范围：其余反例测试、守卫/兼容接线、有效文档；保持本票在前置完成后独立可演示。

```bash
python - <<'PY'
from pathlib import Path
import subprocess
candidates = ["scripts/benchmark_images.py","scripts/image_measurement.py","services/image_telemetry.py","deploy/comfy_lifecycle_probe.py","deploy/start-comfy.py","services/images.py","tests/test_tb08_memory_evidence.py","OPERATIONS.md","docs/superpowers/plans/2026-11-14-image-measurement-contract.md","docs/superpowers/plans/2026-11-14-image-08-memory-evidence.md"]
paths = [p for p in candidates if Path(p).is_file()]
subprocess.run(["git", "add", "--", *paths], check=True)
PY
git commit -m "test(image): t08 boundaries and recovery"
```

## Rollback / compatibility strategy

停用新增采样或报告输出并保留原始证据；不删除任务数据、不关闭 20GiB 保护器。观测不足时后续安全准入不得默认通过。

维护过程先停止新工作并保全新增写入；对运行图片定向停止且确认后端空闲。不能回退成跨用户共享访问、关闭保护器或盲目重跑。

## Out of scope

不宣称历史峰值唯一根因；不把请求 /free 成功视为释放完成；不启用未经标定的资源预算或改写调度。

## Verification environment

以下 python 指令在受支持的工程虚拟环境执行。原工作区可用 .venv/bin/python；Windows 使用对应 .venv\\Scripts\\python.exe。新测试尚未创建，未采集到测试不算通过；本轮仅编写计划，不冒充 red/green 或实机验收已执行。

## Measurement baseline and result audit

- 应用 [测量契约](2026-11-14-image-measurement-contract.md)，修改前审核 baseline，完成后执行第11步结果核查。
- 本轮实际 baseline：**not_run**；没有本轮性能/内存标定原始结果，不能报告速度提升、回归或安全参数已成立。
- 现有历史脚本与原始位置、计时边界错误、固定幂等/no-op风险见测量契约；历史数字不作为当前 before。
- 负载/缓存/并发/样本、host/runtime、输出验证、错误计数和复测命令必须写入实际执行记录；比较设置至少每侧5次交替，安全闭环每拟启用profile至少3轮。
- 原始结果存调用者私有唯一 run 目录；报告队列/加载/推理/保存/下载与端到端时间，状态不全则 inconclusive。

## Self-review and execution handoff

- [x] 每个本票验收条件已映射到上表；父规格归属：AC-02、AC-05。
- [x] 第一条失败原因与最小实现明确；状态反例为测试代码/实际演示，不只保留图。
- [x] 新签名来自共享契约，当前尚未实现的接口由明确前置/本票交付。
- [x] 边界 A/B 各自带测试与文档；回退不会丢新数据或恢复共享读取。
- [ ] 后续执行者运行 red/green、受影响回归与所需实机验收，填写实际证据后再声明完成。

本次只批准编写和发布计划，不启动产品实现。执行时由用户选择原生或子代理方式；未取得执行授权前不启动实现/部署。

## 2026-11-15 execution record (supersedes planning-only status)

User authorized single-ticket implement+tdd; three public seams and initial d2a9d197 fixed review base confirmed. Controlled source checkout reused, original non-Git product pending selective verified delivery. Import slice118de0c independently reviewed Standards0/Spec0. Further implementation/evidence index: evidence/issue-9/execution.md; design decisions ADR0003; commands/schema OPERATIONS T08.

Software RED/GREEN and affected validation are recorded individually, not inferred from prior T07 results. Physical single-task observe remains **not_run**, model switches not attempted: LTX active/image failed/guard inactive prevents proving a safe controlled starting condition. No performance baseline, actual >=5Hz, profile release or dual-desktop acceptance claim. #9 must remain open until controlled real-task raw evidence is supplied; T09/T11 cannot treat software observations or release_epoch as a safe profile budget/release certificate.
