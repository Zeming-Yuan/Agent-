# T11 实机标定：启用有证据的 profile 并完成连续切换 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 维护者可按已验证的内存包络启用图片模式，用户连续“生图→编辑→生图”时不触发保护停服。

**Architecture:** Consumes: T10 最终调度构建、T09 准入和 T08 原始测量契约。Produces: validate_profile_report(report)->list[str]；model-switch CLI；私有原始记录和经证据绑定的 profile 配置。CLI --cycles 接受不小于 3，比较配置时每侧至少 5 轮交替。 先读共享执行契约并保留既有兼容边界；本票只交付确认的纵向行为，不扩展为通用重构。

**Tech Stack:** Python、FastAPI、SQLite、httpx、Pillow、stdio MCP；固定 ComfyUI 0.33.2；平台专属脚本按本票列出的操作系统执行。

**Spec:** [父规格 #1](https://github.com/Zeming-Yuan/Agent-/issues/1)；[完整规格](../../specs/2026-11-14-image-service-reliability-and-multiuser.md)；[共享执行契约](2026-11-14-image-execution-contract.md)。执行者必须同时读取三者。

**Ticket:** T11；Blocked by：T10。标定必须针对已整合的最终 worker/调度构建，避免测量过程中又修改同一服务。

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

1. 标定三轮只有序号：必须有九次不同实际任务证据 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
2. 复用旧 ID/旧配置：不能混入新 runtime 包络 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
3. 只测 fast：不得宣称 standard/high 可用 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
4. A/B 缓存或并发不同：比较无效 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
5. 峰值/保护事件缺失：不能用成功图片掩盖资源风险 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。

---

## File structure and interfaces

- Modify: scripts/benchmark_images.py — model-switch 场景与受控 baseline
- Modify: scripts/image_measurement.py — profile 报告校验/统计
- Create: tests/test_tb11_calibrated_switching.py
- Modify: OPERATIONS.md — 有效预算及标定记录
- Modify: docs/adr/0002-image-resource-admission.md — 记录采用依据，不伪造数值

- Modify: docs/superpowers/plans/2026-11-14-image-11-calibrated-switching.md — 本票文档/ADR/实际测量记录同步

**Consumes / Produces:** Consumes: T10 最终调度构建、T09 准入和 T08 原始测量契约。Produces: validate_profile_report(report)->list[str]；model-switch CLI；私有原始记录和经证据绑定的 profile 配置。CLI --cycles 接受不小于 3，比较配置时每侧至少 5 轮交替。

## Task 1: 首条用户反例与最小纵向实现

**Files:** 使用上面列出的本票实现文件；首条测试写入 `tests/test_tb11_calibrated_switching.py`。本任务最小实现核心位于 `scripts/image_measurement.py`。

**Interfaces:** 消费上述输入，产出本票外部行为；新公共签名以 Architecture/共享契约为准，不另起别名。

- [ ] **Step 1: 写第一条失败测试**

```python
from scripts.image_measurement import validate_profile_report

def test_tb11_no_raw_runs_cannot_enable_profile():
    report = {"profile":"fast","cycles":[1,2,3],"raw_runs":[],
        "input_envelope":{"sizes":["1024x1024"],"references":[1]},
        "runtime_hash":"r","baseline_status":"not_run",
        "guard_events":[],"min_available_bytes":40*1024**3,
        "release_proof":False,"budget":{}}
    errors = validate_profile_report(report)
    assert "raw_runs" in errors
    assert "release_proof" in errors
    assert "budget" in errors
```

- [ ] **Step 2: 运行并确认预期失败原因**

Run: `python -m pytest -q tests/test_tb11_calibrated_switching.py`

Expected: T08 只有单次测量校验，未建立 profile 启用门禁。不能因存在空报告/三条序号就认为已完成三轮实际推理。 这是执行前预期，不是本轮已取得的测试结果。

- [ ] **Step 3: 最小实现，先让这一条完整路径可工作**

在 `scripts/image_measurement.py` 应用以下核心，按该文件职责接入真实路由/存储，不替换真实业务层为 mock：

```python
from scripts.image_measurement import validate_run

def validate_profile_report(report):
    errors = []
    for key in ("profile","runtime_hash","input_envelope","budget"):
        if not report.get(key): errors.append(key)
    cycles = report.get("cycles",[])
    if len(cycles) < 3: errors.append("cycles")
    runs = report.get("raw_runs",[])
    if len(runs) < 9 or any(validate_run(r) for r in runs): errors.append("raw_runs")
    if len({r.get("task_id") for r in runs}) != len(runs): errors.append("duplicate_tasks")
    if report.get("release_proof") is not True: errors.append("release_proof")
    if report.get("guard_events"): errors.append("guard_events")
    if report.get("min_available_bytes",0) < 20*1024**3: errors.append("reserve")
    return errors
```

- [ ] 先以修正后的测量入口记录安全受控环境的 baseline；保存新 run_id、所有尝试与输出验证。历史脚本的固定幂等/截断计时结果只作背景，不作为可比较基线。
- [ ] 按测量契约冻结 runtime/model/workflow hash、五种尺寸包络、1/3 参考图、fast/standard/high、冷/热、并发1及双 owner 队列负载。先做安全上界证明，无安全起点时停止并写 inconclusive，不回退到不安全旧调度。
- [ ] 每个拟启用编辑 profile 至少三轮 G→E→G，其中包含冷/热与编辑取消回切；用实际任务/后端执行事件连接每轮，不只记录返回 200。若比较设置/实现选择，每侧至少5轮 A/B 交替，报告 median/range 与错误数；限制来源不清就不选赢家。

- [ ] **Step 4: 运行首条测试和受影响既有回归**

Run: `python -m pytest -q tests/test_tb11_calibrated_switching.py`

Run: `python -m pytest -q -k "tb11 or tb08 or tb09 or tb10"`

Expected: 所选测试采集非零、断言通过；任何 HTTP/后端替身错误都解释，不能用 deselect/skip 当完成。

- [ ] **Step 5: 同步文档/ADR**

- [ ] OPERATIONS.md：每个启用 profile 的实测参数、环境、原始结果与复测命令
- [ ] docs/adr/0002-image-resource-admission.md：实测采用依据、未知来源与失效条件
- [ ] 当前计划 Measurement baseline 部分追加本次实际 run_id/结果路径；无数据只能写未实测

- [ ] **Step 6: 独立提交边界 A**

提交范围：首个外部行为、测试和必要文档；不夹带下一票迁移。Git checkout 中选择实际改动文件后执行：

```bash
python - <<'PY'
from pathlib import Path
import subprocess
candidates = ["scripts/benchmark_images.py","scripts/image_measurement.py","tests/test_tb11_calibrated_switching.py","OPERATIONS.md","docs/adr/0002-image-resource-admission.md","docs/superpowers/plans/2026-11-14-image-11-calibrated-switching.md"]
paths = [p for p in candidates if Path(p).is_file()]
subprocess.run(["git", "add", "--", *paths], check=True)
PY
git commit -m "feat(image): t11 vertical core"
```

非 Git 产品目录使用逐任务审查快照与 SHA256 变更清单；不在此处初始化或推送整个工作区。

## Task 2: 状态反例、完整验收与恢复边界

**Files:** `tests/test_tb11_calibrated_switching.py`、上面列出的责任模块、文档；新增核心位于 `scripts/image_measurement.py`。

**Interfaces:** 延续 Task 1 的命名/字段/返回值；所有异常路径仍以 owner 隔离和同一任务身份为边界。

- [ ] **Step 1: 把 Review Focus 反例写成具体测试**

以下代码与 Task 1 的测试置于同一测试模块，保留该模块已经定义的 import/帮助函数；不是只画状态图：

```python
import pytest
from scripts.image_measurement import validate_profile_report

def profile_fixture():
    runs=[]
    for i in range(9):
        runs.append({"run_id":"run-1","request_id":f"req-{i}","task_id":f"task-{i}",
            "profile":"fast" if i%3==1 else "generate","runtime_hash":"r",
            "host_match":True,"backend_executions":1,"status":"completed",
            "output_verified":True,"submitted_ns":i*100,"completed_ns":i*100+10,
            "downloaded_ns":i*100+20,"saved_ns":i*100+30,
            "memory_samples":[{"available_bytes":40*1024**3}],"guard_events":[]})
    return {"profile":"fast","cycles":[1,2,3],"raw_runs":runs,
        "input_envelope":{"sizes":["1024x1024"],"references":[1]},
        "runtime_hash":"r","budget":{"reserve_bytes":20*1024**3},
        "min_available_bytes":40*1024**3,"release_proof":True,"guard_events":[]}

def test_tb11_valid_synthetic_report_passes_shape_gate():
    assert validate_profile_report(profile_fixture()) == []

@pytest.mark.parametrize("change,expected",[
    ({"raw_runs":[]},"raw_runs"),({"release_proof":False},"release_proof"),
    ({"guard_events":["reserve_stop"]},"guard_events"),
    ({"min_available_bytes":19*1024**3},"reserve"),({"budget":{}},"budget"),
])
def test_tb11_profile_counterexamples(change,expected):
    report=profile_fixture(); report.update(change)
    assert expected in validate_profile_report(report)

```

- [ ] **Step 2: 执行反例，确认尚缺行为的失败而不是环境错误**

Run: `python -m pytest -q tests/test_tb11_calibrated_switching.py`

尚未实现的边界必须出现对应断言失败；已经满足的反例作为回归保留。缺依赖/网络误连/测试未采集先修正测试环境，不能计作业务 red。

- [ ] **Step 3: 用最小改动满足反例，完成必要接线**

`scripts/image_measurement.py` 的核心内容：

```python
import math
import statistics

def latency_summary(valid_runs):
    if not valid_runs:
        return {"count":0,"p50_ms":None,"p95_ms":None,"range_ms":None}
    values = sorted((r["saved_ns"]-r["submitted_ns"])/1e6 for r in valid_runs)
    return {"count":len(values),"p50_ms":statistics.median(values),
        "p95_ms":values[math.ceil(.95*len(values))-1],
        "range_ms":[values[0],values[-1]]}
```


- [ ] 给 validate_profile_report 增加每轮 profile 顺序、相同 runtime_hash、输入包络实际覆盖、预算正值与版本有效性、采样空洞和原始文件 SHA256 对应验证；JSON schema 通过不等于硬件通过。
- [ ] 根据实测的释放后基线与最大增量、保守裕量签署配置；把稳定窗口/等待上限/样本年龄、有效期及原始证据引用一并写入；加载配置时验证 hash 与有效期。
- [ ] 在最终构建运行 model-switch 命令并记录全部原始事件；如果只标定部分 profile，只启用对应部分并明确剩余未通过，父规格不判完成。

- [ ] **Step 4: 按逐条验收映射验证，并记录原始证据**

| 本票验收条件 | 验证安排 |
| --- | --- |
| 1. 为 fast、standard、high 分别建立覆盖拟支持尺寸/参考数/合成等因素的保守包络；每个拟启用编辑 profile 至少三轮生图→编辑→生图，覆盖冷/热及编辑取消回切。 | profile报告实际输入包络覆盖与runtime/model/workflow哈希；各profile至少3轮真实G→E→G及取消回切。 |
| 2. 交付统一 model-switch 验收命令、原始采样和可阅读报告；记录精确模型/工作流/运行时标识、输入包络和每轮阶段边界。 | model-switch命令输出完整环境/原始JSONL/验证报告，不能只写三条序号。 |
| 3. 真实受测记录满足有效预算/容器边界、MemAvailable 不低于 20GiB，保护器启用且没有触发停服；无可证实的不安全模型重叠。 | 每轮记录最低余量≥20GiB、cgroup边界、guard事件为空且释放证明可追溯。 |
| 4. 将有依据的预算、裕量、稳定窗口、等待上限与启用列表写入有效配置；资源不足演示安全等待/拒绝而非强行完成。 | 加载有效配置实测安全等待/拒绝；记录预算、窗口、等待/时钟配置，不用默认猜测值。 |
| 5. 尚未完成标定的 profile 保持禁用并明确列出；若不能安全建立起始预算，报告阻塞原因，不伪造数值或临时绕过准入。 | no_raw_runs_cannot_enable_profile、全部报告反例；无安全起点时不跑并写inconclusive。 |
| 6. 若不能覆盖全部既有模式，不得宣称父规格完成；标定中发现的问题修复后重跑受影响包络与切换回归。 | fast/standard/high分别验收，未覆盖模式保持关闭并列未完成；受影响包络修复后复测。 |

Run: `python -m pytest --collect-only -q -k tb11_calibrated_switching`

Run: `python -m pytest -q -k tb11_calibrated_switching`

Run: `python -m pytest -q -k "tb11 or tb08 or tb09 or tb10"`

外部演示/复测命令（由本票或其前置提供）：

```bash
python -m scripts.benchmark_images --scenario model-switch --profiles fast,standard,high --cycles 3 --config "<维护者私有配置>" --report-dir "<私有验收目录>"
```

独立演示：对拟启用的每个编辑 profile 执行三轮真实切换并导出报告，再在受控资源不足条件下确认不加载；将任务 ID、曲线及有效配置对应起来。



- [ ] **Step 5: 文档、ADR 与证据同步**

将实际测试输出、受影响回归、失败与恢复步骤写入 OPERATIONS.md；与当前计划对应的 AC 映射逐项填证据。没有实测的项保持未验收，不能只打勾。

- [ ] **Step 6: 独立提交边界 B**

提交范围：其余反例测试、守卫/兼容接线、有效文档；保持本票在前置完成后独立可演示。

```bash
python - <<'PY'
from pathlib import Path
import subprocess
candidates = ["scripts/benchmark_images.py","scripts/image_measurement.py","tests/test_tb11_calibrated_switching.py","OPERATIONS.md","docs/adr/0002-image-resource-admission.md","docs/superpowers/plans/2026-11-14-image-11-calibrated-switching.md"]
paths = [p for p in candidates if Path(p).is_file()]
subprocess.run(["git", "add", "--", *paths], check=True)
PY
git commit -m "test(image): t11 boundaries and recovery"
```

## Rollback / compatibility strategy

停止接纳新图片任务，将问题 profile 禁用，保留旧/新配置与完整曲线；恢复到最近仍有效且已标定的包络。模型/运行时变更导致旧包络失效时保持关闭。

维护过程先停止新工作并保全新增写入；对运行图片定向停止且确认后端空闲。不能回退成跨用户共享访问、关闭保护器或盲目重跑。

## Out of scope

不承诺固定耗时或画质提升；不解释历史事故唯一因果；不把三轮切换替代 8 小时稳定性验收；不做个人配额。

## Verification environment

以下 python 指令在受支持的工程虚拟环境执行。原工作区可用 .venv/bin/python；Windows 使用对应 .venv\\Scripts\\python.exe。新测试尚未创建，未采集到测试不算通过；本轮仅编写计划，不冒充 red/green 或实机验收已执行。

## Measurement baseline and result audit

- 应用 [测量契约](2026-11-14-image-measurement-contract.md)，修改前审核 baseline，完成后执行第11步结果核查。
- 本轮实际 baseline：**not_run**；没有本轮性能/内存标定原始结果，不能报告速度提升、回归或安全参数已成立。
- 现有历史脚本与原始位置、计时边界错误、固定幂等/no-op风险见测量契约；历史数字不作为当前 before。
- 负载/缓存/并发/样本、host/runtime、输出验证、错误计数和复测命令必须写入实际执行记录；比较设置至少每侧5次交替，安全闭环每拟启用profile至少3轮。
- 原始结果存调用者私有唯一 run 目录；报告队列/加载/推理/保存/下载与端到端时间，状态不全则 inconclusive。

## Self-review and execution handoff

- [x] 每个本票验收条件已映射到上表；父规格归属：AC-02、AC-03、AC-04、AC-05、AC-18、AC-20。
- [x] 第一条失败原因与最小实现明确；状态反例为测试代码/实际演示，不只保留图。
- [x] 新签名来自共享契约，当前尚未实现的接口由明确前置/本票交付。
- [x] 边界 A/B 各自带测试与文档；回退不会丢新数据或恢复共享读取。
- [ ] 后续执行者运行 red/green、受影响回归与所需实机验收，填写实际证据后再声明完成。

本次只批准编写和发布计划，不启动产品实现。执行时由用户选择原生或子代理方式；未取得执行授权前不启动实现/部署。
