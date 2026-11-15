# 运行、排查和回退

本项目目录 `/home/clusteradmin/Desktop/Agent多模态服务`（Spark02）；Spark01 专用目录 `/home/spark01/agent-multimodal-service`。不修改其他项目或已有模型网关。

## 当前状态：2026-11-14 为视频释放内存，暂不运行视频

用户要求关闭本项目模型和无用内存占用，为两台 Spark 的现有 LTX 生产流程腾出资源。以下当前状态覆盖本文后续同日的历史恢复记录：

- Spark01：`agent-mm-main`、`agent-mm-main-memory-guard` 已停止并 disable。
- Spark02：`agent-mm-image`、`agent-mm-image-memory-guard`、`agent-mm-gateway`、`agent-mm-https`、`agent-mm-tunnel` 已停止并 disable；Whisper/Omni 继续保持停止及 disable。图像容器在停止等待后退出137，已确认不再运行；不将此次退出认定为内核OOM。
- 用户随后明确“不用跑，你把内存释放出来就行”：立即停止刚启动的两台分段验证任务及其采样器，停用两台 `ltx-worker`、`ltx-resource-guard` 并恢复 disable；运行准入文件移回原 `ltx-worker.enable.paused-agent-mm-20261114`。Spark02 `ltx-api` 已停止，保留原 enabled 配置。视频权重随worker退出释放。
- 保留现有 LTX 温度、资源和单节点串行保护。保留 FDE 共享 embedding、其他业务、桌面应用、模型文件及输出数据。

停止本项目后、LTX 权重加载前，MemAvailable 从 Spark01 56.22GiB 增至94.18GiB（释放37.96GiB），Spark02 从52.89GiB增至95.58GiB（释放42.69GiB）。GB10 使用统一内存，不把GPU统计与系统内存相加；文件缓存已包含在可回收余量中，无需额外清空缓存或关闭交换分区。

短暂恢复API前已备份 SQLite 任务记录；当时数据库没有 queued/running 任务，最近11.11批次的 completion-state 记录为 succeeded（24段、4条总片）。没有重新提交这些已完成任务。两台720×1280、30fps、49帧验证分段在权重加载期间按用户指示终止，未完成，不宣称实际生成或整批验收通过。操作及最终内存快照保存到 `evidence/video-resource-switch-20261114/`。

未来需要运行视频时，先确认资源余量，将对应节点准入文件移回 `ltx-worker.enable`，再启用两台 `ltx-worker`/`ltx-resource-guard`，按实际队列入口决定是否启动Spark02 `ltx-api`。不要让聊天、图像和视频权重同时常驻。原开机启用及停止命令见下文历史记录；当前以本节状态为准。

## 服务

Spark02 的 systemd 用户服务：

- `agent-mm-https`：Caddy 私有 CA，监听 `192.168.10.77:18443`。
- `agent-mm-gateway`：统一网关，回环 `18008`，Docker 私有 runtime 目录持久化附件和 SQLite 任务状态。
- `agent-mm-tunnel`：SSH 加密转发 `127.0.0.1:18010` → Spark01 的模型回环 `18010`。
- `agent-mm-whisper` / `agent-mm-omni`：GPU 后端，回环 `18011` / `18012`，同一固定 NVIDIA 基础镜像派生运行环境，关闭 Omni 语音生成分支。

Spark01 的 `agent-mm-main`：固定 ARM64 vLLM 0.28 镜像 ID，Qwen3.6 NVFP4；具体启动参数在 `deploy/run-main.sh`。默认短请求关闭思考。

```bash
cd /home/clusteradmin/Desktop/Agent多模态服务
python3 scripts/status.py
systemctl --user status agent-mm-gateway agent-mm-whisper agent-mm-omni agent-mm-https
journalctl --user -u agent-mm-gateway -n 80 --no-pager
ssh spark01 'systemctl --user status agent-mm-main; journalctl --user -u agent-mm-main -n 60 --no-pager'
```

两端用户的 `Linger=yes` 已确认，用户服务已开机启用；未对承载现有业务的机器执行整机重启验收。容器仅由 systemd 管理，不另设 Docker restart 策略。

## 下载与版本

Omni 官方 Qwen ModelScope 镜像分片哈希与固定 Hugging Face 提交逐一相同。完成标记 `/data/models/huggingface/Qwen2.5-Omni-7B/.verified.json` 只有完整权重校验后生成。镜像获取和权重获取的日志在对应 `agent-mm-fetch-main-image` / `agent-mm-download-omni-mirror` journal 中；下载不依赖聊天工具会话编号。

Spark01 的 Docker 守护进程下载 CDN 时出现 TLS 超时；Spark02 的全局 Docker 代理也不修改。`scripts/fetch_main_image.py` 直接获取固定官方 manifest，逐个 blob 校验哈希后生成 Docker archive，再传至 Spark01 `docker load`。镜像 ID/原始摘要记录在 evidence。不要把缓存来源或标签当作完整性证明。

NVIDIA 运行环境固定基础摘要，安装 ffmpeg/poppler-utils 后保存不可变本地 image ID（`.private/runtime-image-id`）。运行版本证据在 `evidence/audio-runtime-versions.txt`；部署脚本按 image ID 启动，未使用 latest。

## 故障和状态

- 单次聊天等待槽位最多10秒，繁忙返回429；推理请求读超时600秒。不会自动将本地内容转到云模型。
- 媒体任务可取消。重启时执行中的任务标为 failed，排队任务保留；客户端应查询旧任务结果后再决定是否新建任务。
- `Idempotency-Key` 防止重复建媒体任务；它不承担业务工具副作用去重。工具执行仍由 Agent 管理。
- 临时附件不会自动无限保留；达到总配额后拒绝上传，客户端使用 DELETE 清理。SQLite 和私有数据目录应按实际业务备份，不把密钥写入公开备份。
- 主模型显式限制 KV 缓存6GiB、总上下文200000 token，最大并发2路。Spark01 的 `agent-mm-main-memory-guard` 每2秒检查 MemAvailable；低于20GiB时主动停本项目主模型并保留日志，恢复资源后由维护者重新启动。Spark02 同样以约20GiB余量为运行边界。首次自动缓存启动曾在调优阶段以137退出，不能据此声称已通过8小时稳定性验收。

## 停用/回退

在桌面客户端切回原 Provider，即可保留原入口继续使用。服务器端停用本项目时：

```bash
systemctl --user disable --now agent-mm-https agent-mm-gateway agent-mm-whisper agent-mm-omni agent-mm-tunnel
ssh spark01 'systemctl --user disable --now agent-mm-main agent-mm-main-memory-guard'
```

不删除模型、证书或私有数据。重新启用同名服务即可恢复。API Key 的轮换应在安全路径生成新值、更新客户端，并重启 gateway；CA 根证书或私钥轮换会要求所有客户端重新配置信任。

## 2026-11-14 资源切换

用户要求释放两台 Spark 的视频模型内存，运行本项目 Agent 多模态服务。两台节点均已停用 `ltx-worker` 和 `ltx-resource-guard` 的用户服务及开机启用；其运行准入文件分别移动为 `~/ltx-production/runtime/ltx-worker.enable.paused-agent-mm-20261114`，防止外部启动重新加载视频权重。本项目主模型与内存保护器、Whisper、Omni 恢复启用；网关、HTTPS 和隧道保持运行。其他业务未作资源清理。

未来如要恢复 LTX，需先确保资源足够，必要时先停用本项目模型，再将对应节点的上述 `.paused-agent-mm-20261114` 文件移回 `ltx-worker.enable`，执行 `systemctl --user enable --now ltx-resource-guard ltx-worker`。不要在两套模型同时常驻时直接恢复 LTX。

恢复验证和内存快照见 `evidence/recovery-20261114/`。原8小时混合冒烟已停止，未完成，原始结果保留。

## 2026-11-14 桌面端鉴权诊断

用户反馈同事使用私有接入包中的 API Key，桌面端仍提示提供方拒绝密钥。包内 API Key 与网关密钥一致，正确凭证从 Spark01 跨机器访问聊天接口返回200，错误/缺少凭证返回401。该结果不能单独证明同事端请求配置正确。

排查复现并修正了网关严格比较整个 Authorization 字符串的问题：现在按 RFC 9110 §11.1 和 RFC 6750 §2.1 解析大小写不敏感的 Bearer 方式及一个以上空格；密钥内容仍逐字节、大小写敏感地校验。拒绝请求返回 X-Request-ID 与 WWW-Authenticate，并在 journal 记录请求 ID、来源 IP 和不含凭证的诊断布尔值。禁止记录密钥、完整 Authorization 或密钥摘要。

验证：22项回归通过；小写/大写 Bearer、多空格在实际 HTTPS 入口返回200，错误与缺少密钥仍401；小写 bearer 从 Spark01 跨机器聊天返回200。证据：`evidence/auth-format-fix-20261114.json`。同事端是否命中该问题尚待其重试确认。

现场排查：`journalctl --user -u agent-mm-gateway --since "5 minutes ago" --no-pager`。`authentication_denied` 中 header_present=False 表示未收到 Authorization；bearer_scheme=False 表示鉴权方式或分隔格式不符；formatted_key_matches=True 表示凭证相同但仍有未接受的格式字符。只把这些字段用作诊断，不据此放宽密钥验证。

标准参考：https://www.rfc-editor.org/rfc/rfc9110.html#section-11.1 和 https://www.rfc-editor.org/rfc/rfc6750.html#section-2.1 。

## 2026-11-14 自研客户端字段兼容修正

用户截图中的实际错误为422 `Unsupported completion fields: store`，随后404 `Unknown chat model`；网关10:34日志吻合，证明这些请求已通过鉴权。已实际复现：`spark-main` 加 `store:false` 返回422；完整模型名称返回404。

修正后接收 `store:false` / `null` 并在网关剔除，不向上游声明聊天存储能力；`store:true` 和非法类型仍明确拒绝。完整模型名 `Qwen3.6-35B-A3B-NVFP4` 映射为 `spark-main`，未知模型错误提示使用该别名。其他不受支持字段与媒体安全校验保留。

验证：新增测试先观察到422/404，再修正；全套25项通过。线上普通与流式聊天均携带 `store:false` 返回200，完整模型名流式回复与用量返回正常，错误模型仍404、`store:true`仍422。证据 `evidence/desktop-field-compat-20261114.json`。实际自研客户端仍需重试，不以探针成功代替其整体验收。

官方字段定义：https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create 。

## 2026-11-14 用户要求200K上下文

用户明确要求将总上下文扩展为200K，覆盖初版审批方案的32K上限；原APPROVED-SPEC保留为历史方案。实际部署 `MAIN_CONTEXT=200000`、`MAIN_KV_CACHE_BYTES=6442450944`；网关容器 `MAIN_CONTEXT_TOKENS=200000`，模型发现接口公布 `max_model_len=200000`。主模型原生 `max_position_embeddings=262144`，无需位置编码外推。运行时报告6GiB缓存容量588235 token；最大并发仍限制为2路，未宣称两路满200K的性能验收通过。

长请求超时：网关读超时600秒，Caddy响应头等待600秒、读取900秒；自研客户端建议至少600秒。20GiB内存保护器保持启用。Spark01原32K启动脚本及用户服务备份位于项目 `.private/backups/context-200k-20261114/`，回退时还需同步恢复网关上下文配置和客户端设置。

输出预算修复：规范化 `max_completion_tokens` / `max_tokens`，优先现代字段，默认1024；值必须为正整数或null。若请求输出上限达到或超过整个窗口，内部通过有鉴权的 `/tokenize` 对完整消息、工具及图片计数，仅缩小输出到剩余预算，不截断输入。较小输出上限保持原值，输入与输出之和仍由主模型校验。预算响应头公开计数与实际输出上限；日志不记录消息内容。

验证：31项回归通过，独立审查无剩余已确认问题。流式响应清理由响应对象整体生命周期负责，响应头发送前断开也会释放槽位。实际HTTPS输入199889 token、输出4、总用量199893，返回LONG_CONTEXT_OK，耗时114.439秒；并行工具提示探针也成功，故该延迟不视为独立性能基准。实际工具/图片分词计数与用量逐项一致（7358/85），输出上限200000自动调整成功。原截图的约4.1万字符与32768输出上限请求恢复正常。实际桌面端仍需最终重试。

证据：`evidence/context-200k.json`、`context-200k-memory.json`、`context-200k-final.json`、`output-budget-200k-20261114.json`；新的私有接入包窗口200000、建议输出2048、超时600秒，API Key保持原值。

## 2026-11-14 生图/编辑替换音频

用户已批准以生图和图片编辑替代Whisper/Omni。音频服务已disable/stop，权重保留；转写和声音理解接口返回410；视频工具只分析画面并在结果明确audio_enabled=false。

新增Spark02用户服务 `agent-mm-image`（ComfyUI v0.33.2，127.0.0.1:18013）及 `agent-mm-image-memory-guard`。固定Docker镜像ID在 `.private/image-runtime/image-id`；完整依赖在 `deploy/image-requirements.lock`。模型目录 `/data/models/agent-mm-z-image-turbo`，Z-Image-Turbo及Qwen-Image-Edit-2511均BF16，后者按需轮换，所有文件完成HF固定revision/SHA256校验后才启用。ModelScope镜像的对应SHA逐文件与HF一致，记录在 `evidence/image-deploy-20261114/`。原始权重和CA/API凭证不删除、不轮换。

仅使用固定核心节点图，关闭自定义和外部API节点；保留20GiB可用内存保护。基础镜像的xformers不支持GB10，已实测失败并改用 `--use-pytorch-cross-attention`；同时显式BF16文本编码器。Qwen VAE的cuDNN Conv3D路径在此运行时产生条纹，BF16/FP32重建均失败；`deploy/start-comfy.py`禁用cuDNN后，GPU与CPU重建对照一致（1024 MAE0.85），保留CUDA/SDPA推理。同类任务保留权重缓存，生图/编辑切换时释放旧图和模型；`--cache-ram 20`约束缓存。CPU/GPU共享内存，不能将nvidia-smi分配与系统used相加。

```bash
python3 scripts/status.py
systemctl --user status agent-mm-image agent-mm-image-memory-guard agent-mm-gateway
journalctl --user -u agent-mm-image -n 50 --no-pager
```

图片任务最多4个（与现有媒体任务共用待处理配额），GPU生图/编辑串行；原图和生成结果合计2GiB配额，达到后拒绝，客户端用DELETE /v1/files/{id}清理不再需要的文件。Comfy输入/输出只是scratch：任务结束及启动确认无遗留推理后清理本项目文件；所有生成结果保存到受控文件库。

取消会先确认提交结果，再定向取消并确认后端结束，期间不放行下一任务。若HTTP提交结果未知，image worker停止接受后续队列，health降级；此时先记录日志，依次 `systemctl --user restart agent-mm-image`，等待18013/system_stats恢复，再 `systemctl --user restart agent-mm-gateway`。不要只重试建新任务。内存保护触发会停止image服务，资源恢复后人工start，避免自动重载循环。

完整图片接口见 `docs/IMAGE-SERVICE.md`，Mac私有接入包 `.private/mac-image-tools.zip`。Mac侧尚须安装并从实际Harness入口验收。

回退音频：先取消或结束图片任务，停用image及其guard；备份当前文件和SQLite，再从 `.private/image-runtime/pre-image-deploy.tar.gz` 恢复services及deploy目录（不覆盖私有数据）；重启gateway并enable --now whisper/omni。确认三后端健康后再接音频。回退会失去新增图片接口，因此应提前保留生成结果。初版APPROVED-SPEC保留为历史方案，用户后续明确修改以本节为准。

编辑加速：`quality=fast` 使用固定Lightx2v Qwen-Image-Edit-2511-Lightning BF16 4步LoRA，CFG=1；`standard`20步和`high`40步使用原版、CFG=4，切换时清空旧模型图缓存，防止LoRA残留。Mac MCP工具默认fast，直接API默认standard。LoRA固定revision及SHA见 `lightning-manifest.json` / `lightning-verified.json`。1024快速编辑冷加载367.999秒、连续双图编辑36.407秒；原版20步编辑203.656秒（含本次加载）。快速编辑批次最低可用29.688GiB，原版编辑28.504GiB。高质量40步已做图配置/单元验证，未单独GPU实测，不宣称更好或更快。模型切换与系统文件缓存会显著影响冷启动时间，不将一次冷启动数值当固定SLA。

最终验收证据：`final-verification.json`、`edit-verification.json`、`standard-edit-verification.json`、`mcp-stdio-live.json`、`review.md`及`review-fast.md`。20张生图基准为VAE修正前的记录，最终配置补做3张生成和Mac包真实stdio桥接验证；49项自动回归通过（1项既有Starlette弃用warning）。Mac实际Harness仍须安装包并从原入口验收；无Grok同素材质量对比，生成样张仍可能带虚构小字/标识。

## 2026-11-14 14:42 图片队列故障恢复

实际Mac端已接通MCP并持续查询任务。14:42:48 image-memory-guard记录MemAvailable=20387564KiB，低于20GiB而停止图片服务；当时有编辑取消后切回生图记录。此事件为保护器主动停止，不把后续docker退出137等同内核OOM。14:44之后网关仍接收新任务，worker初始化重试期间任务持续queued；Mac连续取消/重新提交不能恢复后端。

人工核实内存恢复后启动image服务，保留既有队列，task-aa4bb4e60de8469793d33c9db0bbe36b已完成并取回图片。网关新增异步任务及同步images接口的后端可用性检查，后端不可达或image worker停止时返回503并不建新任务；50项回归通过。没有关闭或降低20GiB保护器。此次没有足够证据断言内存降低只由某一个缓存或异步卸载竞态造成；模型切换稳定性仍应继续记录，不宣称已消除全部内存触发情形。

Mac遇到queued时继续查原任务ID；若/health的image unavailable或接口503，请维护者查guard日志并恢复服务。不要反复建新任务。恢复证据位于evidence/image-queue-recovery-20261114。

恢复后新的电脑生图任务已完成，含网关重启后的释放/重载耗时181.088秒，采样期间MemAvailable最低44.48GiB；不能把之前热请求约12秒当作每次首图时间。Mac日志中多次约80秒取消并重建，因此工具说明/私有包补充：20秒为单次查询等待，queued/running持续查原任务，勿按80秒自动取消。

# T01：兼容归属 expand（2026-11-15，离线副本验证）

本阶段只扩展旁表，不启用生产多用户；原 files/tasks 列数、任务 ID、结果引用、全局 4 单与 2GiB 边界保持原契约。`create_app` 初始化将现有无归属对象补为 `legacy`。新旧版写入暂仍使用旧表示，维护者在停写后再次 expand；只读预检会显示这些未归属行。文件/任务写入迁移属于 T02/T03。

先停止新接单、确认图片后端空闲，并同时备份 state.sqlite3、files 目录和私有鉴权配置（原子快照或停写后复制）。在脱敏副本上通过以下公开接口检查；示例路径必须替换为副本，不能对生产路径试跑：

```python
from pathlib import Path
from services.ownership import expand_ownership, preflight_ownership

database = Path('/path/to/sanitized-copy/state.sqlite3')
print(preflight_ownership(database))  # mode=ro；不存在的库报错，不创建
expand_ownership(database, legacy_owner='legacy')
print(preflight_ownership(database))
```

预检字段为 unowned_files、unowned_tasks、unowned_idempotency_records（旧 tasks.idem 非 NULL 且任务无归属）、running_tasks。factory 在 expand 前将上述四项计数写入 ownership_preflight 诊断日志，不记录原始 Key、幂等键或对象内容。预检不运行恢复、不更改状态；运行任务应先保守处理，不能通过重复推理清零。expand 使用一个事务，失败全部回滚，重试不覆盖明确归属。旧版继续写入后，停写、再次预检/expand。

回退路径：停接单并保存新增任务和素材，确认后台无运行推理，再切回已验证的单用户旧版应用；保留旁表，不 DROP 数据或恢复旧快照覆盖新增写入。仅限仍属于 legacy 的数据；已有多个 owner 时只能回退到具备相应 owner 校验的版本。备份恢复先在另一副本检查原任务、素材和结果，再由维护者决定生产切换。

切片 A 证据：`evidence/issue-2/a-*-red.txt` 与 `a-*-green.txt` 记录逐切片 red/green；`a-green.txt` 为计划指定的受影响回归，11 passed。ADR 见 `docs/adr/0001-owner-scoped-storage.md`。目前仅离线合成数据验证；旧/过渡版完整图片链路和恢复验证由切片 B 补齐，生产数据、实机后端、Windows/macOS Harness 未验收。

T01 身份接线：`create_app(root, token)` 保留旧位置参数，默认在 root/keys.sqlite3 只持久化 legacy Key 的 SHA256 摘要和 owner/key_id，原始 Key 仍由私有配置交付。传入显式 `key_registry` 时只信该注册表，位置 token 不成为额外回退凭证。KeyRegistry 的 issue 返回一次性随机 Key；register 对同 owner/key 幂等，跨 owner 重绑报 ValueError；revoke 后即使重新注册或重启也不会恢复授权。同 owner 的新 Key 保留 owner、使用不同 key_id。未知、撤销或非 legacy owner 在 legacy 模式返回 401，保留 WWW-Authenticate 与请求 ID。

`identity_mode='staging'` 只允许在明确隔离的测试数据副本中使用。本票尚未完成文件/任务 owner 校验，staging 不是生产访问控制，不能暴露给用户；生产 application() 仍固定默认 legacy，不能由请求选择身份模式。`strict` 在 T02/T03/T04 完成前启动即 ValueError，非法模式同样在创建数据库前失败，避免半迁移入口。测试身份 A/B 的存在不表示跨人文件与任务隔离已交付。

旧版回退只能用于单一 legacy 数据及仍有效的单 Key；旧版不理解注册表撤销，撤销/轮换后回退需同步更换旧版私有 token 并验证失效 Key 被拒绝。多个 owner 数据、完整个人凭证与隔离上线由后续票收口。

切片 B 在合成旧格式库中验证：独立冻结的旧版完整服务 → 过渡版 → 旧版均上传、执行和取回可解码 PNG；原排队参考图/透明前景关联、历史结果和幂等 task_id 跨重启保留，running 仍按原恢复规则变为 failed，后端实际工作总数为 5（两个原排队任务、三次新生成），没有幂等重放推理。另验证旧/新版原上传及 task_idempotency 用例、旁表迁移注入失败后原子回滚与重试、并发旧写入、并发 Key 注册、数据库/文件/注册表备份恢复到新目录。证据与验收映射见 `evidence/issue-2/acceptance.md`。

本轮离线最终验证：29 项 T01 测试已采集，计划指定受影响回归 31 passed，pytest 全套 79 passed（1 项既有 Starlette/AnyIO 弃用警告）。未配置类型检查/静态检查/构建门禁，标记 N/A；实机、生产与平台链路仍未验证。


# T02：素材 owner 隔离（2026-11-15，受控离线验证）

T02 已接入 HTTP 文件读/删/引用及 worker 结果归属，修正同步编辑全局哈希 ID。`identity_mode='staging'` 仅可用于隔离副本；任务查询/取消与按人幂等尚待 T03/T04，生产 application() 仍 legacy，strict 启动保护保留。T01 上述未完成文件迁移的说明是当时状态；当前细节见 docs/IMAGE-SERVICE.md 和 evidence/issue-3/acceptance.md。

维护与恢复仍先停新工作、定向停任务并确认后端空闲，再同步保全数据库、文件与凭证注册表。新旁表 file_digests 及任务 object_owners 必须随库保存；不可丢弃新 owner 数据。关闭 staging 接入后仅服务 legacy 自有数据；回退版本仍须保留文件 owner 检查与新归属，不能把混合库交给 T01 或更早共享访问代码。无不可逆 schema 重建，本票未部署、未触碰生产库，实机备份/发布/回滚未验证。

# T03：任务归属（切片 A，2026-11-15）

在独立测试副本中验证任务查询/取消、按 owner 的幂等与 worker 结果归属。生产服务保持停用/legacy，未改部署配置或生产库。新 task_requests 旁表须与 state.sqlite3、object_owners、file_digests、files 和 KeyRegistry 一并保全。所有新写入保持旧 files/tasks 列数，无不可逆表重建；重放先于全局容量检查。

回退先关闭 staging 接入并停止接单，保存新增任务/素材/注册表，定向停止运行任务并确认后端空闲。含多人数据时只能回退到具备同等任务与文件 owner 校验的版本，不能直接部署 T02 或更早的全局任务查询实现。旧版兼容测试仅限 legacy 副本，不表示允许生产降级。

测试 seam、基线、red/green 和审查记录见 evidence/issue-4/。类型检查、静态检查、构建/CI、Compose、安全扫描、变异测试、seed 均未配置，标为 N/A；物理模型、真实 HTTPS、双端 Harness、生产备份发布/回滚仍未验证。仅执行受影响测试，不以离线接口结果宣称完整 AC 或性能验收。

T03 旧数据恢复边界：若 T03 之前的任务尚无内容指纹，且原素材已被删除，无法证明新上传内容等价。此时重用旧键返回409，detail含本人原 task_id，继续查询原任务/下载已有结果；不会重跑推理或猜测内容。需要重新创作时使用新键。已有 T03 内容指纹的请求不受此历史限制，删除原参考图后重传相同内容仍复用原任务。

## T03 个人 Key 发放、撤销、轮换与遗失恢复

以下仅为已实现运维命令，不在当前生产库执行。先确定独立受控副本、稳定 IMAGE_OWNER、注册表 IMAGE_KEY_DB 与新文件 IMAGE_KEY_OUT（父目录应为受限私有目录）。同一人轮换时必须沿用原 owner；禁止为方便轮换新建另一个 owner。

```bash
.venv/bin/python -m services.identity --db "$IMAGE_KEY_DB" issue --owner "$IMAGE_OWNER" --out "$IMAGE_KEY_OUT"
.venv/bin/python -m services.identity --db "$IMAGE_KEY_DB" revoke --key-id "$IMAGE_OLD_KEY_ID"
```

发放只向 stdout 返回公开 key_id，原始 Key 只进入新私有文件，勿粘贴进聊天/日志。目标存在或写入失败会非零退出、撤销本次凭证，既有文件保持原样。错误只报告异常类别；本次创建的残片会删除。保留 owner/key_id 的运维记录与私有交付路径，原始 Key 不可由摘要恢复。

轮换顺序：先用不同目标文件为同一 owner 发放新 Key，通过私有渠道交付；验证新 Key 的 `/v1/me` 与原任务/结果访问后，再按旧 key_id 撤销旧 Key。失败时原 Key 继续有效，除非已明确撤销。遗失凭证时重新发放同 owner Key，并按已保存 key_id 撤销遗失凭证；若同时遗失注册表，则从完整私有备份恢复映射，不能把历史任务重新归给所有人。撤销不可“复活”，只能发放新 Key。

离线演练：子进程真实运行 CLI 发放→同 owner 再发放→重复撤销旧 Key，HTTP 验证旧401、新 Key 读原结果200、其他 owner404，输出无原始 Key。新目录副本恢复 SQLite、文件库和 KeyRegistry 后再次验证撤销、任务/result 与相同业务请求 ID。此为合成数据副本演练，不代表生产恢复/发布验收。

T03 凭证交付的组合故障：即使注册表撤销失败，也独立清理本次创建的文件并保留既有文件。若数据库撤销或文件清理不能确认，抛出 KeyDeliveryError；CLI 非零退出并仅报告公开 key_id 与恢复指引，不报告原始 Key。此时不能声称已撤销；保持接入关闭，恢复注册表写入后按该 key_id 重试 revoke。仅当错误明确报告本次新建输出仍待清理（cleanup_pending）时，才核对并清理该输出；既有文件必须保留。原始交付错误不会掩盖必要的恢复编号。

## 2026-11-15 T03 真实无模型验证

按用户要求保持LTX运行且不加载模型。在独立数据目录、loopback HTTPS和原项目CA上完成56个真实网络/进程检查点：A/B鉴权与隔离、真实CPU PDF worker、幂等、轮换/撤销、四单容量，以及MCP离线503/跨人404。临时进程已停止、Key已撤销删除，正式服务与LTX状态保持原样。无产品代码修改。详见 evidence/t03-live-20261115T025313Z/README.md。物理生图/编辑、双端Harness、正式18443/生产发布恢复与模型内存标定仍未验证，#4保持OPEN。


## T04 离线 contract 迁移（生产启用仍阻塞）

2026-11-15 用户允许在 #4 保持 OPEN 时实现 #5 的离线行为；这不是生产切换授权。生产接管人、#4 物理图片验收、生产备份/恢复和双端实际入口仍未验证。保持既有模型、LTX、20GiB 保护和服务配置不变。

仅在脱敏副本执行；实际维护前停止全部数据库、文件和凭证注册表写入者，定向停止并确认后端空闲。`running` 必须先按保守恢复策略明确失败，不自动重跑。T01 固定稳定 owner 是 `legacy`；接管通过向指定人员发放该 owner 的新个人 Key 完成，不改归属、不再分发共享旧 Key。`--legacy-owner` 缺失或与此身份不符均拒绝。

```bash
.venv/bin/python -m scripts.migrate_image_owners --db /absolute/offline-copy/state.sqlite3 --legacy-owner legacy --dry-run
.venv/bin/python -m scripts.migrate_image_owners --db /absolute/offline-copy/state.sqlite3 --legacy-owner legacy --backup-dir /absolute/new-private-backup
```

CLI dry-run 用只读连接，不创建缺失数据库。写入前在 BEGIN IMMEDIATE 中预检文件、所有状态任务的来源/参考/前景/结果关联、owner、请求与摘要映射；悬空、跨人、缺失字节或不安全路径拒绝，错误只含对象 ID，不含业务参数。迁移前 SQLite backup API 保存 state.sqlite3、相邻 keys.sqlite3（若有）和整个 files 目录；新目录0700、文件0600，manifest.json 记录 SHA256。外部路径的注册表、CA和私有配置另行在私有路径保全；不把原始 Key 放进证据。

`contract_ownership(db_path, legacy_owner, backup_dir=...)` 同样先备份；省略 backup_dir 时在数据根 ownership-backups 下创建独占随机目录。备份失败不得迁移；失败备份目录保留用于排查，不能覆盖重用。备份必须在 files 树外，禁止复制符号链接。所有写入者停止是跨数据库/文件一致性的必要运维前提，SQLite 锁不是分布式维护锁。

在同一事务补齐旁表、回填 owner 范围请求映射、删除 tasks.idem 全局唯一约束并记录 ownership_migration。保留原 ID、rowid 顺序、列、业务值、显式索引/触发器。任何迁移异常整体回滚；下次使用新备份目录重试。不能把新多人库交给旧共享服务。

切片 A 的逐步 red/green 及迁移中断原始证据在 evidence/issue-5/；strict 启动与用户接口收口由切片 B 交付。尚未执行生产迁移或恢复，不把副本测试写成生产验收。


### T04 strict 与恢复当前约束（覆盖前述 T01—T03 过渡说明）

所有用户文件/任务接口已取消默认 owner。factory 不再自动 expand；legacy/staging 遇到未归属行或未迁移旧全局请求时也拒绝启动。strict 必须由显式注册表鉴权，且在任何初始化/恢复写入前通过只读 contract 校验。未知迁移版本、未知任务列/隐式唯一约束、残留全局 idem 索引、运行任务、未解释悬空或跨人关联均拒绝；迁移失败回滚主库，保留备份与原对象 ID。

生产 factory 的 AGENT_IDENTITY_MODE 必须显式配置，缺失不会退回共享模式。legacy 只接收 legacy 身份，用于具有完整 owner 感知的受控恢复；staging 仅隔离副本。strict 使用 runtime/keys.sqlite3 的既有个人注册表，不读取 agent-api.key、不注册共享后备凭证。当前部署脚本/生产环境尚未设置该配置，未进行服务重启；生产启用仍被 #4 和维护者接管名单阻塞，不直接执行旧启动脚本。启用前在部署环境显式传入 AGENT_IDENTITY_MODE=strict、验证 root/runtime 路径和注册表，再完成生产门禁。

合法删除的终态素材/结果会在同一事务写 file_tombstones，保证重启仍可识别主动删除而非损坏。结果端点返回404，原任务仍可查且不重跑；同内容新素材加原请求键仍复用原任务。无删除记录的历史悬空引用继续拒绝迁移，维护者必须先调查/修复；不得猜测内容、伪造删除证明或自动公开。

生产启用记录必须在私有运维记录中填入：稳定 legacy owner 与实际接管人映射、个人 Key 的公开 key_id/私有交付位置、contract 提交/校验结果、切换前备份目录与 manifest、owner 感知回滚版本、新写入归档目录与核对清单、后端停止/空闲证据、发布和恢复验证结论。以上生产字段本轮均“未验证/未指定”，不能把合成身份当真实接管名单。

恢复步骤：停全部写入者→确认后端空闲→用 backup_state 为当前新增文件/任务和注册表创建另一个独占归档→按 manifest 核对字节→把旧备份还原到新目录调查，保留当前完整归档→用支持 owner 与 tombstone 的 T04/等价版本恢复最新完整归档并在隔离入口核对本人200/跨人404/已撤销401、task_id和幂等映射→维护者再决定生产切换。旧备份缺少切换后任务和最新撤销状态，不能用它直接覆盖现状；本轮测试分别恢复旧快照和最新归档，未实现自动合并增量或生产切换。

合成演练通过冻结旧 HTTP 服务/真实 worker 完成图片结果（仅外部推理替身），覆盖旧 queued/running/completed/cancelled/failed、迁移拒绝/重试、A/B新写入、Key轮换/撤销、新目录恢复及无额外推理。真实SQLite authorizer验证建表/复制/重命名故障整体回滚；并发迁移重试串行，无重复归属。实际生产、HTTPS/MCP/物理图片和双端 Harness 均未验证，未触碰 LTX 或内存保护器。
