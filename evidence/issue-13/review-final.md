# T12 review record

固定点到 HEAD 的所有 review 都使用受控 checkout `/home/clusteradmin/.codex/workspaces/agent-mm-issue-12-20261116`，只审 T12 diff，不审全量历史：

- Slice A: `c25211e...c4eb33b`。初审发现 requirements/bridge 路径、Harness Node CA、私有 ACL 和首装身份文件问题；修复后复审无未处理问题。
- Slice B: `c4eb33b...6250d47`。初审发现同上边界，修复后复审无未处理问题。
- Installer hardening: `6250d47...ccc9437`。Spec 初审发现 PowerShell 5.1 编码、必需 ConfigFile/ApiKeyFile 和证据措辞问题；修复后复审无未处理问题。
- Verification/docs: `ccc9437...a182e69`、`a182e69...4355017`、`4355017...3322d68`、`3322d68...11ad4d2`。复审确认静态检查与实际 Windows/Harness 边界已区分；计划 checklist、AC 映射和 evidence 摘要已同步。

最终 Standards 结论：无未处理的项目规范违反或 Fowler baseline smell。

最终 Spec 结论：无未处理的 T12 代码/文档范围问题；本票 AC-1—AC-4 的真实 Windows/Harness、TLS/Key、端到端生成/恢复和依赖 #12/T11 仍明确未验证，不能据离线回归关闭票据。
