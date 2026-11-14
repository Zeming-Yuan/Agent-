# T12 Windows 接入：实际桌面端显示进度、重连并保存图片 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Windows 用户通过自己的实际 Harness 安装/配置 MCP，用个人 Key 生图、编辑、重连取回并显示图片。

**Architecture:** Consumes: T06 公共桥接/打包契约和 T11 已标定后端。Produces: make_config(install_dir:str, config_file:str)->dict（client.windows.configure）；独立 Windows 平台资源；不派生另一套 MCP 协议。 先读共享执行契约并保留既有兼容边界；本票只交付确认的纵向行为，不扩展为通用重构。

**Tech Stack:** Python、FastAPI、SQLite、httpx、Pillow、stdio MCP；固定 ComfyUI 0.33.2；平台专属脚本按本票列出的操作系统执行。

**Spec:** [父规格 #1](https://github.com/Zeming-Yuan/Agent-/issues/1)；[完整规格](../../specs/2026-11-14-image-service-reliability-and-multiuser.md)；[共享执行契约](2026-11-14-image-execution-contract.md)。执行者必须同时读取三者。

**Ticket:** T12；Blocked by：T11。实际桌面验收需要已标定且可安全服务的后端；只改 Windows 专属资源，可与 T13 分别验收。

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

1. Unicode/空格路径：argv 不拆坏 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
2. CA 只给 Python：Harness 网络进程仍需正确配置 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
3. 保存目录不可写：恢复同任务不重生成 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
4. 换人后旧日志：不得显示上一 owner → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。
5. 升级/卸载：保留个人配置、日志和图片 → Task 2 的反例测试/所列真实演示；已有行为也保留回归，不能为制造失败而破坏它。

---

## File structure and interfaces

- Create: client/windows/install-windows.ps1 — Python/venv/个人配置安装
- Create: client/windows/configure.py — Windows 绝对 argv 配置
- Create: client/windows/README.md — 实际 Harness 安装/恢复/卸载
- Create: tests/test_tb12_windows_client.py
- Reuse without parallel edits: client/spark_image_tools.py / 公共构建器

**Consumes / Produces:** Consumes: T06 公共桥接/打包契约和 T11 已标定后端。Produces: make_config(install_dir:str, config_file:str)->dict（client.windows.configure）；独立 Windows 平台资源；不派生另一套 MCP 协议。

## Task 1: 首条用户反例与最小纵向实现

**Files:** 使用上面列出的本票实现文件；首条测试写入 `tests/test_tb12_windows_client.py`。本任务最小实现核心位于 `client/windows/configure.py`。

**Interfaces:** 消费上述输入，产出本票外部行为；新公共签名以 Architecture/共享契约为准，不另起别名。

- [ ] **Step 1: 写第一条失败测试**

```python
from client.windows.configure import make_config

def test_tb12_windows_unicode_paths_are_separate_argv():
    root = r"C:\Users\Tester\图片 工具"
    config = r"C:\Users\Tester\个人 配置.json"
    plugin = make_config(root,config)["config"]
    assert plugin["command"] == root + r"\.venv\Scripts\python.exe"
    assert plugin["args"] == [root+r"\spark_image_tools.py","--config",config]
    assert plugin["transport"] == "stdio"
    assert plugin["cwd"] == root
```

- [ ] **Step 2: 运行并确认预期失败原因**

Run: `python -m pytest -q tests/test_tb12_windows_client.py`

Expected: 当前无 Windows 安装/配置模块；最初 ModuleNotFoundError。后续若把整个命令手工拼成一个字符串或复用 Mac venv 路径，argv/command 断言失败。 这是执行前预期，不是本轮已取得的测试结果。

- [ ] **Step 3: 最小实现，先让这一条完整路径可工作**

在 `client/windows/configure.py` 应用以下核心，按该文件职责接入真实路由/存储，不替换真实业务层为 mock：

```python
from pathlib import PureWindowsPath

def make_config(install_dir,config_file):
    root = PureWindowsPath(install_dir)
    config = PureWindowsPath(config_file)
    if not root.is_absolute() or not config.is_absolute():
        raise ValueError("absolute Windows paths required")
    return {"id":"mcp-spark-images","name":"@deepseek-ai/dsh-mcp-client",
        "config":{"serverName":"spark_images","transport":"stdio",
            "command":str(root/".venv"/"Scripts"/"python.exe"),
            "args":[str(root/"spark_image_tools.py"),"--config",str(config)],
            "cwd":str(root),"toolCallTimeoutMs":60000,"failOnStartupError":False}}
```

- [ ] 平台专属 configure CLI 使用 argparse 生成 JSON 数组（兼容 YAML）插件片段；Key 只在私有配置指向的文件，不能内嵌插件或公开 README。
- [ ] 安装脚本检查退出码、现有配置先备份且不覆盖个人请求日志；使用当前用户 SID 给私有 Key/配置设仅本人 ACL，不改变全局 PowerShell 执行策略。
- [ ] 使用个人 CA 配置 Python bridge，并对实际 Harness 的 Node/其他网络进程按其已登记配置加载 CA；不设 verify=False、不把 ca_file 当系统已信任。

- [ ] **Step 4: 运行首条测试和受影响既有回归**

Run: `python -m pytest -q tests/test_tb12_windows_client.py`

Run: `python -m pytest -q -k "tb12 or tb06 or tb07"`

Expected: 所选测试采集非零、断言通过；任何 HTTP/后端替身错误都解释，不能用 deselect/skip 当完成。

- [ ] **Step 5: 同步文档/ADR**

- [ ] client/windows/README.md：版本、安装/升级、CA、工具列表、图片输入能力、恢复及卸载
- [ ] OPERATIONS.md：Windows 实际验收记录与未通过项

- [ ] **Step 6: 独立提交边界 A**

提交范围：首个外部行为、测试和必要文档；不夹带下一票迁移。Git checkout 中选择实际改动文件后执行：

```bash
git add -- client/windows/install-windows.ps1 client/windows/configure.py client/windows/README.md tests/test_tb12_windows_client.py
git commit -m "feat(image): t12 vertical core"
```

非 Git 产品目录使用逐任务审查快照与 SHA256 变更清单；不在此处初始化或推送整个工作区。

## Task 2: 状态反例、完整验收与恢复边界

**Files:** `tests/test_tb12_windows_client.py`、上面列出的责任模块、文档；新增核心位于 `client/windows/install-windows.ps1`。

**Interfaces:** 延续 Task 1 的命名/字段/返回值；所有异常路径仍以 owner 隔离和同一任务身份为边界。

- [ ] **Step 1: 把 Review Focus 反例写成具体测试**

以下代码与 Task 1 的测试置于同一测试模块，保留该模块已经定义的 import/帮助函数；不是只画状态图：

```python
import json
import pytest
from client.windows.configure import make_config

@pytest.mark.parametrize("root,config",[
    (r"C:\A B\图片",r"C:\A B\个人.json"),
    (r"D:\工具",r"D:\配置.json"),
])
def test_tb12_config_roundtrip(root,config):
    plugin = make_config(root,config)
    decoded = json.loads(json.dumps([plugin],ensure_ascii=False))[0]
    assert decoded["config"]["args"][-1] == config
    assert "api_key" not in json.dumps(plugin)

@pytest.mark.parametrize("root,config",[("relative",r"C:\a.json"),(r"C:\tools","a.json")])
def test_tb12_relative_install_paths_rejected(root,config):
    with pytest.raises(ValueError): make_config(root,config)
```

- [ ] **Step 2: 执行反例，确认尚缺行为的失败而不是环境错误**

Run: `python -m pytest -q tests/test_tb12_windows_client.py`

尚未实现的边界必须出现对应断言失败；已经满足的反例作为回归保留。缺依赖/网络误连/测试未采集先修正测试环境，不能计作业务 red。

- [ ] **Step 3: 用最小改动满足反例，完成必要接线**

`client/windows/install-windows.ps1` 的核心内容：

```powershell
param([Parameter(Mandatory=$true)][string]$InstallDir)
$ErrorActionPreference = "Stop"
$Root = [System.IO.Path]::GetFullPath($InstallDir)
& py -3 -c "import sys; raise SystemExit(sys.version_info < (3,11))"
if ($LASTEXITCODE -ne 0) { throw "Python 3.11+ required" }
& py -3 -m venv (Join-Path $Root ".venv")
if ($LASTEXITCODE -ne 0) { throw "venv creation failed" }
$Python = Join-Path $Root ".venv\Scripts\python.exe"
& $Python -m pip install -r (Join-Path $Root "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "dependency installation failed" }
```


- [ ] 在实际 Windows/Harness 版本运行生成→编辑→生成、取消、断网、工具重启、响应丢失恢复和不可写目录取图重试；保留任务 ID、图片 SHA256 与脱敏屏幕证据，服务器 stdio 不代替此步骤。
- [ ] 如果发现公共桥接或构建器缺陷，先暂停平台票，沿公共主干串行修复并回归，再复验两个平台；本票不与 T13 同改公共文件。

- [ ] **Step 4: 按逐条验收映射验证，并记录原始证据**

| 本票验收条件 | 验证安排 |
| --- | --- |
| 1. 登记实际 Windows/Harness/Python 版本；提供可复现安装和更新/卸载说明，不以 Unix shell 或 Mac 目录为前置条件。 | 在实际Windows登记OS/Harness/Python并执行安装/升级/卸载保全演练；PowerShell失败码非零。 |
| 2. 个人 Key、CA、含空格/中文路径、自定义输出目录可用；TLS 校验不被绕过，凭证不进入公开包/报告。 | unicode路径及relative反例，真实CA校验和私有Key权限；错误CA应明确失败而非绕过。 |
| 3. 实际 Harness 完成生图→编辑→生图、显示阶段与前方单数、显式取消、断网/重启恢复以及聊天内图片展示与落盘。 | 实际Harness生成→编辑→生成、阶段/排队、取消、断网/重启恢复、聊天图片及落盘证据。 |
| 4. 验证响应丢失后找回同一任务、本地保存失败后只重取；换 owner 不展示之前的恢复列表。 | MCP重放/保存失败/换owner场景实机执行，与同tid和后端计数对应。 |
| 5. 只改 Windows 专属资产/说明/测试；公共桥接或公共打包若发现缺陷，先串行整合修复，再继续本票验收，不复制成另一套协议。 | diff审查平台票只触及Windows专属资源；公共修复先串行整合并双端复验。 |

Run: `python -m pytest --collect-only -q -k tb12_windows_client`

Run: `python -m pytest -q -k tb12_windows_client`

Run: `python -m pytest -q -k "tb12 or tb06 or tb07"`

外部演示/复测命令（由本票或其前置提供）：

```bash
python -m client.spark_image_tools --config "<Windows 个人配置文件>"
```

独立演示：在实际 Windows 桌面 Harness 中执行上述完整流程，保存平台信息、任务 ID 和脱敏截图；Python 单独取图不能替代 Harness 展示验收。

平台实机步骤必须在实际 Windows Harness 完成并记录版本、任务 ID、脱敏屏幕和图片哈希；单测/静态配置通过不代替实际平台验收。

- [ ] **Step 5: 文档、ADR 与证据同步**

将实际测试输出、受影响回归、失败与恢复步骤写入 client/windows/README.md；与当前计划对应的 AC 映射逐项填证据。没有实测的项保持未验收，不能只打勾。

- [ ] **Step 6: 独立提交边界 B**

提交范围：其余反例测试、守卫/兼容接线、有效文档；保持本票在前置完成后独立可演示。

```bash
git add -- client/windows/install-windows.ps1 client/windows/configure.py client/windows/README.md tests/test_tb12_windows_client.py
git commit -m "test(image): t12 boundaries and recovery"
```

## Rollback / compatibility strategy

先保留本地请求日志、个人配置与已保存图片，再回退平台包/插件配置；仍通过本人任务列表取回服务端结果，不删除任务后重提。

维护过程先停止新工作并保全新增写入；对运行图片定向停止且确认后端空闲。不能回退成跨用户共享访问、关闭保护器或盲目重跑。

## Out of scope

不改公共服务或公共桥接协议；不保证所有 Windows 历史版本/Harness；不新增个人配额或新桌面应用。

## Verification environment

以下 python 指令在受支持的工程虚拟环境执行。原工作区可用 .venv/bin/python；Windows 使用对应 .venv\\Scripts\\python.exe。新测试尚未创建，未采集到测试不算通过；本轮仅编写计划，不冒充 red/green 或实机验收已执行。


## Self-review and execution handoff

- [x] 每个本票验收条件已映射到上表；父规格归属：AC-01、AC-06、AC-07、AC-08、AC-09、AC-10、AC-12。
- [x] 第一条失败原因与最小实现明确；状态反例为测试代码/实际演示，不只保留图。
- [x] 新签名来自共享契约，当前尚未实现的接口由明确前置/本票交付。
- [x] 边界 A/B 各自带测试与文档；回退不会丢新数据或恢复共享读取。
- [ ] 后续执行者运行 red/green、受影响回归与所需实机验收，填写实际证据后再声明完成。

本次只批准编写和发布计划，不启动产品实现。执行时由用户选择原生或子代理方式；未取得执行授权前不启动实现/部署。
