# T14 联合验收与恢复演练：两人双端在同一服务上完成闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 两位真实使用者在 Windows/macOS 同时工作时，素材/结果隔离、轮转顺序、断线恢复与安全模型切换共同成立，维护者能按演练过的边界恢复服务。

**Architecture:** Consumes: T12/T13 实际双端证据、T11 profile 报告与迁移/恢复结果。Produces: check_acceptance(report)->list[str]；CLI --report <file> 非零拒绝缺证据；交付记录关联 AC-01..AC-20，不自动修改父 Issue。 先读共享执行契约并保留既有兼容边界；本票只交付确认的纵向行为，不扩展为通用重构。

**Tech Stack:** Python、FastAPI、SQLite、httpx、Pillow、stdio MCP；固定 ComfyUI 0.33.2；平台专属脚本按本票列出的操作系统执行。

**Spec:** [父规格 #1](https://github.com/Zeming-Yuan/Agent-/issues/1)；[完整规格](../../specs/2026-11-14-image-service-reliability-and-multiuser.md)；[共享执行契约](2026-11-14-image-execution-contract.md)。执行者必须同时读取三者。

**Ticket:** T14；Blocked by：T12、T13。必须两端各自通过后，才能宣称 Windows/macOS、多身份及同一服务的组合体验可交付。

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

1. 只有一端或服务器 stdio：不能通过双端门禁 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
2. 任一 AC 无证据/未运行：不能标成功 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
3. 同一服务混用 owner：组合时仍需隔离 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
4. 恢复覆盖新写入：必须保全并核对 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
5. 最终构建变化：旧运行时包络不能直接复用 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。

---

## File structure and interfaces

- Create: scripts/check_image_acceptance.py — 证据完整性门禁 CLI
- Create: tests/test_tb14_joint_acceptance.py
- Modify: OPERATIONS.md — 双端同服务交付、故障恢复与证据索引
- Modify: docs/IMAGE-SERVICE.md — 最终外部契约及未验收边界
- Reuse: 全部最终实现与私有实机报告，不新增大功能

**Consumes / Produces:** Consumes: T12/T13 实际双端证据、T11 profile 报告与迁移/恢复结果。Produces: check_acceptance(report)->list[str]；CLI --report <file> 非零拒绝缺证据；交付记录关联 AC-01..AC-20，不自动修改父 Issue。

## Task 1: 首条用户反例与最小纵向实现

**Files:** 使用上面列出的本票实现文件；首条测试写入 `tests/test_tb14_joint_acceptance.py`。本任务最小实现核心位于 `scripts/check_image_acceptance.py`。

**Interfaces:** 消费上述输入，产出本票外部行为；新公共签名以 Architecture/共享契约为准，不另起别名。

- [ ] **Step 1: 写第一条失败测试**

```python
from scripts.check_image_acceptance import check_acceptance

def test_tb14_macos_only_cannot_pass_joint_acceptance():
    report = {"criteria":{}, "platforms":{"macos":{"actual_harness":True,
        "os_version":"fixture","harness_version":"fixture","task_ids":["task-a"],
        "evidence":["mac-proof"]}}, "profiles":{}}
    errors = check_acceptance(report)
    assert "windows.actual_harness" in errors
    assert "AC-01" in errors
```

- [ ] **Step 2: 运行并确认预期失败原因**

Run: `python -m pytest -q tests/test_tb14_joint_acceptance.py`

Expected: 尚无组合验收门禁；必须因缺少真实 Windows 证据和 AC 覆盖失败，不能从一张 Mac 图片或服务器 stdio 报告推导双端通过。 这是执行前预期，不是本轮已取得的测试结果。

- [ ] **Step 3: 最小实现，先让这一条完整路径可工作**

在 `scripts/check_image_acceptance.py` 应用以下核心，按该文件职责接入真实路由/存储，不替换真实业务层为 mock：

```python
def check_acceptance(report):
    errors = []
    criteria = report.get("criteria",{})
    for n in range(1,21):
        key = f"AC-{n:02}"
        item = criteria.get(key,{})
        if item.get("passed") is not True or not item.get("evidence"):
            errors.append(key)
    platforms = report.get("platforms",{})
    for platform in ("windows","macos"):
        item = platforms.get(platform,{})
        if item.get("actual_harness") is not True:
            errors.append(platform+".actual_harness")
        for key in ("os_version","harness_version","task_ids","evidence"):
            if not item.get(key): errors.append(platform+"."+key)
    if not report.get("profiles"):
        errors.append("profiles")
    return errors
```

- [ ] 扩展检查器验证所有引用原始报告实际存在/哈希一致、每个 profile 的 validate_profile_report 无错误，且 runtime_hash 与最终构建匹配；不能仅验证字段非空。
- [ ] 按 AC-01..20 逐项执行：两人一端各用自己的 Key，在同一服务混合提交；检查跨人读/删/引用/取消均拒绝、同键各自独立、公平顺序、阶段、取消清理与断线取回。
- [ ] 受控演练后端离线、网关重启、未知提交和资源不足，记录实际任务与后端执行计数；恢复前停新单、确认后端空闲、保全新增数据，不能借恢复覆盖任务或重新推理。

- [ ] **Step 4: 运行首条测试和受影响既有回归**

Run: `python -m pytest -q tests/test_tb14_joint_acceptance.py`

Run: `python -m pytest -q`

Expected: 所选测试采集非零、断言通过；任何 HTTP/后端替身错误都解释，不能用 deselect/skip 当完成。

- [ ] **Step 5: 同步文档/ADR**

- [ ] OPERATIONS.md：联合验收逐 AC 证据、有效配置、恢复演练及交付边界
- [ ] docs/IMAGE-SERVICE.md：最终 API/MCP/双端契约
- [ ] 两份 ADR：记录实测状态；未通过模式如实保留未启用

- [ ] **Step 6: 独立提交边界 A**

提交范围：首个外部行为、测试和必要文档；不夹带下一票迁移。Git checkout 中选择实际改动文件后执行：

```bash
python - <<'PY'
from pathlib import Path
import subprocess
candidates = ["scripts/check_image_acceptance.py","tests/test_tb14_joint_acceptance.py","OPERATIONS.md","docs/IMAGE-SERVICE.md"]
paths = [p for p in candidates if Path(p).is_file()]
subprocess.run(["git", "add", "--", *paths], check=True)
PY
git commit -m "feat(image): t14 vertical core"
```

非 Git 产品目录使用逐任务审查快照与 SHA256 变更清单；不在此处初始化或推送整个工作区。

## Task 2: 状态反例、完整验收与恢复边界

**Files:** `tests/test_tb14_joint_acceptance.py`、上面列出的责任模块、文档；新增核心位于 `scripts/check_image_acceptance.py`。

**Interfaces:** 延续 Task 1 的命名/字段/返回值；所有异常路径仍以 owner 隔离和同一任务身份为边界。

- [ ] **Step 1: 把 Review Focus 反例写成具体测试**

以下代码与 Task 1 的测试置于同一测试模块，保留该模块已经定义的 import/帮助函数；不是只画状态图：

```python
import pytest
from scripts.check_image_acceptance import check_acceptance

@pytest.mark.parametrize("missing",["windows","macos"])
def test_tb14_each_platform_required(missing):
    report = {"criteria":{}, "platforms":{}, "profiles":{}}
    report["platforms"][missing] = {"actual_harness":False}
    assert missing+".actual_harness" in check_acceptance(report)

@pytest.mark.parametrize("n",[1,7,11,16,20])
def test_tb14_each_ac_requires_actual_evidence(n):
    key = f"AC-{n:02}"
    report = {"criteria":{key:{"passed":True,"evidence":[]}},
              "platforms":{}, "profiles":{}}
    assert key in check_acceptance(report)
```

- [ ] **Step 2: 执行反例，确认尚缺行为的失败而不是环境错误**

Run: `python -m pytest -q tests/test_tb14_joint_acceptance.py`

尚未实现的边界必须出现对应断言失败；已经满足的反例作为回归保留。缺依赖/网络误连/测试未采集先修正测试环境，不能计作业务 red。

- [ ] **Step 3: 用最小改动满足反例，完成必要接线**

`scripts/check_image_acceptance.py` 的核心内容：

```python
import argparse
import json
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report",required=True)
    args = parser.parse_args()
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    errors = check_acceptance(report)
    print(json.dumps({"status":"failed" if errors else "passed","errors":errors},ensure_ascii=False))
    raise SystemExit(1 if errors else 0)

if __name__ == "__main__":
    main()
```


- [ ] 从最终构建执行完整 pytest；仅对代码/配置变化影响的 profile 复验标定与双端链路，基线不匹配则重新标定，不无依据重复扩大测试。
- [ ] 在私有报告填写实际平台/版本、全部启用模式、有效参数、失败/未验收项及原始结果位置；使用 check_image_acceptance CLI，任一必要项缺失保持失败。父规格只被引用，不由本票自动关闭。

- [ ] **Step 4: 按逐条验收映射验证，并记录原始证据**

| 本票验收条件 | 验证安排 |
| --- | --- |
| 1. 按父规格 AC-01 至 AC-20 逐项关联证据；两人双端并用、同键请求、跨人访问拒绝、轮转与真实取图全部演示。 | 逐AC私有证据清单与check_acceptance；两人同服务、跨人拒绝、同键独立、轮转和图片回取。 |
| 2. 演练后端离线、网关重启、提交结果未知、资源不足、取消与完成竞态；不出现重复推理、越权、孤儿任务或失联结果。 | 受控故障演练：后端离线/重启/未知提交/资源不足/取消竞态，核对后端唯一执行计数。 |
| 3. 重复验证旧数据接管、Key 撤销/轮换及一致性恢复；恢复前停接单并保全新写入，不回滚成无归属共享访问。 | 迁移副本＋备份/新写入保全演练，撤销/轮换Key和legacy接管均可恢复。 |
| 4. 在最终构建运行完整回归并按需重验受代码/配置变化影响的内存包络；无关已通过项不反复扩测。 | 最终构建完整pytest；runtime改变仅对受影响包络和链路重测。 |
| 5. 交付实际平台/版本、已启用全部模式、有效资源参数、未验收项与可执行恢复说明；任一必需平台/profile 未通过则不宣称父规格完成。 | Windows/macOS及全部拟支持profile证据缺一即拒绝交付；报告失败/未验收项。 |
| 6. 本票只记录交付验收，不自动关闭或改写父规格 Issue；是否标记父规格完成另按后续授权处理。 | 只引用父Issue；发布/验证脚本测试不会关闭或修改父规格。 |

Run: `python -m pytest --collect-only -q -k tb14_joint_acceptance`

Run: `python -m pytest -q -k tb14_joint_acceptance`

Run: `python -m pytest -q`

外部演示/复测命令（由本票或其前置提供）：

```bash
python -m pytest -q
```

独立演示：两位使用者在同一后端各使用一端完成生成/编辑、取消与恢复，互取对方任务失败；维护者据操作说明完成一次受控故障恢复并核对所有原任务。



- [ ] **Step 5: 文档、ADR 与证据同步**

将实际测试输出、受影响回归、失败与恢复步骤写入 OPERATIONS.md；与当前计划对应的 AC 映射逐项填证据。没有实测的项保持未验收，不能只打勾。

- [ ] **Step 6: 独立提交边界 B**

提交范围：其余反例测试、守卫/兼容接线、有效文档；保持本票在前置完成后独立可演示。

```bash
python - <<'PY'
from pathlib import Path
import subprocess
candidates = ["scripts/check_image_acceptance.py","tests/test_tb14_joint_acceptance.py","OPERATIONS.md","docs/IMAGE-SERVICE.md"]
paths = [p for p in candidates if Path(p).is_file()]
subprocess.run(["git", "add", "--", *paths], check=True)
PY
git commit -m "test(image): t14 boundaries and recovery"
```

## Rollback / compatibility strategy

暂停新工作、定向停止并确认后端空闲，保全任务/文件/凭证映射与证据；回退到最后可识别 owner 且预算有效的版本，未验证的模式/平台保持关闭。

维护过程先停止新工作并保全新增写入；对运行图片定向停止且确认后端空闲。不能回退成跨用户共享访问、关闭保护器或盲目重跑。

## Out of scope

不实现遗漏的大功能、不增加配额、不更换模型、不新增 8 小时验收或画质对标；不自行关闭父规格。

## Verification environment

以下 python 指令在受支持的工程虚拟环境执行。原工作区可用 .venv/bin/python；Windows 使用对应 .venv\\Scripts\\python.exe。新测试尚未创建，未采集到测试不算通过；本轮仅编写计划，不冒充 red/green 或实机验收已执行。

## Measurement baseline and result audit

- 应用 [测量契约](2026-11-14-image-measurement-contract.md)，修改前审核 baseline，完成后执行第11步结果核查。
- 本轮实际 baseline：**not_run**；没有本轮性能/内存标定原始结果，不能报告速度提升、回归或安全参数已成立。
- 现有历史脚本与原始位置、计时边界错误、固定幂等/no-op风险见测量契约；历史数字不作为当前 before。
- 负载/缓存/并发/样本、host/runtime、输出验证、错误计数和复测命令必须写入实际执行记录；比较设置至少每侧5次交替，安全闭环每拟启用profile至少3轮。
- 原始结果存调用者私有唯一 run 目录；报告队列/加载/推理/保存/下载与端到端时间，状态不全则 inconclusive。

## Self-review and execution handoff

- [x] 每个本票验收条件已映射到上表；父规格归属：AC-01、AC-02、AC-03、AC-04、AC-05、AC-06、AC-07、AC-08、AC-09、AC-10、AC-11、AC-12、AC-13、AC-14、AC-15、AC-16、AC-17、AC-18、AC-19、AC-20。
- [x] 第一条失败原因与最小实现明确；状态反例为测试代码/实际演示，不只保留图。
- [x] 新签名来自共享契约，当前尚未实现的接口由明确前置/本票交付。
- [x] 边界 A/B 各自带测试与文档；回退不会丢新数据或恢复共享读取。
- [ ] 后续执行者运行 red/green、受影响回归与所需实机验收，填写实际证据后再声明完成。

本次只批准编写和发布计划，不启动产品实现。执行时由用户选择原生或子代理方式；未取得执行授权前不启动实现/部署。

## 正向与最终构建反例

```python
from scripts.check_image_acceptance import check_acceptance

def test_tb14_minimal_complete_shape_passes_only_shape_gate():
    platforms={p:{"actual_harness":True,"os_version":"test","harness_version":"test",
        "task_ids":["synthetic"],"evidence":["synthetic-proof"]} for p in ("windows","macos")}
    report={"criteria":{f"AC-{n:02}":{"passed":True,"evidence":["synthetic"]} for n in range(1,21)},
            "platforms":platforms,"profiles":{"fast":{"runtime_hash":"test"}}}
    assert check_acceptance(report)==[]

def test_tb14_empty_profiles_is_not_delivery():
    report={"criteria":{},"platforms":{},"profiles":{}}
    assert "profiles" in check_acceptance(report)
```

上面的 synthetic 只验证校验器字段逻辑，绝不能作为真实交付证据。Task 2 扩展后的实际 CLI 还要加载原始报告、逐 profile 校验、校验文件哈希/运行时与真实图片证据；对应集成测试用临时真实报告文件，先修改其中一个哈希和运行时，断言 CLI 非零退出。
