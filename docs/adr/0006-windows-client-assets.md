---
status: accepted
---

# Windows 图片客户端专属资产

T12 在 Windows 侧只增加安装、配置和说明资产，复用既有 stdio MCP bridge、HTTPS `/v1`、个人 Key、CA 校验和服务端恢复契约。`make_config` 生成独立的 `command`、`args`、`cwd` 字段，避免中文与空格路径经过 shell 拼接；配置片段只引用私有文件，不携带凭证。

安装脚本使用当前用户的 Python 3.11+ 虚拟环境，不修改全局 PowerShell 执行策略。更新先备份配置并保留请求日志、Key 与图片；卸载只移除虚拟环境，保留个人数据。公共 bridge、打包器、任务协议和服务端状态机不在本票修改范围。

Windows 实机 Harness、真实后端标定、TLS 失败演练和双端完整链路仍需独立证据；未验收内容不得由静态配置测试替代。回退先保全个人配置、日志和图片，再删除 `.venv` 或恢复平台资产。
