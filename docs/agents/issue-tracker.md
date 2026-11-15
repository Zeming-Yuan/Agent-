# Issue tracker: GitHub

任务和规格记录在 https://github.com/Zeming-Yuan/Agent- 的 Issues 中。
使用 gh CLI；每条命令显式指定仓库，支持当前没有 Git remote 的目录。

## 常用操作

- 创建：gh issue create -R Zeming-Yuan/Agent- --title "..." --body-file <file>
- 读取：gh issue view <number> -R Zeming-Yuan/Agent- --comments
- 列出：gh issue list -R Zeming-Yuan/Agent- --state open
- 评论：gh issue comment <number> -R Zeming-Yuan/Agent- --body-file <file>
- 添加标签：gh issue edit <number> -R Zeming-Yuan/Agent- --add-label "<label>"
- 移除标签：gh issue edit <number> -R Zeming-Yuan/Agent- --remove-label "<label>"
- 关闭：gh issue close <number> -R Zeming-Yuan/Agent-

多行正文先保存到文件，再通过 --body-file 提交。
标签名称见 `triage-labels.md`。

技能要求“publish to the issue tracker”时，创建 GitHub Issue。
技能要求“fetch the relevant ticket”时，读取对应 Issue 及其评论。

## Pull requests as a triage surface

**PRs as a request surface: no.**

## Wayfinding

- Map：一个带 wayfinder:map 标签的 Issue，记录 Notes、
  Decisions-so-far 和 Fog。
- 子任务：优先使用 GitHub sub-issues；不可用时，在 Map 的任务列表中
  链接子任务，并在子任务顶部写 Part of #<map>。
- 类型标签：wayfinder:research、wayfinder:prototype、
  wayfinder:grilling、wayfinder:task。
- 阻塞关系：优先使用 GitHub 原生 Issue dependencies；
  不可用时，在子任务顶部写 Blocked by: #<n>, #<n>。
  所有阻塞任务关闭后，该任务才可开始。
- Frontier：按 Map 顺序选择未关闭、无未完成阻塞、且无人认领的子任务。
- 认领：开始工作前，使用 gh issue edit 的 --add-assignee @me。
- 完成：评论答案、关闭子任务，再将结论摘要和链接补入 Map 的
  Decisions-so-far。所有 gh issue 命令均指定 -R Zeming-Yuan/Agent-。
