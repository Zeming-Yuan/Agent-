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

## T02 素材归属迁移（2026-11-15，切片 A）

受控 staging 的上传、鉴权下载和删除使用 Key 解析的 owner。跨人及不存在的文件统一 404 `Object not found`，本人仍在排队/运行任务中使用的素材删除返回 409。上传文件与归属写入同一 SQLite 事务，全局 2GiB 原子容量检查保留。生成保存的兼容入口暂默认 legacy，后续切片补齐工作任务到结果的身份传递。

生产仍使用 legacy 单身份；strict 未开放。此处为临时数据库及外部后端替身的离线 HTTP 验证，不代表实机或 Windows/macOS Harness 验收。逐步 red/green 与回归证据见 `evidence/issue-3/`；类型/静态/构建门禁未配置（N/A）。回退先停接单并保存新增数据；已有多 owner 素材时必须保留归属检查，不可退回共享可读版本。
