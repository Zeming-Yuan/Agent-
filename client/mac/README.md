# macOS DeepSeek Harness 图片工具

本目录只提供 macOS 的安装和 Harness 配置层，复用公共 `spark_image_tools.py`、MCP 协议和服务端恢复契约。个人 Key、CA、配置、请求日志和图片必须保存在私有目录，不提交仓库或写入插件 JSON。

## 安装和升级

将包放在固定路径（例如 `~/Applications/Spark Image Tools`），准备个人 JSON 和 Key 后运行：

```bash
bash client/mac/install-mac.command \
  --action install \
  --install-dir "/Users/me/Applications/Spark Image Tools" \
  --config-file "/Users/me/个人 配置.json" \
  --api-key-file "/Users/me/私有/key"
```

配置至少包含 `base_url`（HTTPS `/v1`）、`api_key_file`、`ca_file`，可选 `output_dir` 和 `journal_path`。路径可以含中文和空格；桥接读取相对路径时以配置文件目录为基准。安装器要求 Python 3.11+，使用包内 `.venv`，并生成不含凭证的 `deepseek-harness-plugin.json`。`command`、`args` 和 `cwd` 是独立字段，避免 shell 再次拆分路径。

升级先备份个人配置，再重建虚拟环境：

```bash
bash client/mac/install-mac.command \
  --action update \
  --install-dir "/Users/me/Applications/Spark Image Tools" \
  --config-file "/Users/me/个人 配置.json" \
  --api-key-file "/Users/me/私有/key"
```

卸载只移除 `.venv` 和生成的插件片段，保留配置、Key、请求日志和图片：

```bash
bash client/mac/install-mac.command --action uninstall \
  --install-dir "/Users/me/Applications/Spark Image Tools"
```

## CA 与 Harness 进程

Python bridge 从配置的 `ca_file` 建立 TLS 校验；实际 Harness 的 Node 网络进程需要在其用户级启动配置中设置 `NODE_EXTRA_CA_CERTS` 指向同一份 CA。两者是不同进程，Python 成功不代表 Harness 已信任证书。不要用 `verify=False` 或关闭 TLS 校验。macOS 若提示局域网访问权限，请允许实际 Harness 进程访问服务。

将生成的 `deepseek-harness-plugin.json` 合并到实际 Harness 配置后重启，确认出现 `generate_image`、`edit_image`、`list_image_tasks`、`get_image_task` 和 `cancel_image_task`。主聊天模型继续使用 `spark-main`，并声明支持 text/image 输入。

## 使用和恢复

提交先返回任务 ID；按阶段和前方单数继续查询。断网、工具重启或提交响应丢失后，先用 `list_image_tasks` 找回本人任务，再用同一 `request_id` 重放；不要创建新任务。保存失败只修复输出目录后重取同一任务，服务端已保存结果不会触发第二次推理。更换 owner 后不应显示旧恢复列表；Key 轮换保持同一 owner。

实机验收需要在实际 macOS/Harness 记录 macOS、Harness、Python 版本及任务 ID，并完成生图→编辑→生图、阶段/排队、取消、断网/重启恢复、聊天展示和自定义目录保存。当前 Linux checkout 只验证配置和脚本边界，不能代替 macOS 实机、真实 TLS 或已标定后端证据。

回退时先停止使用新插件并保全配置、日志、图片和服务端任务，再删除 `.venv` 或恢复平台资源；不得恢复共享 Key 或盲目重新提交。
