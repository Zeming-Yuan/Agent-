# T13 macOS 接入：升级个人配置并验收完整恢复链路 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** macOS 用户从现有包平稳升级到个人 Key 和可恢复工具，在实际 Harness 中完成与 Windows 相同的核心流程。

**Architecture:** Consumes: T06 公共恢复/打包和 T11 已标定后端。Produces: make_config(install_dir:str,config_file:str)->dict（client.mac.configure）；macOS 平台专属升级流程；保留 Windows 相同的工具协议。 先读共享执行契约并保留既有兼容边界；本票只交付确认的纵向行为，不扩展为通用重构。

**Tech Stack:** Python、FastAPI、SQLite、httpx、Pillow、stdio MCP；固定 ComfyUI 0.33.2；平台专属脚本按本票列出的操作系统执行。

**Spec:** [父规格 #1](https://github.com/Zeming-Yuan/Agent-/issues/1)；[完整规格](../../specs/2026-11-14-image-service-reliability-and-multiuser.md)；[共享执行契约](2026-11-14-image-execution-contract.md)。执行者必须同时读取三者。

**Ticket:** T13；Blocked by：T11。复用 T11 已标定后端与稳定公共桥接；只改 macOS 专属资源，可与 T12 分别验收。

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

1. 旧包升级：不能覆盖个人日志/结果 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
2. Unicode/空格：合法 JSON/YAML argv → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
3. Python CA 正常但 Harness 不信任：分进程诊断 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
4. Key 轮换与换人：owner 归属正确 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
5. 局域网权限/目录失败：明确原因且可重取 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。

---

## File structure and interfaces

- Create: client/mac/configure.py — macOS 绝对 argv 配置
- Modify: client/mac/install-mac.command — 个人配置升级与日志保全
- Modify: client/mac/README.md — CA、恢复与实际验收
- Create: tests/test_tb13_macos_client.py
- Reuse without parallel edits: client/spark_image_tools.py / 公共构建器

**Consumes / Produces:** Consumes: T06 公共恢复/打包和 T11 已标定后端。Produces: make_config(install_dir:str,config_file:str)->dict（client.mac.configure）；macOS 平台专属升级流程；保留 Windows 相同的工具协议。

## Task 1: 首条用户反例与最小纵向实现

**Files:** 使用上面列出的本票实现文件；首条测试写入 `tests/test_tb13_macos_client.py`。本任务最小实现核心位于 `client/mac/configure.py`。

**Interfaces:** 消费上述输入，产出本票外部行为；新公共签名以 Architecture/共享契约为准，不另起别名。

- [ ] **Step 1: 写第一条失败测试**

```python
from client.mac.configure import make_config

def test_tb13_macos_unicode_paths_are_separate_argv():
    root = "/Users/tester/Applications/图片 工具"
    config = "/Users/tester/个人 配置.json"
    plugin = make_config(root,config)["config"]
    assert plugin["command"] == root+"/.venv/bin/python"
    assert plugin["args"] == [root+"/spark_image_tools.py","--config",config]
    assert plugin["cwd"] == root
```

- [ ] **Step 2: 运行并确认预期失败原因**

Run: `python -m pytest -q tests/test_tb13_macos_client.py`

Expected: 当前只有 shell 中内联的固定 Mac 配置，没有可测试的个人配置模块；之后仍沿用旧共享 Key 或固定输出路径的升级方式也必须失败。 这是执行前预期，不是本轮已取得的测试结果。

- [ ] **Step 3: 最小实现，先让这一条完整路径可工作**

在 `client/mac/configure.py` 应用以下核心，按该文件职责接入真实路由/存储，不替换真实业务层为 mock：

```python
from pathlib import PurePosixPath

def make_config(install_dir,config_file):
    root = PurePosixPath(install_dir)
    config = PurePosixPath(config_file)
    if not root.is_absolute() or not config.is_absolute():
        raise ValueError("absolute macOS paths required")
    return {"id":"mcp-spark-images","name":"@deepseek-ai/dsh-mcp-client",
        "config":{"serverName":"spark_images","transport":"stdio",
            "command":str(root/".venv"/"bin"/"python"),
            "args":[str(root/"spark_image_tools.py"),"--config",str(config)],
            "cwd":str(root),"toolCallTimeoutMs":60000,"failOnStartupError":False}}
```

- [ ] 将旧安装器的插件字符串生成移到可测试的平台函数，输出 JSON 数组片段；升级前校验个人配置并备份，不覆盖原恢复数据库/结果目录。
- [ ] 按私有配置加载用户 Key，不再从共享默认包恢复；明确 Node Harness 与 Python bridge 各自 CA 配置、局域网权限及 image 输入能力。
- [ ] 实际 macOS Harness 登记 OS/Harness/Python 版本并验收生成→编辑→生成、真实阶段、取消、断网/工具重启恢复及图片显示/落盘。

- [ ] **Step 4: 运行首条测试和受影响既有回归**

Run: `python -m pytest -q tests/test_tb13_macos_client.py`

Run: `python -m pytest -q -k "tb13 or tb06 or tb07"`

Expected: 所选测试采集非零、断言通过；任何 HTTP/后端替身错误都解释，不能用 deselect/skip 当完成。

- [ ] **Step 5: 同步文档/ADR**

- [ ] client/mac/README.md：个人包升级/恢复/卸载和 CA 分进程排查
- [ ] OPERATIONS.md：macOS 实际版本、证据与未验收项

- [ ] **Step 6: 独立提交边界 A**

提交范围：首个外部行为、测试和必要文档；不夹带下一票迁移。Git checkout 中选择实际改动文件后执行：

```bash
git add -- client/mac/configure.py client/mac/install-mac.command client/mac/README.md tests/test_tb13_macos_client.py
git commit -m "feat(image): t13 vertical core"
```

非 Git 产品目录使用逐任务审查快照与 SHA256 变更清单；不在此处初始化或推送整个工作区。

## Task 2: 状态反例、完整验收与恢复边界

**Files:** `tests/test_tb13_macos_client.py`、上面列出的责任模块、文档；新增核心位于 `client/mac/install-mac.command`。

**Interfaces:** 延续 Task 1 的命名/字段/返回值；所有异常路径仍以 owner 隔离和同一任务身份为边界。

- [ ] **Step 1: 把 Review Focus 反例写成具体测试**

以下代码与 Task 1 的测试置于同一测试模块，保留该模块已经定义的 import/帮助函数；不是只画状态图：

```python
import json
import pytest
from client.mac.configure import make_config

@pytest.mark.parametrize("root,config",[
    ("/Users/a/图片 工具","/Users/a/个人.json"),
    ("/Applications/Spark Tools","/Users/a/config.json"),
])
def test_tb13_config_roundtrip(root,config):
    data = json.loads(json.dumps([make_config(root,config)],ensure_ascii=False))[0]
    assert data["config"]["args"][-1] == config
    assert "api_key" not in json.dumps(data)

@pytest.mark.parametrize("root,config",[("relative","/a.json"),("/tools","relative.json")])
def test_tb13_relative_paths_rejected(root,config):
    with pytest.raises(ValueError): make_config(root,config)
```

- [ ] **Step 2: 执行反例，确认尚缺行为的失败而不是环境错误**

Run: `python -m pytest -q tests/test_tb13_macos_client.py`

尚未实现的边界必须出现对应断言失败；已经满足的反例作为回归保留。缺依赖/网络误连/测试未采集先修正测试环境，不能计作业务 red。

- [ ] **Step 3: 用最小改动满足反例，完成必要接线**

`client/mac/install-mac.command` 的核心内容：

```bash
#!/bin/bash
set -euo pipefail
root_dir="$(cd "$(dirname "$0")" && pwd)"
python_exec="$(command -v python3)"
"$python_exec" -c 'import sys; raise SystemExit(sys.version_info < (3,11))'
"$python_exec" -m venv "$root_dir/.venv"
"$root_dir/.venv/bin/python" -m pip install -r "$root_dir/requirements.txt"
# Personal configuration and recovery database are intentionally retained.
find "$root_dir" -maxdepth 1 -type f -name 'api_key' -exec chmod 600 {} \;
```


- [ ] 演练本地保存失败后重取、Key 轮换、切换到另一 owner 后旧恢复列表不可见；记录同一 task_id 和后端执行计数。
- [ ] 本票仅修改 macOS 专属资源；公共实现问题沿主干串行修复并双端复验，不 fork 协议。

- [ ] **Step 4: 按逐条验收映射验证，并记录原始证据**

| 本票验收条件 | 验证安排 |
| --- | --- |
| 1. 登记实际 macOS/Harness/Python 版本；现有包升级保留个人结果和恢复信息，不继续默认分发旧共享 Key。 | 旧包升级保全配置/日志/结果，个人Key替换共享默认；登记真实macOS/Harness/Python。 |
| 2. 配置个人 Key、CA、中文/空格路径及自定义输出目录；区分 Python 桥接与 Harness 网络进程的 CA 配置，保持 TLS 校验。 | unicode路径和relative反例；分别验证Python与Harness的CA/局域网权限。 |
| 3. 实际 Harness 完成生图→编辑→生图、阶段/排队显示、取消、断网/工具重启恢复、聊天内图片展示和本地保存。 | 实际Harness跑完整链路并保存脱敏屏幕/图片/任务ID，服务器stdio不替代。 |
| 4. 保存失败后只重取，响应丢失重放同一请求只执行一次；换 owner 不泄露旧恢复列表。 | 保存失败重取、响应丢失只一次推理、换owner日志不可见；Key轮换恢复同tid。 |
| 5. 只改 macOS 专属资产/说明/测试；共享实现变更须先串行整合，不能与 Windows 票同时改同一公共文件。 | diff审查仅macOS专属资源；公共实现变化必须先主干串行，再两端回归。 |

Run: `python -m pytest --collect-only -q -k tb13_macos_client`

Run: `python -m pytest -q -k tb13_macos_client`

Run: `python -m pytest -q -k "tb13 or tb06 or tb07"`

外部演示/复测命令（由本票或其前置提供）：

```bash
python -m client.spark_image_tools --config "<macOS 个人配置文件>"
```

独立演示：在实际 macOS Harness 从旧包升级后运行完整流程并保留脱敏证据；服务器侧 stdio 样例不算本票通过。

平台实机步骤必须在实际 macOS Harness 完成并记录版本、任务 ID、脱敏屏幕和图片哈希；单测/静态配置通过不代替实际平台验收。

- [ ] **Step 5: 文档、ADR 与证据同步**

将实际测试输出、受影响回归、失败与恢复步骤写入 client/mac/README.md；与当前计划对应的 AC 映射逐项填证据。没有实测的项保持未验收，不能只打勾。

- [ ] **Step 6: 独立提交边界 B**

提交范围：其余反例测试、守卫/兼容接线、有效文档；保持本票在前置完成后独立可演示。

```bash
git add -- client/mac/configure.py client/mac/install-mac.command client/mac/README.md tests/test_tb13_macos_client.py
git commit -m "test(image): t13 boundaries and recovery"
```

## Rollback / compatibility strategy

保留结果、请求日志和个人配置，回退平台插件/安装包；继续按本人原任务取图，不能恢复成多人共用 Key 或盲目重新提交。

维护过程先停止新工作并保全新增写入；对运行图片定向停止且确认后端空闲。不能回退成跨用户共享访问、关闭保护器或盲目重跑。

## Out of scope

不改公共服务/协议；不保证所有 macOS 历史版本/Harness；不把 Mac 成功视为 Windows 验收；不新增个人配额。

## Verification environment

以下 python 指令在受支持的工程虚拟环境执行。原工作区可用 .venv/bin/python；Windows 使用对应 .venv\\Scripts\\python.exe。新测试尚未创建，未采集到测试不算通过；本轮仅编写计划，不冒充 red/green 或实机验收已执行。


## Self-review and execution handoff

- [x] 每个本票验收条件已映射到上表；父规格归属：AC-01、AC-06、AC-07、AC-08、AC-09、AC-10、AC-12。
- [x] 第一条失败原因与最小实现明确；状态反例为测试代码/实际演示，不只保留图。
- [x] 新签名来自共享契约，当前尚未实现的接口由明确前置/本票交付。
- [x] 边界 A/B 各自带测试与文档；回退不会丢新数据或恢复共享读取。
- [ ] 后续执行者运行 red/green、受影响回归与所需实机验收，填写实际证据后再声明完成。

本次只批准编写和发布计划，不启动产品实现。执行时由用户选择原生或子代理方式；未取得执行授权前不启动实现/部署。
