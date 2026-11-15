# T03 真实无模型链路验证（2026-11-15）

用户明确选择保持两台 LTX 运行、只做不加载模型的真实测试。最高图片/桌面验收范围并未因此通过。运行源代码固定点：`e0e76cf5e8c1179cbdb23b3195d52bb26bf9330e`（已合并PR #18）；runtime_sha256逐文件确认产品代码与该提交一致。

时间：2026-11-15T10:53:13.254567+08:00 至 2026-11-15T10:53:15.977210+08:00（Asia/Shanghai）。本轮56个检查点通过，清理/凭证边界检查也通过。报告 `report.json`、实际CPU worker响应 `task-A.json` / `task-B.json`、合成PDF输入 `fixture.pdf`、原始余量观测 `memory-observed.json`。`reference.png` 是人为生成的64×64参考夹具，绝非模型输出。

## 已验证

- 临时独立staging网关（真实uvicorn进程，127.0.0.1:18018）、真实Caddy TLS（127.0.0.1:18444）、原项目CA；验证正确CA成功、系统未信任CA失败。没有MockTransport/ASGITransport/TestClient。
- 临时注册表通过真实CLI发放A/B Key；0600输出，401缺少/未知凭证、稳定owner、轮换后继续取原任务/文件、撤销旧Key401、伪造owner422。
- A/B实际multipart上传同一份合成PDF；真实SQLite/文件库/CPU PDF worker调用poppler完成任务、返回已知文字，文件下载字节一致。任务完成来自真实worker，未手工置completed。
- 跨人文件下载/删除/引用、任务查询/取消与未知ID统一404。同owner同键/同内容重传新素材ID复用原任务、改输入409，不同owner同键独立。
- 切换同一个临时网关至无worker模式，通过真实HTTPS接纳4个自然queued的PDF任务；验证幂等重放不多占位置、第五个429/Retry-After10、外人取消404且队列仍满、本人取消释放一个位置；最后通过接口取消测试排队任务。未造假任务状态。
- 真实MCP stdio子进程发现4个工具；生成/编辑在实际图片端口离线时返回HTTP503；跨人get/cancel通过MCP返回HTTP404。没有生成成功或返回图片的主张。
- 临时进程全部停止、临时Key全部撤销，原始Key文件与MCP私有配置删除；服务日志无原始Key。原项目CA公钥哈希不变，正式gateway/https/image/guard状态未改变，LTX worker/guard保持active。Spark01也复核其LTX worker/guard为active；没有发出任何LTX或模型服务的停止/启动命令。

## 未验证 / N/A

- 物理图片生成、编辑与真实生成结果下载：按用户约束未运行；不能以503作为生成成功。
- Windows/macOS实际桌面Harness：没有在线可控桌面设备，本轮MCP运行于Spark02 Linux；不替代双端验收。
- 正式18443入口/生产数据迁移与发布恢复：未运行，HTTPS验证使用隔离loopback端口与相同项目CA。
- 20GiB保护器/模型内存包络与性能：未标定。1Hz余量只是本轮环境观察，不是内存安全或延迟结论。
- 类型/lint/构建/完整门禁：未运行；无产品代码变动，本轮仅真实检查与证据。

## 初次探针与复现

首轮 t03-live-20261115T025029Z 因脚本构造空Bearer被httpx拒绝，尚未到达服务端，状态保留failed，不算产品缺陷。改为发送无鉴权头后，t03-live-20261115T025108Z完成55项；最终补运行时哈希及CPU响应保存后，本轮56项通过。没有产品修复，也未重写旧报告。

复现：在本项目受支持环境执行 `.venv/bin/python evidence/t03-live-20261115T025313Z/run-live-check.py`。脚本只使用本项目已配置的uvicorn/Caddy/MCP/CLI与真实协议，为每次运行创建唯一私有数据和证据目录；端口被占用或图片后端已在线时预检拒绝，不启动/停止任何模型服务。需要现有项目CA与本地私有CA存储；不复制私钥到公开证据。

#4 保持OPEN，真实图片/双端验收仍由后续门禁承接；不能宣称T03完整验收或部署完成。
