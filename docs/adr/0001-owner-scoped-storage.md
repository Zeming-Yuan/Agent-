---
status: proposed
---

# 用旁表扩展对象归属，保留旧版写入

T01 使用 `object_owners(kind, object_id, owner)` 旁表，保留 files 的 4 列和 tasks 的 12 列及原有全局 idem 唯一约束。直接增加 owner 列会破坏旧版位置 INSERT；旁表允许旧版在 expand 后继续上传、写任务和保存结果。

`expand_ownership` 在单个 BEGIN IMMEDIATE 事务中补齐明确 legacy owner；重复执行保留既有归属。只读预检报告无归属文件、任务、幂等记录和运行任务，旧版新写入不会被触发器静默归属。T02/T03 才迁移文件/任务写入和用户访问路径，T04 收口后再将本决策改为 accepted。

过渡期保持生产 legacy 单身份访问；未具备全链路 owner 校验时不能开放多人生产入口。回退保留旁表和新写入数据，多 owner 数据存在后不得回退到共享可读的旧版。

T01 KeyRegistry 单独持久化凭证摘要和不可变的 owner/key_id；撤销不被重注册或默认 factory 重启抵消。HTTP 只把已解析的 Principal 放入 request.state，不改变尚待 T02/T03 迁移的文件与任务 API。legacy 拒绝非 legacy；staging 是隔离测试配置；strict 在 owner 迁移完成前拒绝启动。这一 fail-closed 过渡限制优先于提前开放严格模式，T04 收口时必须移除该限制并验证真正的 owner 路径。

T02 切片 A 将文件与 `object_owners` 在同一 BEGIN IMMEDIATE 中提交，读取/删除先验证归属。文件方法的 legacy 默认仅供尚未迁移的旧内部调用；所有已迁移 HTTP 文件入口显式传 owner。删除使用写事务串行检查在用引用与回收，跨人和未知 ID 都返回相同 404。T01 模拟旧写入的测试改用已冻结旧 Store，避免把 T02 的新归属写入当作旧版行为。

T02 切片 B 使用 `file_digests(owner,digest,file_id)` 旁表，仅用于同步参考图内容复用，联合主键限制本人去重，file_id 为随机 UUID。旁表与原 files/object_owners 写入同一 BEGIN IMMEDIATE；文件删除一并移除 digest。原 files/tasks 列数保持不变，旧 SQL 仍可写入，旧素材 ID 与关联不重命名。

任务提交在自己的 BEGIN IMMEDIATE 内复核所有素材归属，和删除在用检查串行，避免前置检查到接纳间被删除的悬空引用。任务旁表同时记录提交者 owner，内部 `worker_task` 取回持久身份供文件读取/结果保存；这是 T02 所需身份传递，不开放用户任务全权限入口。T03 仍负责用户 task/submit 访问与按人幂等迁移，T04 负责严格收口，因此 ADR 仍 proposed、生产仍 legacy。

文件创建的失败清理只回收已成功排他创建的路径，覆盖事务提交异常；内容命中已有参考图不取得其清理所有权。多人数据写入后，只可停写保全数据并回退到具备同等文件归属检查的版本，不可直接运行 T01/更早共享可读实现。

T03 切片 A 增加 `task_requests(owner,request_key,fingerprint,task_id)` 旁表。新幂等指纹使用规范业务参数和按用途/顺序排列的素材内容 SHA256；在同一个 BEGIN IMMEDIATE 中重新检查素材 owner、计算指纹、读取/补齐映射、检查全局容量并写任务/归属。非 legacy 的 tasks.idem 为 NULL；legacy 保留原始指纹及全局键表示，以支持 expand 副本中的旧写入/重放。生产不允许旧写入和多人接入并存，T04 仍负责 contract，因此状态保持 proposed。

调用方清单：gateway 的任务提交/查询/取消显式传入鉴权 owner；image_routes 的提交/等待/结果路径显式传 owner；Store 内部 update/next_task 不借用默认用户查询，图片和媒体 worker 通过 worker_task 读取持久身份并传入素材/结果接口。既有测试 legacy 默认仅作为 expand 兼容接口保留，T04 再移除默认值。权限404、业务冲突409、全局满载429/Retry-After保持明确区分。未引入新状态机、队列公平性或个人配额。
