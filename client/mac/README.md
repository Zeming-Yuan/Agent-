# Mac DeepSeek Harness 生图与编辑接入

本包仅供可信局域网用户，api_key 是私密凭证，不上传公共仓库。服务器仍是 https://192.168.10.77:18443/v1。

1. 把本目录放在 Mac 的固定路径，例如 ~/Applications/SparkImageTools；不要保留在临时解压目录。
2. 运行 `bash install-mac.command`，需要 Python 3.11+。脚本仅创建本目录的虚拟环境与插件片段。
3. 在实际 DeepSeek Harness 的插件配置中合并生成的 deepseek-harness-plugin.yaml，保留其他配置。该格式来自已检查的 @deepseek-ai/dsh-mcp-client 插件接口；不同 Harness 版本请由本地 Agent 核对。
4. 聊天 Provider 继续配置 spark-main、OpenAI Chat Completions、200000 总上下文和合理输出上限；模型输入能力声明为 text 和 image，否则 Harness 会拒收 MCP 返回的图片。不要把 spark-image 当作聊天模型。
5. 聊天 Provider 的 Node 进程仍需在启动前设 NODE_EXTRA_CA_CERTS 指向本包 agent-root-ca.crt；Python 生图桥接会自行读取该 CA，保持 TLS 校验。macOS 如提示局域网权限，请允许实际 Harness 进程访问。
6. 重启实际 Harness，确认工具列表出现 generate_image、edit_image、get_image_task、cancel_image_task（公开名称带 mcp__spark_images__ 前缀）。

示例：
- “生成一张简洁写实的保温杯电商背景，暖白色石台、柔和侧光、右上留出标题空间。”
- “编辑这张图片，把背景换为现代厨房，保留商品主体、包装文字和商标。”本地 Agent 调用 edit_image 时传图片的 Mac 绝对路径，最多3张。
- “把这个透明PNG商品原图放到生成的背景中，标题写‘冬日好物’。”通过 generate_image 的 foreground_path 与 title 参数完成。

工具先返回任务ID，再查询进度。get_image_task 完成时返回 MCP 图片内容，并把 PNG 保存到 ~/Pictures/Spark Agent。不要反复提交同一任务。首次加载和切换可需数分钟；每次查询最多20秒只是单次工具等待，不是任务总超时，不要在80秒后自动取消重建。若服务503，停止重复提交并联系服务维护者。默认fast编辑使用BF16 4步加速；standard编辑20步、high编辑40步为原版模式。1024快速编辑连续请求实测约36秒，冷加载约6分钟；模型切换与排队会增加等待。工具返回任务ID后继续查询进度，不要等待某一次MCP调用持续数分钟。

生图/编辑模型：Z-Image-Turbo BF16 / Qwen-Image-Edit-2511 BF16，按任务轮换。真实商品优先透明前景合成；生成式编辑不能保证商标、包装和外形逐像素一致。准确标题/价格用 title 排版或业务设计工具。

本包不自动修改 Mac 上未知位置的 Harness 配置。最终验收：从实际 Harness 上传商品照片，完成一次生图、一次图片编辑、一次取消，并在聊天中显示返回图片；保留错误信息但不要记录密钥。
