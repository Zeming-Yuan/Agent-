# 图片服务执行契约与基线

本文件是 T01—T14 计划共同输入；父规格见 ../../specs/2026-11-14-image-service-reliability-and-multiuser.md。这里定义未来实现接口，不表示当前已有这些能力。

## 执行边界

- 本次只交付计划与 GitHub 文档/Issue，不实施产品、不发放真实 Key、不运行生产图片负载。
- 产品工作区当前不是 Git 仓库。执行前使用 source-baseline.json 核对源码；仅含文档的 GitHub 仓库不是完整产品源码。不得在文档仓库伪造产品实现提交。
- 每个计划标明逻辑提交边界；在受控产品 Git checkout 中按清单提交。若源码仍非 Git，保存逐任务审查快照和 SHA256 变更清单，保全回退材料，不擅自初始化或全量上传工作区。
- T01→T02→T03→T04→T05→T06→T07→T08→T09→T10→T11 串行整合；T12/T13 只修改各自专属资源，可分别推进；T14 等待两端。公共文件变更先回到主干串行整合。
- 同一服务实机标定与部署修改互斥；开始下一硬件运行前确认前一运行及清理结束。
- 20GiB 保护保持启用；不新增个人配额、计费、每日次数或个人限流。保留既有全局 4 个未完成媒体任务和 2GiB 文件总量边界。

## 兼容与身份接口（T01 定义，T02/T03 迁移，T04 收口）

新模块 services/identity.py 定义 Principal(owner: str, key_id: str) 与 KeyRegistry(db_path: Path)。方法：register(owner: str, raw_key: str) -> Principal、issue(owner: str) -> str、resolve(raw_key: str) -> Principal | None、revoke(key_id: str) -> None。issue 返回一次性原始凭证，数据库只存 SHA256 摘要；raw_key 具有足够随机熵，原始值不进入日志。运维命令将新 Key 写入用户指定的独占私有文件。

create_app 保持旧位置参数 root、token；新增 keyword-only key_registry: KeyRegistry | None 和 identity_mode: str，允许 legacy/staging/strict 三值。legacy 只接受 legacy owner；staging 只用于受控隔离环境；strict 拒绝任何无归属回退。请求身份来自 request.state.principal。

services/ownership.py 提供 expand_ownership(db_path: Path, legacy_owner: str) -> None、preflight_ownership(db_path: Path) -> dict、require_owner(db, kind: str, object_id: str, owner: str) -> None。采用旁表 object_owners(kind, object_id, owner) 保存归属，不改变旧 files/tasks 表的列数；旧版 INSERT INTO ... VALUES(...) 因此继续兼容。require_owner 对不属于该 owner 的对象统一抛 HTTPException(404, 'Object not found')。

迁移后的 Store 文件方法增加 keyword-only owner: str：file、path、add_file、save_generated、delete_file。任务方法 task、submit 同样显式接收 owner。内部 worker 通过 worker_task(tid) 获取含 owner 的任务，不把内部全权限入口暴露给 HTTP。T04 之后用户路径方法不保留默认 owner。

T03 新增 task_requests(owner, request_key, fingerprint, task_id) 旁表，联合主键(owner, request_key)；旧 tasks.idem 保留兼容，非 legacy 新任务写 NULL。INSERT、素材归属、幂等命中和全局容量检查使用同一个 BEGIN IMMEDIATE 事务；重放在容量检查前返回。指纹以规范业务参数及 owner 范围内素材 SHA256 计算，不以随机临时上传 ID 作为业务身份。T04 在确认无旧写入后移除全局 idem 唯一索引/兼容读取，重建表时显式列名并保留原 rowid 顺序。

GET /v1/me 返回当前 owner；GET /v1/tasks 返回 {object:'list', data:[task], has_more:bool, next_cursor:str|null}，仅本人，按稳定入队序分页。状态筛选使用 status 参数，after 为本人可访问任务的游标；他人游标与不存在游标统一 404。

## 共享测试夹具（由 T01 交付 tests/conftest.py）

owner_env 为 pytest fixture，使用独立临时数据库和临时随机测试 Key，提供：client(*, backend=None, run_worker=False, identity_mode='staging') -> TestClient；auth(owner: str) -> dict[str,str]；upload(c, owner='A') -> str；submit(c, owner='A', *, kind='image_generate', request_key=None, **options) -> httpx.Response；wait_task(c, tid, owner, predicate, timeout=3.0) -> dict；new_backend(*, hold=False, hold_stop=False) -> ImageBackend；registry: KeyRegistry；keys: dict[str,str]；root: Path。

client 运行真实 create_app、鉴权、Store 与 worker，外部推理用 httpx.MockTransport。upload 上传由 PIL 生成的 8×8 PNG；submit 默认 prompt='fixture'，传入 owner 对应 Bearer 并可传 Idempotency-Key。wait_task 轮询真实 HTTP 状态直到 predicate 或单调时钟截止，截止时抛 AssertionError 并输出最后任务，不永久等待；只用于测试，不制造成功状态。

ImageBackend 的 jobs 是实际收到的 /prompt 请求列表；started、finish、release_stop、offline 为 threading.Event。默认 finish/release_stop 已 set；hold/hold_stop 对应清除。/prompt 记录规范 UUID 并 started.set；/history 在 finish 未 set 时返回空，完成时返回有效 PNG 引用；/view 返回可解码 PNG；/interrupt 等待 release_stop 后移除指定运行任务；/queue 如实返回仍运行的 ID；/system_stats 在 offline 后返回 503。异步等待使用 asyncio.to_thread(event.wait, bounded_timeout)，不能阻塞应用事件循环。未知路径返回明确 404，不能用万能成功隐藏协议错误。

测试断线、响应丢失和阶段事件时，在此外部后端扩展受控事件，不 mock Store 或手动改 completed。生产模式不得安装测试控制端点。

## 任务与客户端接口（由对应票交付）

T05 定义 owner 范围的已有请求 lookup 和任务列表。重放已有任务不检查后端 readiness；创建新工作才检查。查询、超时和等待连接中止不触发取消。

T06 定义 client/request_journal.py 的 RequestJournal(path: Path, service: str, owner: str)，prepare(request_id: str, fingerprint: str, payload: dict) -> dict、accepted(request_id: str, task_id: str) -> None、pending() -> list[dict]。SQLite 联合键(service, owner, request_id)；同键不同指纹 ValueError；先提交本地日志再发网络请求。ImageBridge 构造新增 journal_path: Path | None；generate/edit 新增 keyword-only request_id: str | None，向后兼容旧位置参数。通过 /v1/me 获取稳定 owner 后才读取日志；MCP 新增 list_image_tasks，generate/edit 暴露 request_id 可选参数。凭证不写日志。

T07 用 task_runtime 旁表扩展 stage、stage_seq、stage_started_at、stage_updated_at、blocked_reason、cancel_requested，保留旧 status/progress/result 契约。Store.transition(tid: str, *, status: str, stage: str, expected_seq: int, result: dict | None = None, error: str | None = None) -> dict 执行事务 CAS；终态不可改写。取消先登记 cancel_requested，运行任务继续 running/cancelling，确认后端停止后再 cancelled；queued 可直接取消。step/steps 只用于生成阶段，未知时为 null。

T08 在 services/image_telemetry.py 定义 ResourceSample(available_bytes:int, cgroup_headroom_bytes:int, observed_at:float, resident_profiles:frozenset[str] | None, running_prompts:tuple[str,...] | None, release_epoch:int)。observed_at 使用本机 monotonic 秒；跨主机事件靠 UTC 时间和 host_id 对齐，禁止跨主机相减单调时钟。后端观测缺失以 None 表示，不能当空集合。后台只读观测仅在专用回环/运维身份可见。

T08 在 scripts/image_measurement.py 定义 validate_run(record: dict) -> list[str]。record 至少包含 run_id、request_id、task_id、profile、runtime_hash、host_match、backend_executions、status、output_verified、submitted_ns、completed_ns、downloaded_ns、saved_ns、memory_samples、guard_events。时间点来自同一客户端单调时钟且有序。原始图片另外保存并解码校验，报告不保留凭证或真实业务内容。

T09 定义 services/image_resources.py 的 MemoryBudget(peak_increment_bytes:int, margin_bytes:int, reserve_bytes:int, valid_until:float, runtime_hash:str)、AdmissionDecision(allowed:bool, reason:str)；admit(sample:ResourceSample | None, budget:MemoryBudget | None, *, now:float, runtime_hash:str, released:bool, max_age:float) -> AdmissionDecision。稳定窗口、最大采样年龄、等待上限必须为正且由已签署的标定配置提供；缺失则不启用该 profile，不编造生产默认数值。测试中的合成数值只用于验证分支。

T10 定义 services/image_queue.py 的 choose_next(heads:list[dict], last_owner:str | None) -> str | None。heads 只包含每个 owner 的最早未完成任务，含 id、owner、eligible；按 owner 稳定排序后从 last_owner 后循环选首个 eligible。claim 与持久游标写入同一事务。queue_ahead 由同一规则模拟快照，含当前占用任务；目标尚不具备资源条件时为 null 并给原因，不伪装成确定排位。

T11 定义 scripts/image_measurement.py 的 validate_profile_report(report:dict) -> list[str]，profile 报告包含精确运行时/模型标识、input_envelope、cycles、raw_runs、budget、guard_events、min_available_bytes、release_proof、baseline_status。只有所有必要字段及实际证据通过才启用；schema/验证不是实机通过的替代品。

T14 定义 scripts/check_image_acceptance.py 的 check_acceptance(report:dict) -> list[str] 与 CLI --report <file>。报告包括父规格 20 个 AC 的证据链接、两端实际平台/Harness 版本、本人/跨人请求结果、有效 profile 报告、后端工作计数和恢复演练记录。缺项、未运行或失败一律非零退出，不能从文件存在推导成功。

## 独立提交与恢复

每个计划的 Task 1、Task 2 分别为独立逻辑提交，提交必须包含通过的测试、该任务实现与对应文档。不要把多个 ticket 的共享迁移同时交给不同实现者。回退先停接单、保全新增任务/素材、定向停止并确认后端空闲；多人数据产生后只回退到 owner 感知版本。不能以回滚为由降低保护器、丢失新结果或恢复公共共享访问。

