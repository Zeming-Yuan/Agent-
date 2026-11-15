# 桌面客户端接入

在桌面软件中新建一个「自定义 OpenAI / OpenAI Compatible」提供商，使用 Chat Completions 模式：

| 设置 | 填写值 |
|---|---|
| Base URL | `https://192.168.10.77:18443/v1` |
| 模型名称 | `spark-main` |
| API Key | 从本项目 `.private/agent-api.key` 安全读取；不要上传到群聊或公共仓库 |
| 流式输出 | 开启 |
| 输入类型 | 文字、图片（PNG/JPEG/WebP） |
| 总上下文 | 200000 token，包含系统提示、工具、历史、图片和输出 |
| 建议输出上限 | 2048 token，可按任务调整；不要把总上下文直接填成输出上限 |
| 长请求超时 | 建议至少600秒；200K长输入预填充速度需看实际测试 |

如果软件分开填写主机和路径：主机为 `https://192.168.10.77:18443`，模型请求路径为 `/v1/chat/completions`。不要重复添加 `/v1`。当前提供 Chat Completions；仅支持 Responses 或 Anthropic 的客户端需要另加适配。

## 自研客户端请求格式

使用 `POST /v1/chat/completions`，请求头带 `Authorization: Bearer <API Key>` 与 `Content-Type: application/json`。最小请求体：

```json
{"model":"spark-main","messages":[{"role":"user","content":"你好"}],"store":false,"stream":true}
```

`model` 推荐 `spark-main`；兼容完整名称 `Qwen3.6-35B-A3B-NVFP4`，网关会转为稳定别名。转写和 Omni 的模型 ID 不能用作普通聊天模型。`store:false` 或 `null` 可接收并由网关消费，不转发为存储请求；本地服务没有保存聊天供后续检索的接口，`store:true` 会明确返回422。

截图若显示 `Unsupported completion fields: store`，对应2026-11-14 10:37之前的网关兼容缺陷，现已修正；`Unknown chat model` 则应检查实际发送的 JSON `model` 字段，而不只看界面上的模型显示名称。

## 证书只需导入一次

公开根证书：`certificates/agent-root-ca.crt`。只分发这份证书，不分发 `.private/data` 下的 CA 私钥。

- Windows：双击证书 → 安装证书 → 当前用户 → 受信任的根证书颁发机构。若桌面软件以系统服务运行，应由维护者为该服务配置证书信任。
- macOS：导入登录钥匙串，并将该证书设置为受信任。
- Linux/容器：优先在该客户端进程指定此 CA 文件；只有需要系统信任时再安装到系统 CA 库。

部分桌面程序的 Node/Python 网络进程使用独立信任库。操作系统导入后仍报证书错误时，需要在该程序的实际网络进程配置 CA，例如 Node 的 `NODE_EXTRA_CA_CERTS` 或 Python 的自定义 SSLContext。保持 TLS 证书校验开启。

当前服务身份是 `192.168.10.77`；客户端须在能够路由到此地址的局域网。服务器当前网卡地址仍受现有网络配置管理，后续应在路由器做 DHCP 保留；本项目没有改动全局网卡配置。

## 音频和媒体接口

普通 OpenAI 桌面聊天页面不一定支持自定义媒体工具。服务已提供以下协议，客户端有工具/插件能力时可对接：

- `POST /v1/audio/transcriptions`：OpenAI multipart 转写；模型 `whisper-large-v3-turbo`，短音频不超过30秒，支持 json/verbose_json/text。
- `POST /v1/files`：multipart `file` 上传，返回 `file-...`；单文件64MiB，总暂存2GiB。
- `POST /v1/tasks`：JSON `{"kind":"transcribe","file_id":"file-..."}`，返回任务 ID。kind 可选 `transcribe`、`audio_understand`、`pdf`、`video`；语言默认 zh，声音理解可在 options.prompt 填写问题。
- `GET /v1/tasks/{id}`：状态、进度、结果；`POST /v1/tasks/{id}/cancel`：取消。相同 `Idempotency-Key` 和相同请求复用原任务；改变请求内容返回409。
- `GET /v1/files/{id}/content`、`DELETE /v1/files/{id}`：读取/清理附件；仍被排队/执行任务使用的附件不能删除。

所有请求都需要同一个 `Authorization: Bearer ...`。这是首期单客户端身份；文件 ID 不等于登录凭证。长期多用户使用需要增加独立身份和文件所有权。

后台队列最多4个任务，串行处理重媒体。音视频最多5分钟，按30秒切音频；PDF最多20页；视频每15秒抽帧，因此可能漏掉采样间隔内的事件。图片使用 inline data URL，不从客户端提供的任意远程地址抓取。模型只提出工具调用，实际业务工具由桌面 Agent 执行。

## 判断是否就绪

`GET /v1/models` 是接口连通测试，列出模型别名，并不代表模型已经完成加载。

带凭证访问 `GET /health`，HTTP 200 且 `status=ready` 才表示三个后端均响应；HTTP 503 / degraded 会列出未就绪后端。完整业务验收、质量及8小时持续测试见 README 和 evidence。

## 200K 与输出上限

2026-11-14按用户要求将主模型总窗口从32768扩展为200000 token，KV缓存从2GiB增加到6GiB；以现场实际长请求证据为准。客户端的 `context_window` 应设为200000，输出 `max_completion_tokens` 建议2048，二者含义不同。若客户端将输出上限填为整个窗口或更大，网关会用主模型分词器计算输入与工具模板，只缩小输出上限到剩余预算，不截断消息；输入已经占满窗口则明确拒绝。普通较小的输出上限仍按客户端指定值处理，输入和输出之和也须不超窗口。

预算发生调整时响应头包含 `X-Context-Window`、`X-Input-Tokens`、`X-Max-Output-Tokens`，方便自研客户端排查。
