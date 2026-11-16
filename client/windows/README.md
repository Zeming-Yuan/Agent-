# Windows DeepSeek Harness 图片工具

本目录是 Windows 专属安装和配置层。它复用根目录的 `spark_image_tools.py`、HTTPS/MCP 协议和服务端任务恢复；不会复制一套 Windows 协议。Python 要求 3.11 或更新版本。

## 安装

1. 将 T12 Windows 客户端目录解压到固定路径，例如 `C:\Users\Tester\Spark Image Tools`。包根目录应包含 `spark_image_tools.py`（或可由脚本从 `client\spark_image_tools.py` 补齐）、`client\windows` 以及依赖清单。不要把个人 Key、CA、配置、请求日志或图片放入公开 ZIP/仓库。
2. 准备仅当前用户可读的 `api_key_file` 和 CA 文件及个人 JSON 配置，然后在 PowerShell 中运行：

   ```powershell
   .\client\windows\install-windows.ps1 -InstallDir "C:\Users\Tester\Spark Image Tools" `
     -ConfigFile "C:\Users\Tester\Spark Image Tools\personal.json" `
     -ApiKeyFile "C:\Users\Tester\Spark Image Tools\private\api.key"
   ```

   脚本只使用当前用户的 `py -3` 启动 Python 3.11+ 虚拟环境，并在依赖安装失败时返回非零错误。它会优先使用安装根目录的 `requirements.txt`，否则使用受控客户端的 `client\image-tools-requirements.txt`；它不修改全局 PowerShell 执行策略。
3. 生成 Harness 插件片段：

   ```powershell
     C:\Users\Tester\Spark Image Tools\.venv\Scripts\python.exe `
     C:\Users\Tester\Spark Image Tools\client\windows\configure.py `
     --install-dir "C:\Users\Tester\Spark Image Tools" `
     --config-file "C:\Users\Tester\Spark Image Tools\personal.json" `
     | Out-File -Encoding utf8NoBOM .\spark-images.windows.json
   ```

   将 JSON 数组作为实际 Harness 的 MCP 插件配置导入。`command`、`args` 和 `cwd` 是独立字段，因此中文和空格不会被 shell 二次拆分。配置只引用 Key/CA 文件，不嵌入凭证。

`personal.json` 的最小形状如下；`api_key_file`、`ca_file`、`output_dir` 和 `journal_path` 可以是绝对路径，也可以相对配置文件所在目录：

```json
{
  "base_url": "https://<gateway-host>:18443/v1",
  "api_key_file": "C:\\Users\\Tester\\Spark Image Tools\\private\\api.key",
  "ca_file": "C:\\Users\\Tester\\Spark Image Tools\\private\\agent-root-ca.crt",
  "output_dir": "C:\\Users\\Tester\\图片输出",
  "journal_path": "C:\\Users\\Tester\\Spark Image Tools\\private\\requests.sqlite3"
}
```

服务 URL 必须是 HTTPS `/v1`；客户端保持 CA 校验，不使用 `verify=False`。Key 文件只在私有路径中读取，不能写入插件 JSON、日志或报告。

实际 Harness 的网络进程若使用 Node，请在该 Harness 的用户级启动配置中把 `NODE_EXTRA_CA_CERTS` 指向同一份个人 CA；只给 Python bridge 配置 CA 不会改变其他进程的系统信任。不要把 CA 合并到公共包，也不要用关闭证书校验来绕过配置错误。

## 更新与卸载

更新前保留个人配置、Key、请求日志和图片，并运行：

```powershell
.\client\windows\install-windows.ps1 -InstallDir "C:\Users\Tester\Spark Image Tools" `
  -Action Update -ConfigFile "C:\Users\Tester\Spark Image Tools\personal.json" `
  -ApiKeyFile "C:\Users\Tester\Spark Image Tools\private\api.key"
```

更新会先生成带时间戳的配置备份，再重建本地虚拟环境；它不会覆盖个人请求日志或输出目录。卸载只删除 `.venv`，保留配置、Key、日志和已保存图片：

```powershell
.\client\windows\install-windows.ps1 -InstallDir "C:\Users\Tester\Spark Image Tools" -Action Uninstall
```

## 使用与恢复

实际 Harness 中应看到 `generate_image`、`edit_image`、`list_image_tasks`、`get_image_task` 和 `cancel_image_task`。提交先返回任务 ID；按阶段和前方单数继续查询。断网、工具重启或提交响应丢失后，先用 `list_image_tasks` 找回本人的任务，再使用同一个 `request_id` 重放；保存目录不可写时只修复目录后重取 `get_image_task`，不要重新提交推理。取消必须由用户显式发起，`cancelling` 表示后台清理仍在进行。

实际 Windows/Harness 的生图→编辑→生图、取消、断网/重启恢复、聊天内图片展示和自定义目录保存仍需在已标定后端可用后验收。当前票不伪造这些实机证据。
