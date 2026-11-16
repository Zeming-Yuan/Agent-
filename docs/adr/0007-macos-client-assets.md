---
status: accepted
---

# macOS 图片客户端专属资产

T13 只在 `client/mac/` 增加 macOS 安装、配置和说明。`configure.py` 是插件生成的唯一实现，生成独立的 `command`、`args`、`cwd` 字段，使用绝对 POSIX 路径，中文和空格不经过 shell 拼接；插件片段只引用个人配置文件，不携带 Key 或 Authorization。

安装器要求 Python 3.11+；源码 checkout 必须显式提供独立 `--install-dir`，私有 bundle 才默认使用自身根目录，避免改写仓库。安装器从显式个人 JSON 校验 HTTPS `/v1`、`api_key_file` 和 `ca_file`，再创建虚拟环境并调用 canonical `configure.py`。更新先备份配置；卸载只删除虚拟环境、插件片段和本次安装生成的 bridge/configure 副本，保留个人 Key、请求日志、恢复记录和输出图片。安装器不得回退到共享 `api_key` 或固定 `spark-image.json`。

Python bridge 的 CA 配置与实际 Harness 网络进程的 `NODE_EXTRA_CA_CERTS` 是两个独立边界，任一进程证书不受信都必须明确诊断，不得关闭 TLS 校验。公共 bridge、请求日志、服务端任务状态机和打包器不在本票修改。

Linux checkout 只验证配置、脚本语法和离线恢复说明；真实 macOS/Harness、TLS、局域网权限、生成→编辑→生成、取消、断线重启恢复和本地保存仍需平台证据。回退先停止使用新插件并保全新增数据，再删除 `.venv` 或恢复 macOS 资产，不恢复跨用户共享访问。
