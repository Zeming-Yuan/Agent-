# 生图和图片编辑接口

统一入口：`https://192.168.10.77:18443/v1`，使用现有 Bearer 凭证与项目 CA。当前部署进度及实际验证以 README 和 evidence/image-deploy-20261114 为准。

- 聊天/看图：`spark-main`，Chat Completions，200000 总上下文。
- 文生图：`spark-image`，Z-Image-Turbo BF16，1024默认，8步，单张并发。
- 图片编辑：`spark-image-edit`，Qwen-Image-Edit-2511 BF16、BF16视觉文本编码器，最多3张参考图；fast为Lightx2v BF16 4步加速，standard20步、high40步为原版编辑。Mac工具默认fast，直接API未指定quality仍默认standard。
- 主模型和生图模型接口不同；生图/编辑通过 Agent 工具调用，不能仅在聊天模型下拉框选择图片模型。

## 异步任务（Agent推荐）

`POST /v1/tasks`：

```json
{"kind":"image_generate","options":{"prompt":"商业摄影，白色保温杯，米色石台，柔和侧光，无文字","size":"1024x1024","seed":417,"title":"品质生活"}}
```

返回202和任务ID。`GET /v1/tasks/{id}` 查询 queued/running/completed/failed/cancelled；`POST /v1/tasks/{id}/cancel` 取消。`Idempotency-Key` 可避免重试重复排队，同一key不同输入返回409。长任务不要盲目重提。

上传参考图：`POST /v1/files` multipart字段file，返回 file_id。

```json
{"kind":"image_edit","options":{"prompt":"将背景改为现代厨房，保留商品主体和包装文字","image_ids":["file-上传返回的32位ID"],"size":"1024x1024","quality":"fast","seed":417}}
```

image_ids只接受本服务上传ID；拒绝URL、路径、任意工作流；需1至3张。支持PNG/JPEG/WebP，每张<=12MiB、<=16MP，实际推理参考图会按模型工作流缩放。

任务完成结果包含file_id、content_url和mime_type。`GET /v1/files/{id}/content` 返回需鉴权PNG；桌面端应取回后保存为附件，或使用下述MCP桥接，不要把需Bearer的URL直接当作普通img链接。

## OpenAI风格同步接口

- `POST /v1/images/generations`：JSON `{ "model":"spark-image", "prompt":"…", "size":"1024x1024", "n":1, "response_format":"b64_json" }`。
- `POST /v1/images/edits`：multipart字段image或image[]（可重复1至3次）、prompt、model=spark-image-edit、size、quality、n=1、response_format=b64_json。
- 成功返回created、data[0].b64_json，以及本地扩展file_id和task_id。同步等待约570秒；若504含task_id，继续查询原任务。异步任务推理上限900秒。
- 当前支持尺寸：1024x1024、1152x896、896x1152、1280x768、768x1280。暂不宣称支持OpenAI所有images字段、URL结果或所有模型功能；暂不支持mask，传入会422明确拒绝。

## 商品外观与质量

需要精确保留原商品时，优先上传透明PNG前景，在image_generate options指定foreground_file_id；生成背景后合成原前景。纯不透明商品图会明确拒绝此模式，可改用image_edit。准确标题用title叠字，价格/Logo建议业务排版。生成式编辑需复核商标、外形和文字；不承诺与Grok Bot相同效果。

## Mac工具包

私有包 `.private/mac-image-tools.zip`，包含CA、现有私密api_key、桥接程序、固定依赖、安装脚本和接入说明。通过受信任渠道转交；不提交代码仓库。

MCP工具：generate_image、edit_image、get_image_task、cancel_image_task。先提交再查询，完成返回图片内容并保存到Mac的 `~/Pictures/Spark Agent`。实际Harness须把主聊天模型声明为支持image输入，才会接纳工具返回的图片。服务器侧的stdio验证不能替代实际Mac桌面验收。

## 实测与等待

1024生图20张基准中位11.66秒、P95 12.67秒；该基准在最终VAE修正前，最终配置3张生图回归分别12.233、11.604、13.425秒；Mac包桥接完整生图取图18.21秒。快速编辑单图冷加载约368秒、连续双参考图编辑36.41秒；生图与编辑切换会重新加载，后台串行排队。完整时间含网关处理与取图，不等于仅采样耗时。原版20步编辑一次203.66秒（含本次切换/加载）；快速编辑/合成/取消验证期间MemAvailable最低29.69GiB，另一次原版编辑最低28.50GiB，20GiB保护器继续启用。

样张说明：改杯身颜色与双参考换背景已人工查看；透明前景合成验证保留像素和准确中文标题，但当前夹具是合成商品形状，并非真实SKU的美术验收。没有与Grok进行同素材盲测；生成结果可能出现虚构小字、Logo或细节变化，不能保证达到相同效果。

## T02 素材归属迁移（2026-11-15，离线验证）

受控 staging 的上传、鉴权下载、删除、image_ids、透明前景及 PDF/video 的 file_id 引用使用 Key 解析的 owner。跨人及不存在的文件统一 404 `Object not found`，在后端就绪检查和入队前验证。本人排队/运行任务中使用的素材删除返回 409，外人同样请求仍为 404。全局 4 个未完成任务、2GiB 文件总量及既有图片限制不变，没有个人配额。

同步编辑自动上传按 `(owner, digest)` 去重，仅保存随机不透明 file_id；不同人相同内容是独立对象，内容哈希不是公开 ID。同一人的已有参考图可复用；失败仅回收本次创建且未被任务使用的素材。普通上传仍使用随机独立 ID。文件、归属、参考图 digest 写入共用 BEGIN IMMEDIATE，全局容量检查保持原子；任务提交在同一写事务内重新检查素材归属，与删除的在用保护串行。排他创建失败不得删除同名既有文件。

图片和既有媒体 worker 从持久任务归属读取素材，图片结果写回同一 owner；同步等待也按请求 owner 取回结果。任务写归属仅是素材链路的必要身份传递：任务查询/取消隔离、按人幂等和任务列表仍由 T03/T04 完成。生产仍固定 legacy，strict 继续拒绝启动，staging 不得作为多人生产入口。

本票验收映射、逐步 red/green、独立审查、受影响回归和复测入口见 `evidence/issue-3/acceptance.md`。测试使用临时数据库、A/B 临时 Key 及外部后端替身，不代表真实 HTTPS/模型或 Windows/macOS Harness 验收；这些仍未验证，归后续 T14。类型/静态/构建门禁未配置（N/A）。回退先停接单并保存新增数据；多 owner 数据存在后必须保留归属检查，不能退回共享可读版本。

## T03 任务归属迁移：切片 A（2026-11-15，离线）

上述 T02 的任务查询/取消及按人幂等待迁移说明是历史状态。现在受控 staging 中，任务查询与取消仅允许本人；跨人和未知任务统一返回 404 `Object not found`。同步图片等待同样使用已鉴权 owner；worker 使用内部 `worker_task` 取回持久归属，不向 HTTP 暴露全权限读取或 owner 字段。

幂等范围为 `(owner, Idempotency-Key)`：同人同键同业务输入复用原任务，同键不同输入 409，不同 owner 同键独立。素材身份以流式 SHA256 内容判定并保留参考图顺序与用途，临时上传 ID 改变不影响重试；提示词、尺寸、质量、seed、标题等业务参数参与指纹。新键表示新创作。已命中请求先于全局四单容量检查返回，不额外占位。后端离线时的无就绪检查重放由后续 T05 处理。

`task_requests` 旁表与任务、归属在同一 BEGIN IMMEDIATE 中写入；保留原 tasks 12 列和全局 idem UNIQUE，非 legacy 写 NULL。legacy 新写入保留旧指纹表示；旧幂等记录经 owner 校验后补入旁表，冻结旧版双向兼容测试覆盖只含 legacy 的副本。混合 owner 库不能交给旧版运行。生产仍 legacy，strict 仍拒绝启动；任务列表/contract 收口及生产多人开放不属于此切片。

T03 旧数据恢复边界：若 T03 之前的任务尚无内容指纹，且原素材已被删除，无法证明新上传内容等价。此时重用旧键返回409，detail含本人原 task_id，继续查询原任务/下载已有结果；不会重跑推理或猜测内容。需要重新创作时使用新键。已有 T03 内容指纹的请求不受此历史限制，删除原参考图后重传相同内容仍复用原任务。

## T03 身份查询与 Key 运维（切片 B）

`GET /v1/me` 返回 `{"owner":"当前身份"}`，只来自已验证凭证；同一 owner 的多把有效 Key 返回相同身份。未知/撤销 Key 返回401，并保留请求 ID 与 WWW-Authenticate。换 Key 不改变任务、参考图与结果归属。请求体或 options 伪造 owner/key_id 返回422。

维护者在本地通过 `python -m services.identity --db <注册表路径> issue --owner <稳定身份> --out <新私有文件>` 发放凭证；命令只输出 key_id，原始值只写独占创建的0600文件。`revoke --key-id <公开编号>` 可重复执行。服务器注册表仅存摘要和映射；命令参数、日志和恢复记录不传原始凭证。文件交付失败会撤销本次 Key 并清理本次新建的残片，不覆盖或删除既有文件。

临时 Key CLI、同步/异步相同请求身份、轮换后原结果访问、重启以及新的隔离副本恢复均已有自动化证据，见 `evidence/issue-4/acceptance.md`。尚未验证真实 HTTPS/MCP、物理图片后端、Windows/macOS Harness 或生产切换；完整交付仍等待后续门禁。

T03 凭证交付的组合故障：即使注册表撤销失败，也独立清理本次创建的文件并保留既有文件。若数据库撤销或文件清理不能确认，抛出 KeyDeliveryError；CLI 非零退出并仅报告公开 key_id 与恢复指引，不报告原始 Key。此时不能声称已撤销；保持接入关闭，恢复注册表写入后按该 key_id 重试 revoke。仅当错误明确报告本次新建输出仍待清理（cleanup_pending）时，才核对并清理该输出；既有文件必须保留。原始交付错误不会掩盖必要的恢复编号。


## T04 contract 与身份配置

当前源码的用户 Store 接口要求显式 owner，在线提交只使用 task_requests 的(owner,request_key)映射。历史 tasks.idem 保留值用于审计/恢复，不再提供全局回退。身份模式缺失的生产 factory 拒绝启动；strict 只使用既有个人注册表，在启动前检查离线 contract 标记与归属完整性。迁移命令、备份和回滚边界见 OPERATIONS.md 的 T04 章节。

已完成任务的本人素材/结果删除记录在 file_tombstones；删除结果后下载明确404，任务身份和幂等映射保留，不重新生成。未知缺失、跨人引用和运行中未收敛任务不允许切换。架构已实现不等于生产已启用：#4仍OPEN，本轮仅离线副本与受控外部后端替身验证，生产映射/发布/恢复仍未验证。


## T05 服务端续取：切片 A（2026-11-15，离线）

受控源码的异步图片提交先按本人业务指纹读取 Idempotency-Key：命中直接返回原任务，输入冲突409。后端离线不阻止已有任务查询、本人列表、幂等重放或鉴权下载已保存结果；真正的新工作仍须后端就绪并经过事务内幂等/全局容量复查。

`GET /v1/tasks?status=completed&limit=20&after=<本人任务ID>` 返回 `object: "list"`、`data`、`has_more` 和 `next_cursor`（末页为 null）。按接纳顺序升序，时间相同仍稳定排序；默认20条，limit为1..100。status可为queued/running/completed/failed/cancelled，非法筛选422。游标先检查本人归属，跨人/未知/空游标一致404；可用不同当前状态的本人任务作为游标。列表不依赖后端，不公开owner或内部幂等指纹。

本切片8项HTTP测试与red/green记录在 evidence/issue-6；同步生成/编辑离线重放、断线与完整恢复由切片B接续，当前尚未完成。仅使用临时身份/数据库及外部图片后端替身，未部署或实机验收。


## T05 服务端续取：切片 B（2026-11-15，离线）

本段取代切片A中“同步待完成”的中间状态。同步生成、同步编辑和异步图片提交使用相同的本人幂等读取顺序；已命中任务不检查后端或worker就绪。同步编辑仍以同owner参考图内容参与指纹，失败接纳仅清理本次自动上传的参考图。无请求键的新同步编辑保持上传前的离线拒绝。

连接断开或等待协程被取消只结束HTTP等待，不更新持久任务、不取消worker；显式取消接口保持原行为。同步570秒等待到期返回504，detail包含原task_id；继续GET原任务或使用原Idempotency-Key重放，不换新键。异步响应丢失可先GET本人列表，再查询或重放原请求；单次查询超时不改变任务状态。

已保存图片无需推理后端在线即可下载。本人删除结果后，原任务和请求映射继续保留；下载与同步重放明确404，异步重放仍返回原任务及原结果引用，不重跑模型。相同业务输入的新键表示新创作，离线时仍503。

已contract的strict运行时重启先只读验证完整归属，再在worker启动前将中断的running任务标记failed（Service restarted during processing）；queued和completed保留。worker恢复时先沿用既有后端清理策略，再执行queued，不续算或重放failed任务。迁移/维护预检仍拒绝running；无归属、悬空、跨人、缺请求映射等仍拒绝启动且不写库。

本票34项恢复测试、逐AC映射和复测命令见 evidence/issue-6/acceptance.md；进程崩溃通过子进程os._exit复现，图片推理使用受控外部协议替身。生产部署、真实HTTPS/MCP/图片节点、Windows/macOS Harness、GPU内存/性能尚未验证，由后续现有票继续验收。未配置类型/静态/构建门禁（N/A），没有把受影响回归当作全量门禁。

## T06 MCP 续取：切片 A（2026-11-15，离线）

公共桥接首次生成前先通过 GET /v1/me 确定 owner，将 request_id 与业务指纹持久化后才 POST /tasks，使用同一 Idempotency-Key。generate_image 可传 request_id；跨调用重试必须复用该值，新创作省略时生成新 UUID，不能按提示词永久去重。同键不同输入在本地拒绝。默认日志 ~/.local/state/spark-image-tools/requests.sqlite3，也可传 journal_path；日志按规范服务 URL 与稳定 owner 隔离，不存 Key。

切片 A 仅交付无参考素材生成的持久身份；编辑/素材、本人列表、原子保存及显式个人包入口由切片 B 接线。证据 evidence/issue-7/：01-red 缺 journal_path，01-green 真实 call_tool/HTTP/Store/worker 丢响应重启后同任务且一次后端执行，a-regression 3 passed。生产、双端 Harness 与真实后端未验证；未配置类型/静态/构建检查为 N/A。
