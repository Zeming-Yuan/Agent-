# 图片服务：已确认任务与实施计划

用户已确认14票拆分，并要求每个多步票写计划后一并发布GitHub。本目录只包含文档，不代表产品实现或新测试/实机验收已完成。

先读[父规格](../../specs/2026-11-14-image-service-reliability-and-multiuser.md)、[执行契约](2026-11-14-image-execution-contract.md)、[测量审计](2026-11-14-image-measurement-contract.md)。14票均涉及多个层/验证或实际环境操作，均需要计划；没有额外为单步杂项造票。

| 票 | 实施计划 | Blocked by |
| --- | --- | --- |
| T01 | [Expand：旧身份可在兼容结构上完成原有图片流程](2026-11-14-image-01-legacy-expand.md) | 无 |
| T02 | [迁移素材链路：两个测试身份的文件互不可见](2026-11-14-image-02-owner-file-migration.md) | T01 |
| T03 | [迁移任务链路：个人 Key 可生成、编辑、取图与轮换](2026-11-14-image-03-owner-task-migration.md) | T02 |
| T04 | [Contract：旧数据有明确归属后切换到完整多人隔离](2026-11-14-image-04-owner-contract-cutover.md) | T03 |
| T05 | [服务端续取：断线保留任务，后端离线仍能找回结果](2026-11-14-image-05-server-resume.md) | T04 |
| T06 | [MCP 续取：工具重启与保存失败只重取，不重生成](2026-11-14-image-06-mcp-resume.md) | T05 |
| T07 | [真实阶段与取消：确认保存或停止后才报告终态](2026-11-14-image-07-truthful-lifecycle.md) | T06 |
| T08 | [内存观测：一次创作可导出按阶段关联的完整曲线](2026-11-14-image-08-memory-evidence.md) | T07 |
| T09 | [安全开工：释放可确认、预算足够才加载下一模型](2026-11-14-image-09-safe-admission.md) | T08 |
| T10 | [公平轮转：已接纳用户不被持续插队并看到前方单数](2026-11-14-image-10-fair-queue.md) | T09 |
| T11 | [实机标定：启用有证据的 profile 并完成连续切换](2026-11-14-image-11-calibrated-switching.md) | T10 |
| T12 | [Windows 接入：实际桌面端显示进度、重连并保存图片](2026-11-14-image-12-windows-client.md) | T11 |
| T13 | [macOS 接入：升级个人配置并验收完整恢复链路](2026-11-14-image-13-macos-client.md) | T11 |
| T14 | [联合验收与恢复演练：两人双端在同一服务上完成闭环](2026-11-14-image-14-joint-acceptance.md) | T12、T13 |

每票含第一条失败测试、最小实现、反例测试、逐AC验证、文档/ADR同步、两个独立提交边界和恢复策略。尚未执行的测试与baseline明确标为未运行；引用私有配置/结果路径的命令是执行时输入，不包含任何真实凭证。

共享服务/状态/公共桥接串行整合；平台专属T12/T13可分别验收；T14等待两端。本次不修改或关闭父规格Issue。

