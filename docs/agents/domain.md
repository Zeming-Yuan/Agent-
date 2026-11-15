# Domain Docs

## 布局

采用 single-context：
- 根目录 GLOSSARY.md：领域术语。
- docs/adr/：架构决策记录。

这些文档按需生成，本次设置只记录约定。

## 探索前读取

探索代码前，读取根目录 GLOSSARY.md，以及 docs/adr/ 中与当前工作相关的 ADR。

如果根目录已有 GLOSSARY-MAP.md，则按其指引读取相关上下文的词汇表，
并检查相关的 src/<context>/docs/adr/。

文件不存在时直接继续，无需提示缺失或提前建议创建。
domain-modeling 在术语或决策明确时按需创建它们。

## 使用领域词汇

Issue 标题、重构建议、假设和测试名称使用词汇表中的规范术语。
发现真实的术语缺口时，记录给 domain-modeling 处理。

## ADR 冲突

建议与现有 ADR 冲突时，明确指出对应 ADR，并说明重新讨论的理由。
