# REPORT-T10 — R26 ⑯ BGE 冷启动退化诊断（AUTO20 队列 #10）

- 执行者：T10 子 agent（诊断域独占；业务代码零改动）
- 日期：2026-09-22
- 探针：`edu-agent/scripts/_r26_probe_bge_cold.py`（下划线前缀=临时，git add -f 入库，只读诊断）
- 结论：**C（探针/门限口径问题）为主 + A′（环境负载方差）为辅，无硬件退化证据（B 排除）**

---

## 1. 结论摘要（三选一）

**结论 C：探针口径问题** —— BGE-M3 进程级冷加载的**物理基线**就是 15–30s（import torch + FlagEmbedding ≈ 12–15s 是最大头），30s 门限把「正常冷启动」当异常红。所谓「退化」的 40s+ 样本（36/182，19%）是**主机负载方差**（check-demo 自身 5 轮 uvicorn 启停堆叠 + GPU 常驻 4.5GB 显存占用 + 78–81C 高温低频）导致的长尾，而非崩溃后的持久性退化：

- 主机自 2026-09-19 08:05 重启后**未再崩溃**（Kernel-Power 41 集中在 9/16–9/19），而「绿转红」发生在 9/20 起——时间线与崩溃事件**不吻合**；
- 今日（9/22）6 次实测冷加载 29.0–66.7s 与 9/18–9/21 的分布（p50≈21.7s / p90≈50.4s / max 90.5s）**同一分布**，无逐日漂移趋势；
- 分段计时实证：磁盘读 1.25–1.54 GB/s（SSD 健康）、CUDA init 0.22–0.38s、model_load 4.7–7.4s——**全部正常**；瓶颈在 import 阶段（torch 3.2–3.5s + FlagEmbedding 8.9–12.0s），这是 CPU 单线程 DLL/模块装载，与 GPU/崩溃无关；
- device=cpu 对照 24.2s ≈ cuda 21.0s——CUDA 路径无额外惩罚，**排除 GPU 驱动/显存碎片退化**（A 的"驱动退化"子项排除）。

---

## 2. 冷启动实测分段计时（3 轮 cuda + 1 轮 cpu + 2 轮纯读盘）

探针分段：`import_torch` / `import_flagembedding` / `cuda_init` / `model_load`（BGEM3FlagModel，与业务 embedder.py `_get_bge_model` 同参：use_fp16、device）/ `first_embed` / `raw_file_read_hot`。每轮均为新进程（进程级冷）。

### cuda 三轮（device=cuda, use_fp16=True, RTX 4060 Laptop 8GB）

| 段 | 轮1 | 轮2 | 轮3 | 说明 |
|---|---|---|---|---|
| import_torch | 3.34s | 3.24s | 3.55s | torch 2.11.0+cu128 DLL 装载 |
| import_flagembedding | 8.89s | 8.96s | 11.32s | **最大头**（含 transformers 等） |
| cuda_init | 0.27s | 0.27s | 0.38s | CUDA context 创建，**正常** |
| model_load | 7.43s | 4.71s | 6.35s | 2.27GB 权重→显存 |
| first_embed | 1.11s | 0.92s | 1.58s | 首条 encode（dim=1024 验证） |
| raw_file_read_hot | 1.48s | 1.54s | 2.29s | 页缓存热读 |
| **合计（import→embed）** | **21.03s** | **18.11s** | **23.17s** | |

### 对照组

| 实验 | 合计 | 关键差异 |
|---|---|---|
| device=cpu | 24.23s | model_load 5.38s / first_embed 3.67s——cuda 与 cpu 全程差 <3s，CUDA 因素排除 |
| 纯读盘 ×2（不 import torch） | 1.47s / 1.25s（1.54 / 1.81 GB/s） | SSD 顺序读健康，**磁盘不是瓶颈** |
| 隔离 torch+CUDA init | 3.29s + 0.22s | 与全探针一致，无干扰 |

**定位**：21s 基线中 ~12s 是 Python import（纯 CPU），~5–7s 是权重装载，CUDA init 可忽略。「15-25s 正常档」与此完全吻合；40s+ 需要额外 20s+，只能来自并发资源争抢（见 §4）。

---

## 3. GPU 态取证（开工时快照）

- **nvidia-smi**：RTX 4060 Laptop 8GB，驱动 610.47 / CUDA 13.3；**显存 4517/8188 MiB 已占用（55%）**，GPU 78–81C、P8 低功耗档 6W；进程列表 26 个 C+G 图形进程（Weixin×2、Chrome×2、Edge、Doubao、Docker Desktop、wallpaper64 等）+ 1 个 C 计算（PID 12320 = 常驻 uvicorn 9988，watchdog 守护的合法服务进程，**未触碰**）。
- **无僵尸 python 显存泄漏**：全部 python 进程逐一核对命令行——2×hermes gateway、2×watchdog_8000、2×uvicorn 9988（同一服务主备对）、backlot/http.server/server.py 各 1——**均有明确归属，无可杀僵尸**（铁律 3 允许杀的"明显僵尸探针"不存在，故未执行任何 kill）。
- **节流原因 active=0x1（GPU Idle）**，无过热/无电源节流标志；时钟 max 3105MHz 正常。
- **磁盘**：E: = Phison Pcie4.0 E21-512G SSD，HealthStatus=Healthy；C: = Micron 1100 2TB Healthy。E: 余 618GB（模型目录完整，model.safetensors 2.27GB 与 README 一致）。
- **RAM**：32GB 总 / 6.3GB 空闲；页面文件 C: 16MB 已满用 + **D: 32GB 用 5.2GB**——9/18 曾 22 次触发 os error 1455（页面文件太小，BGE mmap 失败降级 DashScope），集中在 22:35–22:37；此后未复发，但 C: 页面文件 16MB 配置明显过小。
- **崩溃史**：Kernel-Power 41（意外断电/强杀）在 9/16、9/17、9/18、9/19 08:05 各一次，**9/19 后无**；VMware VMX 0xc0000005 与之同窗。

---

## 4. 历史横向对账（logs/app.log，2026-09-18 → 09-22，552 次真实加载）

`grep "bge_m3 完成 Nms — BGE-M3 已加载"`（排除 0ms skipped 项）：

| 口径 | 数值 |
|---|---|
| 全体 552 次含热载（p50=3ms=进程内热） | p75=15.8s / p90=27.7s / max=90.5s |
| 仅冷载 >5s（182 次） | **min 14.6s / p50 21.7s / p90 50.4s / max 90.5s / avg 27.3s**；>40s 共 36 次（19%） |
| 按日均值 | 9/18: 30.1s → 9/19: 27.0s → 9/20: 22.1s → 9/21: 28.6s → 9/22: 43.4s（仅 6 样本） |
| 今日 6 次 | 31.5 / 55.3 / 35.1 / 42.8 / 66.7 / 29.0s（01:51–05:13 深夜窗口，恰逢多 agent 并行+check-demo 反复启停） |

**判读**：p50 21.7s 与「此前正常 15-25s」吻合；40s+ 长尾自 9/18 起就存在（61721ms @9/18、60196ms @9/19、62889ms @9/20、90500ms @9/21），**不是 9/20 后新出现的状态**。9/22 均值偏高但样本仅 6，且当夜 T7/T8/T11 等多 agent 并行作业同机运行——长尾与**并发负载**强相关，与「崩溃后持久退化」叙事不符（9/19 后零崩溃）。

长尾的机理解释（证据链闭环）：check-demo ⑯ lifecycle 探针自身连续 5 轮拉起 uvicorn（每轮各自加载 BGE 2.27GB 进显存+页缓存/页面文件压力），此时**同机常驻 9988 已占 4.5GB 显存、GPU 78–81C 掉频**，新进程的 model_load 与 CUDA context 竞争变慢——这正是 9/20 勘误注释（check-demo.mjs:587「体检单自己 5 轮启停后 GPU/页缓存清冷」）已观察到的现象，探针 300s 超时后仍偶发红是因为**lifecycle 5 轮叠加 + 后台预热链（bge_m3 29s + reranker_local 11.9s）串行近 45s**（实测 /health/warmup：elapsed_ms=44601，status=degraded 仅因 reranker_sidecar 8601 未启动——与本任务无关的已知环境项）。

---

## 5. 修复建议（均为建议，未改任何代码）

### C 类（主结论）：探针/门限口径

1. **⑯ 探针口径拆分**：lifecycle 探针 `_lifecycle_real_verify.py` 的 30s 就绪门只应约束「进程可服务」——uvicorn /health 200 本身 3–8s 足够；BGE 预热是 lifespan 后台任务不阻塞就绪。建议门限语义改为「start < 30s 内 /health 200」+「warmup 后台任务 < 300s 达 ready/degraded」两段式，且 warmup 时限**仅告警不红**（现状 degraded 本就不阻断服务，reranker_sidecar failed 即为例证）。
2. **check-demo ⑪ veclock_health_probe 的 300s 预算保留**但输出耗时注脚（当前 PASS/FAIL 行无耗时，退化趋势不可见）；建议探针末行附 `elapsed=Ns`，连续 3 次超 60s 才升红。
3. **巡检口径**：编排者档案「曾 21563ms」与日志 p50 21.7s 一致——建议以 **p50≤25s / p90≤55s / 硬红线 120s** 为 BGE 冷加载健康带（按 §4 分布），替代单次 30s 门限。

### A′ 类（辅）：环境长尾缓解（安全可逆，未执行——涉及常驻服务/系统配置，超诊断域）

4. **页面文件扩容**：C: pagefile 16MB（≈已满）+ D: 32GB。9/18 的 22 次 os error 1455 即页面文件耗尽。建议 C: 设系统管理大小或 ≥16GB 固定（1/2 RAM），一次配置永久消除 1455 类 mmap 失败。
5. **GPU 显存预算**：常驻 26 个 C+G 进程占 4.5GB/8GB。若需稳定冷加载 p90，考虑桌面会话减载（wallpaper64/Doubao/Weixin 小程序等 C+G 大户）或 BGE 预热改 `low_cpu_mem_usage`（需业务侧改动，此处仅登记方向）。
6. **sidecar 缺位**：reranker_sidecar(8601) 未启动导致每轮 fallback `reranker_local` 额外 +6.5~11.9s 预热（warmup.py:171-175 设计如此）——启动 8601 sidecar 可直接砍掉预热链 1/4 时长。

### 明确排除

- **B 硬件退化**：SSD 双盘 Healthy、顺序读 1.5+ GB/s、GPU 无节流/无 ECC 错误、cuda_init 0.2s、cpu/cuda 加载等价——无任何硬件层证据。
- **驱动退化**：610.47/CUDA 13.3 工作正常；torch cu128 经驱动转发兼容层正常出向量（dim=1024）。
- **EMBED_BACKEND 漂移**：.env 实测 `EMBED_BACKEND=cuda`、`EMBED_DEVICE=cuda`、`BGE_M3_PATH=E:/stu/ai-models/bge-m3` 未漂移（9/22 03:17 曾有一次 cloud skipped 记录，为当时测试注入，已复位）。

---

## 6. 批判自检

1. **样本量批判**：9/22 仅 6 次冷载，日均值 43.4s 的「偏高」不具统计显著性（9/21 单日 max 90.5s 更高）——结论不依赖该均值，依赖 5 日分布重叠 + 崩溃时间线不吻合。
2. **探针自身偏差**：分段探针跑在多 agent 并行主机上，三轮波动（18.1–23.2s）即环境噪声的直接证据；未做「独占静默主机」复测——但 §4 的 552 样本历史分布已覆盖该盲区（p50 稳定）。
3. **温度 78–81C 长期高温**：笔记本 RTX 4060 在 P8 档 78C 偏高（桌面 wallpaper/多应用），未做烤机验证——不改变本结论（温度影响的是稳态频率而非加载），登记为运维关注项。
4. **未 kill 任何进程**：符合铁律 3——核对后确认无可杀僵尸；nvidia-smi 前后无变化需求。
5. **报告口径**：本报告不改任何 `.mjs`/业务代码，门限修正建议需编排者派单至 check-demo 维护域落地。

## 7. 证据文件清单

- 探针：`edu-agent/scripts/_r26_probe_bge_cold.py`（mode=cuda/cpu/read 三态，可复跑）
- 日志口径：`edu-agent/logs/app.log`（grep `bge_m3 完成 .*ms — BGE-M3 已加载`）、`/health/warmup` 实时快照（elapsed_ms=44601, bge_m3=29002ms, degraded=sidecar）
- GPU/磁盘：nvidia-smi 610.47 快照、Get-PhysicalDisk（双 SSD Healthy）、Get-WinEvent Kernel-Power 41（9/16–9/19）
