---
status: proposed
---

# 用旁表扩展对象归属，保留旧版写入

T01 使用 `object_owners(kind, object_id, owner)` 旁表，保留 files 的 4 列和 tasks 的 12 列及原有全局 idem 唯一约束。直接增加 owner 列会破坏旧版位置 INSERT；旁表允许旧版在 expand 后继续上传、写任务和保存结果。

`expand_ownership` 在单个 BEGIN IMMEDIATE 事务中补齐明确 legacy owner；重复执行保留既有归属。只读预检报告无归属文件、任务、幂等记录和运行任务，旧版新写入不会被触发器静默归属。T02/T03 才迁移文件/任务写入和用户访问路径，T04 收口后再将本决策改为 accepted。

过渡期保持生产 legacy 单身份访问；未具备全链路 owner 校验时不能开放多人生产入口。回退保留旁表和新写入数据，多 owner 数据存在后不得回退到共享可读的旧版。

T01 KeyRegistry 单独持久化凭证摘要和不可变的 owner/key_id；撤销不被重注册或默认 factory 重启抵消。HTTP 只把已解析的 Principal 放入 request.state，不改变尚待 T02/T03 迁移的文件与任务 API。legacy 拒绝非 legacy；staging 是隔离测试配置；strict 在 owner 迁移完成前拒绝启动。这一 fail-closed 过渡限制优先于提前开放严格模式，T04 收口时必须移除该限制并验证真正的 owner 路径。
