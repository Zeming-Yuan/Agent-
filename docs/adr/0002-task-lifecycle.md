---
status: accepted
---

# 持久任务阶段与取消清理

T07 在 task_runtime 旁表保存正交阶段、单调 stage_seq、阶段起点/最近有效更新时间、阻塞原因和取消请求，保留 tasks 十二列与五态。取消请求在同一写事务中登记；运行中保持 running/cancelling，清理退出后才 cancelled，queued 直接收敛。状态/结果/阶段使用 BEGIN IMMEDIATE 与 expected_seq CAS，已达终态不可覆盖。用户操作先校验 owner，内部 worker 不借用用户身份。

切片A交付取消路径；事件归属与其它终态路径在切片B接入同一状态写入边界。不会把 /free 受理等同模型释放，不增加第二套调度。回退保留旁表和新增任务/文件，停接单并确认后台停止；不能恢复提前 cancelled 的行为。

T07 A审查修复：原生 asyncio 重复取消不得打断清理；清理结算后向上继续传播服务关闭。取消与已返回结果相遇时明确 cancelled，回收尚未交付结果，不滞留 cancelling。状态和阶段以单条 JOIN 读取同一提交快照。
