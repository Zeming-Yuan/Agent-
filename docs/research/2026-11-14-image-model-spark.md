# DGX Spark 本地生图模型候选（2026-11-14）

范围：核对 Qwen Image、Z-Image，并补充 FLUX 3 Image Klein 的官方发布与许可；比较中文文字与通用图像能力、DGX Spark（GB10/SM121、ARM64、128 GB UMA）部署证据、权重/运行内存和许可。没有下载权重或触碰服务。

## 用户用途确认后的方案

用户确认用途为“日常配图、电商图，速度质量兼顾”。推荐首期采用 **Spark01 现有 200000-token 主模型 + Spark02 Z-Image-Turbo BF16**。Whisper 与 Omni 退出常驻，原权重保留用于回退。本节为待实施方案，不是完成记录。

- 日常配图、概念海报：主模型整理提示词，Z-Image-Turbo 生成，固定排版工具叠加需准确呈现的标题、价格与品牌标识。
- 真实商品主图/场景图：上传商品照片后，保留原商品前景，生成背景并合成；遮罩与边缘需检查。Z-Turbo 不负责重画商品，避免把商标、包装、规格画错。
- 确需改变商品姿态或复杂局部编辑时，再评估 Qwen-Image-Edit-2511 按需加载，与 Z-Turbo 互斥驻留；商品一致性和本机内存、速度必须用业务样本验收。
- 初始配置：约 1MP（默认 1024×1024）、batch=1、生图并发 1、有界队列；沿用官方 Turbo 采样设置。以 35GiB 作为初始生图内存规划额度、至少 20GiB 可用内存作为保护线；35GiB 不是已测峰值。
- 2026-11-14 本机复核：Spark02 MemAvailable=75918979072 bytes，约 70.71GiB；Whisper/Omni 的 NVIDIA 进程分配分别为 2056/17807MiB，合计约 19.40GiB。共享内存下这些分配已经包含在系统内存中；停用后实际可用内存需重新测量，不能直接保证将增加相同数值。
- 网关拟增加 `/v1/images/generations` 及任务状态/取消接口，由桌面 Agent 的生图工具调用并展示图片附件。聊天仍使用 `spark-main`；生图接口不能仅靠在 Chat Completions 模型目录中新增名称实现。
- 停用音频服务时同步修改健康检查、模型目录和媒体能力；原视频流水线依赖 Whisper，需明确改为仅分析画面或返回不支持音频，不能留下失效调用。
- 验收至少覆盖 20 个日常/电商样本、冷/热生成时间、P50/P95、峰值内存、同时聊天、排队/取消和 Mac 桌面端图片展示。没有本机数据前不承诺每张耗时。

补充候选：[FLUX 3 Image Klein 官方模型卡](https://huggingface.co/black-forest-labs/flux-3-image-klein) 提供 5.6B 视觉模型、16 步蒸馏版及参考图编辑能力，但采用 [FLUX Kommunity License](https://huggingface.co/black-forest-labs/flux-3-image-klein/blob/main/LICENSE.md)，商业输出例外附带公司及关联方年化收入低于 500 万美元等条件。因此本方案不把它当作无需确认许可条件的公司默认模型。其官方速度/内存数据不等于本机实测。

## 结论

如果日常任务是快速制作商业配图、电商图，优先试 **Tongyi-MAI/Z-Image-Turbo**：其官方权重采用 Apache-2.0，官方模型页称 6B、8 次采样，擅长中英文字与写实图；NVIDIA 的 DGX Spark ComfyUI playbook 已给出该模型的 ARM64/Linux BF16 部署流程和 20 GB 下载清单。NVIDIA 对此工作流给出的约 24 GB GPU-memory 门槛，按 12 GB DiT 加 8 GB 文本编码器估算，且明确尚未计入 activations；Spark02 当前可用内存约 70.71GiB；停用音频模型后的实际余量与生图峰值还需复测。NVIDIA 所说“30 秒内”是 playbook 的预期，不是本机实测，也不应当与 H800 的亚秒数字混为一谈。Z-Turbo 是纯文生图；不能当作保留真实商品外观、对上传商品图做精确改图的方案。

**Qwen-Image-2.1-Turbo** 是更强的综合候选：官方本地 BF16 权重、8 步采样、图像编辑与最多 10 张参考图能力均可确认；但 2.1 与 Turbo 权重都是 Qwen Research License，条款明确仅限非商业研究/评估，商业用途需单独申请许可。未取得该许可前，不建议作为商业生产替代。2.1 比 1.0/2512 架构更轻（视觉 DiT 7B），并有 Turbo 8-step；官方 Hugging Face 使用 BF16。对 Spark 的官方 NVIDIA quickstart 尚未找到。

Qwen-Image-3.0 的官方文章于 2026-07-21 发布，介绍 4.5k token、多语言与复杂排版能力，但本次未找到对应 Qwen 官方 Hugging Face/GitHub 可下载仓库或权重；应视为“云端产品可用，官方本地权重未核实”，不要按本地模型规划。

## 对比

| 候选 | 可下载 ID / 精度 | 任务与特点 | 权重和显存 | Spark 证据与速度 | 许可 / 适用性 |
|---|---|---|---|---|---|
| Z-Image-Turbo | `Tongyi-MAI/Z-Image-Turbo`；官方 Diffusers BF16；NVIDIA playbook 使用 `Comfy-Org/z_image_turbo` BF16 split | 6B；8 NFE；写实、中英文字、prompt adherence；Turbo 以速度换多样性；仅 T2I | NVIDIA 估计下载约 20 GB：DiT 12 GB、Qwen3 4B text encoder 8 GB、VAE 335 MB；GPU memory 约 24 GB 是运行时预算，另有激活开销 | NVIDIA 官方 DGX Spark playbook 直接提供 Linux/ComfyUI/CUDA 13.0/BF16 路径；其文档预期单张在 30 秒内完成。没有找到可复现的 Spark 专项 benchmark；模型卡的 H800 亚秒延迟不可外推到 GB10 | Apache-2.0。当前推荐商业本地起点；若需要编辑/多图参考，工作流要另配编辑模型 |
| Qwen-Image-2.1-Turbo | `Qwen/Qwen-Image-2.1-Turbo`；官方 BF16 Diffusers checkpoint，8 步；Comfy-Org 另提供 ComfyUI 文件 | 文本生成 + 图像编辑；中文排版/海报、透明 RGBA、最多 10 张参考图；比普通 2.1 快 | 视觉 DiT 7B BF16 约 14 GB 参数权重。官方架构另有 Qwen3-VL 8B 文本编码器；BF16 参数量约 16 GB，加 VAE 后整个 pipeline 权重粗估约 31 GB，尚未含 runtime/activation。官方未给 Spark 峰值或生成耗时；该估算不能当作峰值显存实测 | 有官方 Diffusers/CUDA/BF16 入口，但未找到 NVIDIA Spark 专项 recipe 或在 GB10/SM121 的第一方基准。8 步是模型设置，不等于本机延迟结论 | Qwen Research License：只允许非商业研究/评估；商业用途须向 Qwen 单独申请。商用前阻塞项 |
| Qwen-Image-2.1（非 Turbo） | `Qwen/Qwen-Image-2.1`；官方 BF16 | 同 7B visual DiT；40 步示例；适合编辑、透明图与多参考 | 参数规模及 BF16 pipeline 估算与 Turbo 相同；完整峰值未见官方实测 | 官方 Diffusers 可运行但更高步骤数；无 Spark 第一方 benchmark | 同 Qwen Research License；Turbo 在更少步数下更适合快速生成 |
| Qwen-Image-Edit-2511（按需编辑） | `Qwen/Qwen-Image-Edit-2511`；官方 BF16 Diffusers | 专做图像编辑，支持多输入图，官方强调人物一致性/工业设计等；不能替代日常 T2I 主模型 | 官方列 20B BF16；DiT 参数本身理论约 40 GB，完整 pipeline 还需编码器/VAE，峰值更大；仅按需加载/卸载，避免常驻占用共享 UMA | 官方有 Diffusers 本地 BF16 推理样例；未找到 DGX Spark 第一方部署/性能测试 | Apache-2.0。可作为“需要保留上传商品外观时”的独立编辑候选，但启动成本、延迟与峰值需实测 |
| Qwen-Image-2512 | `Qwen/Qwen-Image-2512`；官方可下载权重，BF16 推理示例 | 20B 系列文本生成，官方强调更自然的人物、纹理和文字布局；50 步示例 | 仅 DiT BF16 理论约 40 GB；连同文本编码器、VAE 和 activations 峰值会更高。按 Spark02 约 70 GiB 可用预算可以研究，但不能据参数量断言峰值足够 | 官方没有 Spark 的特定 recipe/延迟数据；比 Z Turbo/Qwen 2.1 Turbo 默认采样步数多 | Apache-2.0；可商用。它不是云端专属：Qwen 官方 GitHub 与 HF 均有公开权重和 BF16 本地推理代码 |
| Qwen-Image-3.0 | Qwen 官方 blog / Qwen Chat 产品名；未查到 Qwen 官方可下载权重 ID | 官方宣称最多 4.5k-token 输入、12 种语言、复杂布局与细字渲染 | 无本地官方权重，不估算 | 无 Spark 部署依据 | 按云端产品处理；本次未发现官方可用于自托管的权重及其许可 |

内存说明：权重文件大小、加载后的参数占用、运行峰值是三件事。BF16 参数粗算按每参数 2 bytes；再加文本编码器/VAE、图像 latent、attention workspace、CUDA context 和 ComfyUI/PyTorch reserve。共享 UMA 下还要给 OS、现有模型及服务留余量。Z Turbo 的 ~24 GB 是 NVIDIA 对模型工作流给出的最低近似门槛（明确尚未计激活），不是已核实的峰值；Qwen 的 ~31 GB 是架构参数推算的完整 BF16 权重规模，峰值未知。所有候选在 128 GB 总内存上“放得下”不等于速度相同。

## Qwen 版本与可下载性核对

- Qwen 官方 Hugging Face 卡明确给出 `Qwen/Qwen-Image-2.1` 为 7B 参数 BF16，并直接提供 `QwenImage21Pipeline`；许可证链接指向 2026-09-20 的 Qwen Research License。
- `Qwen/Qwen-Image-2.1-Turbo` 官方卡显示同 7B 架构、8 步、支持编辑，并提供本地 BF16 Diffusers 代码；不是云端 only。
- Qwen 官方 GitHub 的旧主仓库列出 `Qwen/Qwen-Image-2512` 权重、BF16 推理示例；其 HF 页面标注 Apache-2.0，因此 2512 也不是云端 only。
- Qwen 官方 3.0 博文介绍产品能力；截至本研究日期，未检索到 Qwen 官方组织下的 3.0 权重页/源代码仓库。该项是基于官方公开仓库检索的否定性发现，不能证明内部或未索引渠道绝对不存在。
- Qwen-Image-Edit-2511 官方 HF 卡为 20B BF16、Apache-2.0，提供多图编辑代码；它是可商用本地编辑备选，不等于速度/质量已在 Spark 验证。

## 官方来源

- [NVIDIA DGX Spark ComfyUI playbook](https://github.com/NVIDIA/dgx-spark-playbooks/blob/main/nvidia/playbook-comfyui/README.md)：Spark/64–128 GB UMA 支持矩阵、Z-Image-Turbo quickstart、CUDA 13.0、三个 BF16 文件下载项、20 GB 下载/24 GB GPU memory 估算、30 秒预期及 UMA 提示。
- [NVIDIA DGX Spark hardware guide](https://docs.nvidia.com/dgx/dgx-spark/hardware.html)：Grace Blackwell、20-core Arm、128 GB unified memory。
- [Tongyi-MAI Z-Image 官方 Hugging Face 卡/仓库说明](https://huggingface.co/Tongyi-MAI/Z-Image-Turbo)：6B、8 NFE、写实与中英文字；模型卡给出的 H800 亚秒数字仅属于其所述 H800 测试类别。
- [Z-Image-Turbo Apache-2.0 权重页](https://huggingface.co/Tongyi-MAI/Z-Image-Turbo)。
- [Qwen-Image-2.1 官方 Hugging Face 卡](https://huggingface.co/Qwen/Qwen-Image-2.1)：7B、BF16、T2I/编辑、RGBA、多参考、官方 pipeline；[Research License 原文](https://huggingface.co/Qwen/Qwen-Image-2.1/raw/main/LICENSE)。
- [Qwen-Image-2.1-Turbo 官方 Hugging Face 卡](https://huggingface.co/Qwen/Qwen-Image-2.1-Turbo)：8 步、同一 7B visual architecture、BF16 Diffusers 本地示例；[相同 Research License 原文](https://huggingface.co/Qwen/Qwen-Image-2.1-Turbo/raw/main/LICENSE)。
- [Qwen 官方 Qwen-Image-2.1 GitHub](https://github.com/QwenLM/Qwen-Image-2.1)：2.1 发布信息、架构、权重与多框架适配；发布页显示权重从 HF/ModelScope 获取。
- [Qwen-Image-2512 官方 Hugging Face 卡](https://huggingface.co/Qwen/Qwen-Image-2512)：公开权重、Apache-2.0、本地 BF16 代码、50 步示例；[Qwen Image GitHub](https://github.com/QwenLM/Qwen-Image) 亦列出其权重。
- [Qwen-Image-Edit-2511 官方 Hugging Face 卡](https://huggingface.co/Qwen/Qwen-Image-Edit-2511)：20B BF16、多图编辑、Apache-2.0 与本地 Diffusers 样例。
- [Qwen-Image-3.0 官方文章](https://qwen.ai/blog?id=qwen-image-3.0)：发布日期 2026-07-21 与产品能力；未包含可下载权重 ID。
- [Qwen-Image-2.1 官方文章](https://qwen.ai/blog?id=qwen-image-2.1)：说明 2.1 于 2026-09-20 开源。

## 尚未确认

1. NVIDIA 的 Z-Turbo “30 秒内”是说明文档的预期，未找到公开的同配置 Spark02 实测；需在本机实际跑目标分辨率/采样参数后才可做吞吐承诺。
2. Qwen 2.1-Turbo 在 GB10/SM121 上的 BF16峰值显存、首图时间、后续图时间及官方支持矩阵均未确认；其 8 steps 不能直接推出比 Z Turbo 快。
3. 未发现 NVIDIA 官方针对 Z Turbo 或 Qwen Image 的 NVFP4 recipe。Hugging Face 上存在第三方 NVFP4/INT8 量化变体，但本次未核验其校准质量、Spark kernel 兼容性或许可继承，故不列为可验证候选。

## 已部署后的实测补充（2026-11-14）

用户追加编辑并批准部署后，已落地Z-Image-Turbo BF16 + Qwen-Image-Edit-2511 BF16互斥轮换，并将 [Lightx2v官方4步适配器](https://huggingface.co/lightx2v/Qwen-Image-Edit-2511-Lightning) 作为fast选项；全部固定revision/SHA。普通编辑20/40步不使用适配器。实际快速换色和双参考背景编辑已查看，热双图36.407秒，冷单图367.999秒；原版20步一次203.656秒。编辑批次可用内存最低28.504GiB，20GiB保护器启用。此结果证明本机功能可用，不是Grok同素材盲测或真实SKU质量合格率。实测样张及最终运行配置证据在evidence/image-deploy-20261114；最终生产VAE禁用此NGC运行时有条纹的cuDNN路径，CUDA/SDPA保留。
