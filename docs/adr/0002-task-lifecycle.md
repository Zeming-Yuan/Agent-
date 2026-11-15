---
status: accepted
---

# 持久任务阶段与取消清理

T07 在 task_runtime 旁表保存正交阶段、单调 stage_seq、阶段起点/最近有效更新时间、阻塞原因和取消请求，保留 tasks 十二列与五态。取消请求在同一写事务中登记；运行中保持 running/cancelling，清理退出后才 cancelled，queued 直接收敛。状态/结果/阶段使用 BEGIN IMMEDIATE 与 expected_seq CAS，已达终态不可覆盖。用户操作先校验 owner，内部 worker 不借用用户身份。

切片A交付取消路径；事件归属与其它终态路径在切片B接入同一状态写入边界。不会把 /free 受理等同模型释放，不增加第二套调度。回退保留旁表和新增任务/文件，停接单并确认后台停止；不能恢复提前 cancelled 的行为。

T07 A审查修复：原生 asyncio 重复取消不得打断清理；清理结算后向上继续传播服务关闭。取消与已返回结果相遇时明确 cancelled，回收尚未交付结果，不滞留 cancelling。状态和阶段以单条 JOIN 读取同一提交快照。

## T07 切片 B 决策

唯一纯reducer apply_event负责阶段单调性、有效采样及终态证明；Store.event在BEGIN IMMEDIATE读取一致快照、分配序号并同时提交tasks/runtime，transition以expected_seq CAS包装既定内部命令。旧image update调用也汇入同一边界，避免第二状态机。HTTP任务读取采用单JOIN，同阶段不重置起点。

ComfyEventStream只处理固定外部协议：确认client sid后提交，normalize_event只承认可关联prompt及固定节点事件；阶段/采样去重在reducer，失联不重跑。execution_error只传安全类别，不持久化原始提示词/输入/异常。MCP不镜像任务状态，只把权威stage渲染成中文、过滤旧progress。

输出先写私有临时文件并fsync，再在容量/owner同一事务内排他link、目录fsync和元数据提交。慢数据I/O不占DB写锁，写线程与原生取消都必须结算后才收敛。此处fsync验证在Linux服务器端；双端只消费公共桥接。崩溃孤儿文件由停写后的受控核对维护处理，不能自动重跑。

最后串行控制权包含后端停止、history/scratch及未交付结果回收。清理不明停止worker与新准入；单纯观测丢失不伪造进度，仍可通过history安全取结果。本票不提供模型释放证明或资源预算。扩展可向前兼容，回退须保留最终取消规则与显式列写入；不删除旁表或新增数据。
