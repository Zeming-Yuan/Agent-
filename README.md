# Agent 多模态服务

初版依据 `APPROVED-SPEC.txt`，后续按用户明确要求扩展至200K，并以生图/图片编辑替换Whisper与Omni。桌面端使用OpenAI接口，HTTPS入口仍为 Spark02 `192.168.10.77:18443`，沿用专用CA和凭证。

**当前状态（2026-11-14，为视频释放资源）：按用户要求停用本项目聊天、图像、网关、HTTPS、隧道及相关守护服务，并取消开机加载。用户随后明确只释放内存、不运行视频；两台 LTX worker、资源守护及 Spark02 LTX API 均停止，视频权重不保留常驻。** 模型、凭证及任务数据保留。本项目桌面聊天/生图入口当前不提供服务。最初释放资源后、LTX 加载前的可用内存为 Spark01 94.18GiB、Spark02 95.58GiB；最终实测及操作证据见 `evidence/video-resource-switch-20261114/`，运行切换说明见 [OPERATIONS.md](OPERATIONS.md)。

**停用前能力验证：生图、单图编辑、多图参考编辑已实际调用并检查样张。** Whisper/Omni此前已停用且取消开机加载。聊天配置为Spark01 200K上下文；Spark02图像配置为Z-Image-Turbo BF16生图、Qwen-Image-Edit-2511 BF16编辑，串行轮换，保留20GiB内存保护。接口与Mac接入见 [IMAGE-SERVICE.md](docs/IMAGE-SERVICE.md)；私有工具包 `.private/mac-image-tools.zip`。

本轮49项回归通过；单图换色、双图换背景、透明前景像素保留与中文标题、运行中取消后继续生图均通过。Mac私有包已通过真实stdio→HTTPS→生成→取回MCP图片验证；尚未在老板Mac的实际Harness窗口安装验收。快速编辑连续请求约36.41秒，首次加载约368秒；原版20步编辑一次约203.66秒。生图20张基准中位约11.66秒，最终运行配置另做3张回归；模型切换/排队时间另计。不承诺与Grok同等质量，商品Logo/细小文字需核对。证据见 `evidence/image-deploy-20261114/`。

2026-11-14 14:42图片服务曾触发20GiB内存保护而停止，导致后续图片任务长期排队；已恢复并完成原队列任务，新增离线时503拒绝建新任务，50项回归通过。保护器保留，未将本次恢复计为长期稳定性验收。见 `evidence/image-queue-recovery-20261114/`。

下文三模型/音频恢复记录属于本次替换前的历史验证，不代表当前仍提供音频能力。

**完整业务验收尚未完成。** 2026-11-14 按用户要求停用两台 LTX 视频生成模型、释放资源并恢复本项目三模型。恢复后的实时状态与功能验证见 `evidence/recovery-20261114/`。原8小时服务端混合冒烟于2026-11-13停止，累计38轮、3次失败，未通过8小时验收，不能代替实际桌面端业务验收或准确率报告。

2026-11-14 恢复验证：三模型 `/health` 全部 ready；HTTPS 聊天、图片、Whisper 转写、Omni 声音理解、PDF 提取和视频任务均完成实际调用。恢复后的可用内存为 Spark01 约71.2GiB、Spark02 约74.5GiB，两台 LTX 视频生成服务及自动恢复守护已停用。以上为功能恢复检查，不代表完整质量或8小时验收通过。


2026-11-14用户要求扩展到200K，已部署并实测：输入199889 token、总用量199893 token，输出 `LONG_CONTEXT_OK`，耗时114.44秒。该次为合成材料、仅4 token输出的容量功能检查，期间另有工具提示请求，不代表长文分析准确率或独立负载性能。当前窗口200000、KV缓存6GiB，31项回归通过；流式开始前断连的槽位清理问题也已修复。长请求采样期间Spark01/Spark02可用内存最低约60.0/71.4GiB。详见 `evidence/context-200k.json`、`context-200k-final.json`、`output-budget-200k-20261114.json`。

## 桌面端填写

| 设置 | 值 |
|---|---|
| 提供商类型 | 自定义 OpenAI Compatible，Chat Completions |
| Base URL | `https://192.168.10.77:18443/v1` |
| 模型名称 | `spark-main` |
| API Key | `.private/agent-api.key`；通过私有接入包交付，不贴在聊天中 |
| CA | `certificates/agent-root-ca.crt`，需配置到实际客户端网络进程 |
| 上下文 | 最大200000 token，包含全部输入及输出；2026-11-14用户要求扩展 |

说明见 [DESKTOP-CLIENT.md](DESKTOP-CLIENT.md)。私有接入包 `.private/desktop-openai-bundle.zip` 内含参考设置、调用凭证、公开 CA 和操作说明，不含 CA 私钥。它不是所有桌面软件通用的一键导入格式。尚未识别具体桌面软件，未声称已修改该软件的实际配置。

## 部署布局

| 节点/服务 | 运行配置 | 监听 |
|---|---|---|
| Spark01 主模型 | Qwen3.6-35B-A3B-NVFP4，vLLM0.28.0 ARM64，独立容器 | 127.0.0.1:18010 |
| Spark02 生图/编辑 | Z-Image-Turbo / Qwen-Image-Edit-2511，BF16，固定ComfyUI 0.33.2；quality=fast为4步适配器，standard20步/high40步 | 127.0.0.1:18013 |
| Spark02 Whisper / Omni | 已停用，原模型文件保留；音频接口410 | 不再监听18011/18012 |
| Spark02 网关 | 鉴权、OpenAI 适配、附件、媒体任务、取消与状态 | 127.0.0.1:18008 |
| Spark02 HTTPS | 独立 Caddy 内部 CA 实例，Bearer 凭证 | 192.168.10.77:18443 |

Spark02 通过 SSH 加密隧道连接 Spark01 回环端口。模型端口未直接向局域网新增开放。现有服务保持原配置。两端用户服务已启用，`Linger=yes` 已确认；未执行整机重启验收。

主模型最大并发2路、FP8 KV 缓存6GiB、图片每请求最多4张；采用 eager 模式作为当前已验证配置，性能指标需另测。Spark01 内存保护器在 MemAvailable 低于20GiB时停止本项目主模型，优先保留现有业务。正常运行快照中两节点均保留远大于20GiB的可用余量。

## 已完成的现场验证

- [x] 核对实际资源、旧下载进程与文件，避免继续依赖失效的聊天会话编号。
- [x] 主模型三个权重分片校验；vLLM 固定 ARM64 manifest 和全部镜像 blob 校验。
- [x] Omni 五个权重分片、辅助文件与固定官方版本 SHA-256 一致。
- [x] 三模型完成实际加载，HTTPS `/health` 返回 ready。
- [x] OpenAI SDK 实测普通回复、流式、工具调用 ID/参数、工具结果回填续答。
- [x] `tool_choice=auto` 的真实流式工具参数和多轮闭环通过；库存17为本地测试夹具，没有调用真实业务系统。
- [x] 图片识别、可提取文字 PDF、扫描 PDF 页面视觉分析、视频抽帧及音轨转写通过功能测试。
- [x] Whisper 真实中文短音频与长音频分段转写；返回可核对的时间戳。
- [x] 16K阶段实际输入14979 token；32K阶段实际输入31985 token、总用量31989 token，均成功返回且未越界。
- [x] 本机与 Spark01 跨机器 HTTPS 访问；正确 CA/凭证通过，错误凭证或不信任 CA 被拒绝。
- [x] 自动回归20项通过；独立代码审查发现的并发槽位、解码 admission 与上传配额问题已修复。
- [ ] 实际桌面客户端安装 CA、填写 Provider 并从其原入口联调。
- [ ] 方案要求的100次单独/混合负载性能统计、20个真实业务工具任务、中文文档字段/语音/声音/视觉标注质量验收。
- [ ] 至少8小时持续运行验收；原服务端混合冒烟已停止，尚未达到完整交付准入。

单次示例结果不是P95或准确率：Whisper中文样本返回“每一天都要快乐哦”，热请求约0.17秒处理2.43秒音频；近32K输入请求约9.75秒，输出仅4 token。不能据此宣称达到完整方案的性能指标。

**已知质量限制：** Omni 在3秒440Hz纯音夹具上返回了“语音”，该项误判保留在原始证据中；声音理解准确率尚未验收。语气等描述只作辅助线索。

## 恢复与下载记录

原会话86960/48061已失效，原进程也不再作为完成依据。Omni 海外下载停滞后，改从 Qwen 官方 ModelScope 镜像获取相同分片，逐一匹配固定 Hugging Face 提交 `ae9e1690543ffd5c0221dc27f79834d0294cba00`；处理器/分词配置来自该固定提交。

Spark01 直接拉取 Docker Hub/CDN 出现 TLS 超时。未改全局代理；在 Spark02 直接获取固定 manifest、校验各 blob，再通过 SSH 导入 Spark01。固定原始 ARM64摘要：

`sha256:2a7cde230b59f3ce6cab33dd245ba6bee41aa87b38c9fe84f966ff24016813ce`

当前 Docker archive 导入后的本地镜像 ID：

`sha256:991978a4dce45d28da78551777d949da90dbff03228c2f0fc98a8affe19ab4ca`

导出配置与官方配置逐字节一致，32个 rootfs diff ID 一致。Docker archive 导入后的本地 ID 与原始 registry manifest/config digest 含义不同，不能混用。完整证据在 `evidence/main-image-verified.json`。

首次自动KV缓存配置分配约34.55GiB，启动在 FlashInfer 自动调优阶段以137退出，Docker OOMKilled=false，未取得内核OOM证据；不把原因写成已证实的OOM。改用显式2GiB缓存并加20GiB保护后，16K/32K启动与实际请求均通过。该事件仍计入部署记录，不算已通过8小时稳定性验收。

## 查看当前状态

```bash
cd /home/clusteradmin/Desktop/Agent多模态服务
python3 scripts/status.py
cat evidence/soak-server-8h/summary.json
journalctl --user -u agent-mm-soak -n 30 --no-pager
.venv/bin/python -m pytest -q
```

原8小时任务为一次性后台进程，目前已停止，报告状态为 `stopped_on_failure`。每轮并发文字、转写及后台 PDF/视频任务，周期性调用 Omni；这是固定合成/公共夹具的轻量混合冒烟，不是实际桌面业务负载。原结果保留在 `evidence/soak-server-8h/`，未将本次恢复运行计为8小时验收通过。

运行/回退说明见 [OPERATIONS.md](OPERATIONS.md)，实现与决定见 `docs/superpowers/plans/2026-11-13-dual-spark.md`。

## 主要证据

- `evidence/status-current.json`、`gateway-https-local.json`、`gateway-https-from-spark01.json`
- `evidence/openai-sdk-acceptance.json`、`tool-auto-stream-roundtrip.json`
- `evidence/context-16k.json`、`context-32k.json`、`vision-red-image.json`
- `evidence/whisper-https.json`、`whisper-long-task.json`、`omni-real-audio-final.json`、`omni-tone-task.json`
- `evidence/pdf-extraction-task.json`、`scanned-pdf-task.json`、`video-task.json`
- `evidence/gateway-tests.txt`、`review-20261113.md`、`fault-acceptance.json`
- `evidence/main-startup-attempt1.json`、`main-image-verified.json`、`omni-weights-verified.json`
