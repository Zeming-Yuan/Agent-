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

T03 旧数据恢复边界：若 T03 之前的任务尚无内容指纹，且原素材已被删除，无法证明新上传内容等价。此时重用旧键返回409，detail含本人原 task_id，继续查询原任务/下载已有结果；不会重跑推理或猜测内容。需要重新创作时使用新键。已有 T03 内容指纹的请求不受此历史限制，删除原参考图后重传相同内容仍复用原任务。

T03 切片 B 的 `/v1/me` 只公开 Principal.owner。Key CLI 复用 KeyRegistry，`issue_to_file` 将一次性凭证排他写入0600私有文件，仅返回 key_id；创建/写入失败撤销新 Key，清理仅限本次创建的文件。轮换为先发同 owner 新 Key并验证，再撤销旧编号；撤销重复执行幂等。未增加 HTTP 管理接口或客户端可选 owner。任务、文件、参考图、请求映射、注册表在离线副本恢复后仍维持同一归属；生产 strict 与 contract 尚待 T04，状态保持 proposed。

T03 凭证交付的组合故障：即使注册表撤销失败，也独立清理本次创建的文件并保留既有文件。若数据库撤销或文件清理不能确认，抛出 KeyDeliveryError；CLI 非零退出并仅报告公开 key_id 与恢复指引，不报告原始 Key。此时不能声称已撤销；保持接入关闭，恢复注册表写入后按该 key_id 重试 revoke。仅当错误明确报告本次新建输出仍待清理（cleanup_pending）时，才核对并清理该输出；既有文件必须保留。原始交付错误不会掩盖必要的恢复编号。


T04 切片 A 在离线维护事务中收口：先验证全部归属和文件关联，再保存独占私有备份，回填历史 task_requests，并重建 tasks 删除全局 idem 唯一约束；原 rowid/ID/引用、列值、显式索引和触发器保留。旁表仍是权威归属。业务指纹提取为 Store 与迁移共用的 task_fingerprint，避免历史重放与在线提交采用不同算法。运行中任务及悬空/跨人引用拒绝迁移；不会自动重跑或把异常数据公开。当前 strict/runtime 收口尚待切片 B，ADR 暂仍 proposed；生产启用另等 #4 验收及明确接管记录。
