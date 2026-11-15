# Issue #7 / T06 MCP 恢复验收记录

用户确认固定基线 `45fa55afde3cbe97549f89ccb18eb71c5e677b68`；受控源码 checkout 为 `/home/clusteradmin/.codex/workspaces/agent-mm-issue-2-20261115`，分支 `feat/issue-7-mcp-resume`。前置 #6 已关闭。本票只推进公共客户端离线实现，不部署、不推送、不发行真实 Key、不操作 GPU。

测试 seam 已经用户确认：公共 MCP call_tool / 真实 stdio → HTTP 鉴权、Store、SQLite、worker → 下载与原子保存，以及个人包构建入口。只替换外部推理和明确的网络/文件故障边界；stdio 验收使用临时 CA 和真实回环 HTTPS。

## 逐条验收映射

| #7 条件 | 自动化证据 | 边界 |
| --- | --- | --- |
| 1. 首次提交前持久化、重试复用、新意图新标识 | 01 RED 缺 journal_path → GREEN；真实 MCP 接纳后丢响应、重建桥接仍同 task_id。HTTP POST 前通过独立 RequestJournal.pending 读到已提交标识；新意图与冲突回归。a-id RED → GREEN 拒绝空值/超长/控制字符/非ASCII；08 accepted 不覆盖原任务。 | 跨调用恢复显式传原 request_id，不按内容猜测意图。本地日志丢失时按服务端任务列表找回。 |
| 2. 生成、编辑、素材恢复按 owner 幂等，推理一次 | 02 RED（编辑缺参数、前景随机上传ID导致指纹冲突）→ GREEN；两种实际 call_tool 重启复用原素材；删除素材后同内容重传仍同任务，backend.jobs=1。并发同键及冲突输入回归保持一条映射/一次推理。 | 首次 02-invalid-foreground 是无效不透明素材夹具，保留但不计作业务 RED。没有真实模型或性能结论。 |
| 3. 本地丢失/换人/换服务/同人换Key | 03 RED 编辑 request_id 被忽略 → GREEN；实际 MCP 列表/状态/分页。同 owner 新Key恢复原映射；B列表不含A；另一个服务的本地分区为空；删除journal仍从服务端恢复。跨人任务/游标404，撤销Key401。 | 测试将两个服务域名送到同一真实鉴权应用，独立验证本地分区；不借此宣称跨服务同步。 |
| 4. 下载保存故障不重生成，返回真实图片 | 04 四项 RED（截断PNG、权限、fsync磁盘、目录）→ GREEN；网络故障为既有回归。旧目标不变、临时文件清理、服务端completed不变，修复后同fid/PNG/MCP ImageContent，任务POST与后端工作计数不变。实际stdio也修复真实阻塞目录后取图。 | 磁盘满/权限在系统文件边界确定性注入；真实目录错误另有进程级验收。物理磁盘满/Windows ACL未验证。删除结果404且不重跑。 |
| 5. 显式个人配置和平台资源，不用全局Key、不打包日志 | 05 旧构建器导入试读全局Key → 显式 build_bundle API；包精确条目、指定个人Key、临时CA、公共模块和所选资源。独立目录真实stdio启动。06 伪装为README的其他Key资源 RED → 同扩展白名单 GREEN。新输出排他、包0600；journal不含测试Key；URL拒绝凭证/query/fragment。 | 测试仅临时随机或明确合成凭证，未读取生产Key；资源是显式选择的受信任脚本/说明，不能把秘密嵌入其中。 |
| 6. 公共契约稳定供后续平台接入 | 固定 build_bundle(config_path,platform_assets,output_path)；根wrapper转入唯一公共client实现，包含request_journal与统一依赖。5个MCP工具/生成编辑request_id schema。B审查路径别名覆盖 RED → GREEN，保护解压后的公共入口。 | T12/T13只提供平台资源；实际Windows/macOS安装器和Harness验收仍归 #13/#14，联合实机恢复归 #15。 |

## 独立 stdio 验收

`test_tb06_mcp_resume_stdio_kill_restart_and_save_recovery` 启动真实临时 HTTPS 网关、鉴权、Store、SQLite、worker，仅外部图片后端使用替身。构建个人zip并在源码之外解压，无源码 PYTHONPATH，从无关cwd启动实际MCP子进程。

HTTP接纳成功但响应尚未发回时kill桥接；重启后的不同PID通过list_image_tasks读到request_id及task_id=null，并从服务端列表找到原任务。用原request_id重放返回同ID。文件占用保存目录时get_image_task报错；修复目录，再调用返回真实ImageContent且保存相同PNG。后端工作计数为1，journal中无测试Key。该测试是Linux stdio验证，不能替代Windows/macOS实际桌面Harness。

## TDD、审查和验证

切片A提交 `735df49`、`ca5e2ef`。初审 Standards 两项（CLI导入、空request_id），Spec 一项（空request_id）；均有独立RED→GREEN并复审为0/0，见review-a.md。初始首条及已有回归3passed，修复后8passed。

切片B提交 `4b6af14`、`de970c0`。两轴初审各发现一个P2：`./spark_image_tools.py`能在解压时覆盖公共入口。b-review-path-red记录4失败/1既有守卫通过；修复后7项包检查通过，b-review-affected为66passed。后续复审发现Windows末尾点/空格别名残留，新增7项RED→GREEN，并补2项文件作为目录前缀的RED→GREEN；包检查16passed。最终独立复审另见review-b.md；尚未收到结论时不得以此记录当作审查通过。

05 RED体现旧构建器隐式读取全局Key的错误行为：受控checkout没有该Key，未读取任何真实全局凭证。02无效夹具单独保留。原始测试输出只归一化行尾空白，保留失败与成功事实。

命令来自README和T06计划，在既有受支持的产品虚拟环境执行：

```bash
python -m pytest --collect-only -q -k tb06_mcp_resume
python -m pytest -q -k tb06_mcp_resume
python -m pytest -q -k "tb06 or bridge_returns_real_mcp_image_content"
python -m pytest -q tests/test_tb06_mcp_resume.py tests/test_tb06_mcp_stdio.py tests/test_image_bridge.py tests/test_tb05_server_resume.py
```

修复前b-collect为26项，b-affected-before-review为61passed。第一轮路径守卫后b-review-affected为66passed；完整跨平台名称守卫后final-collect为40项，b-final-affected为75passed。均有一项既有Starlette/AnyIO弃用警告。最终交付后复验另行记录，不以旧计数替代。

N/A（未配置）：类型检查、静态lint、构建CI、Compose、seed、安全扫描、变异门禁。包构建及真实stdio由上述测试验证，未执行新环境依赖安装或平台安装器。按用户要求没有跑全套测试/完整门禁。

未验证：生产发布与备份/恢复/回滚、真实模型、20GiB和内存标定、Windows/macOS实际Harness；由既有 #4/#5/#12–#15 承接。父规格保持OPEN，不改写其验收状态。本票无服务端数据库迁移、配额、模型或调度改动。

## 交付与回退

向原非Git产品目录交付前，逐路径核对基线内容，再选择性复制已审查代码、测试、文档和脱敏证据，以SHA256复核。不初始化或全量上传产品，不复制私有运行数据。实际交付结果见下文或sync-manifest.json。

回退先停止新创作，保留客户端journal与服务端最新DB/files/注册表和撤销记录，按既有运维要求确认后端清理。仅使用保留owner及请求映射的包/服务版本；可按已知任务ID直接鉴权查询/下载。不得删日志后自动重提、用旧库覆盖新增写入、恢复共享访问或盲目重跑失败推理。没有不可逆迁移；后续平台/硬件工作已有对应ticket。

## 最终源码审查与验证

最终实现提交8b1a7d6，切片A/B均已独立双轴复审至0/0；B两位reviewer分别从固定提交归档运行16项包检查通过。75项受影响测试通过、40项T06已采集，保留一项既有依赖弃用警告。无未处理的重要问题或deferred minor；不扩展为完整规格/生产/双端实机完成。
