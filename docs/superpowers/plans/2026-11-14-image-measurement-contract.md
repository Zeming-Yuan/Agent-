# 图片内存与延迟：测量基线及比较契约

日期：2026-11-14。适用 T08/T09/T10/T11/T14；这是一份测量方案和脚本审计，不是本次性能或内存标定结论。

## 本轮实际做了什么

- 已读取 scripts/benchmark_images.py、scripts/verify_image_edit.py、scripts/verify_standard_edit.py、部署锁文件以及既有结果摘要。
- 只运行了本工作区的 uptime/nproc：20 个逻辑核，load average 2.11/1.97/2.10。这不是图片执行节点环境证明，不能据此声称 GPU 空闲。
- 本轮没有提交生产图片任务，没有运行新的 baseline，也没有新的 before/after 原始结果。baseline_status=not_run；因此不能报告更快、更省内存或已通过标定。
- 历史原始记录位置：evidence/image-deploy-20261114/benchmark-generation.json、edit-verification.json、standard-edit-verification.json、mcp-stdio-live.json。它们来自不同测试口径和配置时间点，仅作历史背景，不作为当前修改基线；公开只同步路径与审计结论，不上传私有素材/凭证。

## 已发现的具体测量问题

1. benchmark_images 的 seconds 在读取任务 completed 后立刻生成，之后才 GET 图片/保存：不包含下载、PNG 校验和磁盘保存，不能叫完整用户端到端延迟。
2. 请求键固定为 image-bench-final-20261114-序号，重复运行会幂等命中原任务；没有后端唯一执行计数就不能证明新工作发生在计时区间。
3. 采样读取执行脚本机器的 /proc/meminfo，但请求发送到配置的服务地址；未检查采样 host_id 与实际执行节点是否相同。
4. 只有一条整个批次的 minimum，没有完整时间序列、容器峰值、模型驻留或释放证明，无法定位切换峰值。
5. HTTP raise_for_status 会提前退出，拒绝/连接异常可能没有计入最终 total；成功样本统计不能代表全部尝试。
6. 下载只检查 HTTP 成功，没有解码验证图片、尺寸与最终内容；重复结果和空/损坏图片可能被算成功。
7. 历史生成基准混合冷/热状态；没有调优一致的 A/B、交替复测与限制因素剖析。nearest-rank p95 算法本身可保留，但小样本 p95 只描述这批样本，不外推稳定 SLA。
8. 模块导入即 asyncio.run(main())，测试导入统计函数可能启动真实工作；T08 第一条失败测试先阻止这个副作用。

## 修改前的测量安排

1. **写出要验证的句子**：默认目标为“在指定运行时和输入包络内，连续切换保持 20GiB 余量且无保护停服”。如比较设置，另写明单位、具体负载及预期端到端指标；未完成前不写性能结论。
2. **审核测量入口**：先完成 import 安全和测试隔离；冻结当前被比较侧的代码/配置哈希，按 T08 记录四个时间点及实际后端执行。
3. **登记环境**：在真正图片节点运行 uptime、nproc，记录系统/驱动/容器/模型/工作流/依赖版本、75GiB 容器边界、20GiB 保护和其他进程；并记录负载生成器所在主机/CPU。忙碌时不能擅停其他服务，需登记噪声并交替比较。
4. **验证工作与输出**：每次新 run_id/独立请求键；任务、规范后端 prompt_id 和原始执行事件匹配；验证图片解码/尺寸/内容，计数失败/拒绝/超时/重试/无执行样本。先验证再纳入有效样本。
5. **找限制因素**：在不计入正式结果的 profiling 运行检查加载 I/O、文本/视觉编码、采样、VAE、保存和负载生成器；分别记录冷加载/热推理/排队占比。无法确定限制因素时不选性能赢家。
6. **建立可比较 baseline**：先跑生产等价 flags、版本、缓存、并发与固定数据集；记录真实原始路径/run_id。若旧侧不安全或无法调优一致，不为比较关闭保护器，结论写 inconclusive，并仅给新侧绝对安全观测。
7. **冻结方案和负载**：默认并发1执行；混合用户公平场景保持同一到达序列且不超过既有全局4单。分别标记生成、fast、standard、high、尺寸、参考数、前景合成、冷/热及取消回切，不能把 fast 与 standard 当同条件性能方案。
8. **重复与交替**：父规格安全闭环至少每 profile 三轮 G→E→G；若用来比较/采用设置，每侧至少五轮 A/B 交替，固定种子/素材及缓存安排，报告 median/range。差异不超过运行波动则 no measurable difference。
9. **核对数量级与统计**：不把系统 used 与 GPU allocated 相加；不把旧驻留量再从增量预算扣两遍。对传输/磁盘带宽、CPU 核数、推理占比做上界校验；p95 采用 nearest-rank 并报告样本数、失败数和所有原始值。
10. **用户指标**：同时报告 submit→保存/显示的端到端时间，以及 queue/unload/load/generate/save/download 分段。Windows/macOS 各自显示证据单列；服务器计时不能代替实际 Harness。
11. **完成后核查结果**：逐项重新回答 benchmark-checklist 的七个问题（限制因素、调优一致、物理上界、错误与正确输出、可复现、端到端相关、工作真实发生）。写 faster/slower/no measurable difference/inconclusive；任一关键证据缺失写 inconclusive。把实际 baseline/run_id、原始结果位置、复测命令和有效配置追加到当前 ticket 计划，未运行保持 not_run。

## 可复制复测入口（由 T08/T11 实现，不在本轮执行）

私有配置包含 base_url、api_key_file、ca_file、telemetry_source、expected_host_id、运行时哈希和输入夹具；命令中仅传配置路径，不传凭证内容。

    python -m scripts.benchmark_images --scenario observe --config "$IMAGE_BENCH_CONFIG" --report-dir "$IMAGE_BENCH_REPORT"
    python -m scripts.benchmark_images --scenario model-switch --profiles fast,standard,high --cycles 3 --config "$IMAGE_BENCH_CONFIG" --report-dir "$IMAGE_BENCH_REPORT"

比较两个候选设置时使用各自冻结配置交替至少五轮，命令增加 --cycles 5；保留每一侧实际配置和运行顺序，不事后删除慢/失败样本。

## 结果产物

每个 run 目录包含 environment.json、attempts.jsonl、memory.jsonl、lifecycle.jsonl、profile-report.json、summary.json 及私有样张。目录由调用者提供、每轮唯一，不覆盖历史记录。若缺少任一原始证据，验证器失败而不是自动填 passed。公开 issue/ADR 只放脱敏结论与可访问的证据索引。

