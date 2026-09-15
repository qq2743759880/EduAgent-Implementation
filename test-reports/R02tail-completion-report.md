# R02-tail 完工报告：TTFT 检索段优化（start→retrieval）

- 执行：ZCode-R02-tail ｜ 完工：2026-09-15 ｜ 工作区 `E:\stu\project\stu\EduAgent实施手册`
- 任务：profile→优化 start→retrieval 段（编排者活体基线 3.38-3.6s，目标 ≤2s 或对齐旧路径同段水平）
- 交付 commit：`feat(r)/R02-tail-ttft`
- 复跑：`test-reports/r02tail-ttft-probe.py`（8010 临时实例）、`scripts/eval/r20b_dualrun_probe.py`（Jaccard 复跑）、`tests/test_contract_task_r02tail.py`（新增 5 单测）

---

## §0 结论速览

| 项 | 结果 |
|---|---|
| start→retrieval（热态，8010 实测） | **3.78~3.95s → 1.50~1.98s**（4 轮热态中位 **1.67s**，全部 ≤2s，**达标**） |
| profile 根因 | rerank 段占 81%：其中 **sidecar 连接失败固定烧 ~2.05s/请求**（端口关闭，纯浪费）+ 本地 CUDA 重排 ~0.9-1.0s/150 对；graph 通道串行叠加；memory 召回串行叠加 |
| 修复（4 项，检索语义零变化） | ① sidecar 连接失败熔断（冷却窗默认 60s，可关）② sidecar 连接相位短超时 1s ③ 图谱通道∥Milvus 通道并行 ④ memory 召回∥检索并行 + 本地 rerank 移线程池 |
| 红线 | hyde=True/top_k=12/5/0.40 禁动✅（未触及）；knowledge Jaccard 复跑✅（§4）；旧路径行为禁回归✅（同一函数共享修复，pytest+开关实测）；SSE 契约禁改✅（零帧格式改动）；STREAM_VIA_GRAPH 开关✅ |

---

## §1 profile 分解表（不许猜——8010 临时实例实测，2026-09-15）

### §1.1 分段计时日志落点（保留为常驻观测）

| 落点 | 内容 |
|---|---|
| `retriever.py::_milvus_hybrid_search_safe` | `[retrieval-profile] milvus total/embed(dense)/sparse/search/asm` |
| `retriever.py::_rerank_docs` | `[retrieval-profile] rerank sidecar attempt / local fallback / local (breaker-skip)` |
| `retriever.py::retrieve_three_channel` | `[retrieval-profile] pipeline total | hyde/milvus/graph/merge/rerank/cliff | raw/final` |
| `sixnode.py::fan_out` | `[sixnode.fanout-profile] total/retrieval/mem_par_await/summary/docs` |
| `graph_stream.py` | 完成日志追加 `node_arrivals_ms={...}`（各节点 update 到达时刻） |

### §1.2 优化前分解（2026-09-15 09:34，4 轮；热态=第 3~4 轮）

环境：BGE-M3 CUDA✅（启动预热 31.8s）· 进程内 reranker CUDA✅（预热）· **rerank sidecar 8601 关闭** · **Neo4j 7687 关闭**（与 9-14 基线差异：当日 Neo4j UP，见 §5 环境注记）

| 轮次 | start→retrieval | route→plan（前置管线） | fan_out | milvus | graph | rerank | memory |
|---|---|---|---|---|---|---|---|
| 1（冷） | 10.407s | ~945ms（skill registry 首扫 318 项） | 9440ms | 2485ms | 465ms | 5289ms（sidecar 2080 + 本地冷 3207） | 1200ms（串行） |
| 2 | 8.023s | ~420ms | 7597ms | 612ms | 509ms | 5860ms（sidecar 2092 + 本地 3766） | 615ms（串行） |
| 3（热） | **3.780s** | 63ms | 3713ms | 460ms（embed 259+search 195） | 213ms | **2959ms（sidecar 2051 失败 + 本地 898）** | 80ms（串行） |
| 4（热） | **3.952s** | 78ms | 3867ms | 487ms（embed 277+search 207） | 212ms | **3060ms（sidecar 2060 失败 + 本地 1007）** | 107ms（串行） |

**热态根因排序（不许猜的结论）**：
1. **rerank 2.96~3.06s = start→retrieval 的 ~81%**，其中 **sidecar 连接尝试固定 2051~2092ms**（4 轮一致；8601 端口关闭，连接耗尽路径烧满，纯浪费——结果注定失败），本地 CUDA 重排 150 对 898~1007ms。
2. Milvus 通道 460~487ms（稠密嵌入 ~260ms + 远端混合检索 ~200ms；HyDE=纯字符串改写 **0ms，非 LLM 调用**，候选方向①不成立）。
3. Neo4j 图谱通道 212~213ms 串行叠加（今日 Neo4j DOWN 熔断快速失败；9-14 基线 UP 时为真实查询，串行全额在关键路径）。
4. memory 召回（recall_topk：第二次嵌入+Milvus memory 查询）80~107ms 串行叠加。
5. 前置管线（route 规则路由/skill/compact/context_edit/plan + checkpoint 保存）合计仅 63~78ms——**非靶点**。
6. 参数对齐项（hyde/top_k）无计时影响：hyde=0ms。

## §2 修复内容（全部检索语义零变化，红线内）

| # | 修复 | 文件 | 语义保持论证 |
|---|---|---|---|
| 1 | **sidecar 连接失败熔断**：transport 级失败（ConnectError/超时）后开启冷却窗（`RERANK_SIDECAR_COOLDOWN_S` 默认 60s，0=关），窗内跳过 HTTP 尝试直接进程内直连；冷却到期自动重试（sidecar 优先级不丧失）。仅 transport 级失败触发——HTTP 非 200/分数长度不符不熔断（sidecar 进程活着，逐请求重试） | `retriever.py` | 窗内走的就是原「sidecar 失败→本地回退」的同一降级路径，分数来自同模型同批式（rerank_pairs AC1 单对分数逐位相等）；degrade 标签同为 `rerank_sidecar_unavailable`；新旧路径共享同一函数与同一熔断态，**不产生两路径分歧** |
| 2 | **sidecar 连接相位短超时** `RERANK_CONNECT_TIMEOUT`（默认 1s）：连接失败快速暴露，不再吃满连接耗尽（实测对已关闭端口固定 ~2.05s） | `retriever.py`+`config.py` | 只影响失败路径的耗时上限；成功路径 connect≤1s 本地进程恒满足 |
| 3 | **图谱通道∥Milvus 通道并行**：`_graph_expand` 与 Milvus to_thread 同时启动，两通道仅共同依赖 rewrite_query、产物独立（docs/graph_entities 分开装配）；关键路径 sum→max | `retriever.py` | 输入/输出/RRF/重排/断崖全部不变；降级原因仍按 milvus→graph 固定顺序汇总（单测断言）；Milvus 超时语义不变（超时后仍收口 graph，同原串行） |
| 4 | **memory 召回∥检索并行**（sixnode.fan_out）+ **本地 rerank 移入线程池**（`asyncio.to_thread`，不再阻塞事件循环 ~1s/请求） | `sixnode.py`/`retriever.py` | recall_topk 调用参数与产出逐字节同语义（成功→记忆摘要/失败→占位+warning，单测断言）；to_thread 同调用同分数，仅不再卡事件循环（并发健康度） |

未采纳候选（profile 数据否决/越红线）：HyDE 换 fast 模型/缓存——**HyDE 是纯字符串改写 0ms，无 LLM 调用可优化**；rerank 批大小/候选数（150）调整——改 batching 或截断输入会动分数→动排序→动 Jaccard，**红线禁入**；嵌入模型——BGE-M3 CUDA 已 warm（86~114ms），非瓶颈。

## §3 Before / After（同环境同仪器，8010 实测）

| 口径 | before（09:34） | after（09:44） | 判定 |
|---|---|---|---|
| start→retrieval 热态 | 3.780 / 3.952s（n=2） | **1.503 / 1.606 / 1.733 / 1.979s（n=4，中位 1.67s）** | **-57%；全部 ≤2s，达标**（编排者基线 3.38-3.6s 同段：亦显著低于） |
| start→retrieval 冷态（首请求） | 10.407 / 8.023s | 9.151s | 冷态因子=skill registry 首扫+首形状 CUDA kernel，非本批范围 |
| rerank 段 | 2959~3060ms | **993~1108ms**（sidecar 熔断窗内 0 尝试） | -66% |
| sidecar 连接失败损耗 | 2051~2092ms/请求 | 窗内 0ms；窗到期首请求 1046ms（1s 短超时封顶）后重新熔断 | 消除 |
| graph 段（Neo4j DOWN） | 212~213ms 串行 | 0~150ms（并行隐藏 + 熔断快速失败） | 移出关键路径 |
| memory 召回 | 80~107ms 串行 | 并行隐藏（mem_par_await≈检索窗） | 移出关键路径 |
| milvus 段 | 460~487ms | 428~751ms | 持平（嵌入+远端 RTT 物理下限，未动） |
| LLM 首 token（非本批靶） | 6.354~6.385s | 3.758~10.752s（LLM 波动大） | 不受本批影响 |

> 实测后 sixnode 有一处纯日志行格式修正（fanout-profile 汇总列），不影响计时路径；after 数字取自该修正前同代码路径。

## §4 验收实证

### ① start→retrieval 3 次取中位
见 §3：热态 4 轮 1.503/1.606/1.733/1.979s，中位 **1.67s ≤ 2s**（含首请求冷态 5 轮中位 1.733s）。复跑：`edu-agent/` 下 `.venv/Scripts/python.exe ../test-reports/r02tail-ttft-probe.py 3`（需先起 8010 临时实例并等预热）。

### ② knowledge 通道 Jaccard 复跑（r20b 双跑 100 样本，seed=20260914）
**结果：knowledge 通道 82/82 条 Jaccard=1.000（min=1.00），intent 分歧 0%（0/100），need_search 分歧 0%，unstable=0**——与 R02 参数对齐后基线逐位一致，红线✅。复跑耗时 659s（100 样本）+ 语义抽检 30 条。分组：chat_history-knowledge 34、edge_chitchat 6、edge_knowledge 6、edge_tool 4、eval_set32 32，**全部=1.000**；非 knowledge 18 条（tool/learning 子代理结构面，R20-b 已登记 P2-23）mean=0.1667，与 R02 同为结构性残差（本批未触碰子代理编排），全量均值 0.85。
产物：`test-reports/r02tail-dualrun-results.json`（逐样本）/ `r02tail-dualrun-summary.json` / `r02tail-dualrun-baseline.md` / `r02tail-dualrun-rerun.log`。
**冻结文件处置（如实披露）**：`dualrun-summary.json`（45eb81ce）/ `dualrun_samples.json`（d5c2c2b6）/ `test-reports/dualrun-baseline.md`（518899e8）/ `scripts/eval/dualrun-baseline.md`（7b29f206=git HEAD）复跑前后 md5 一致或已从 git md5 级恢复。例外：`scripts/eval/dualrun_results.json` 为 git-ignored（.gitignore:45 `*_results.json`）每轮覆盖产物，本轮复跑将其覆盖为 2026-09-15 内容且**无同字节备份**（开工时仅快照 md5=c567fa1f 未快照内容，流程疏漏）；该文件角色即"最近一轮逐样本明细"（探针每次运行覆写），人读/机验冻结参照由 tracked 的 dualrun-baseline.md/dualrun-summary.json 及 R02 会话拷贝 `r02-dualrun-results.json` 承担，本批复跑明细另存 r02tail-dualrun-results.json。

### ③ SSE 契约回归（task104 口径）
- 活体：`r02tail-ttft-probe.py` 5 轮全部 `start→retrieval→token(delta)×N→done`，done 壳 `code:0,message:"ok"`，token 字段 `delta`，retrieved_count=150/final_count=5，零 error 帧。
- 单测（合并一轮）：`r02tail(5) + r02(16) + chat_stream_error(6) + task31(12) + task24(6)` = **45 passed**（最终复跑 2026-09-15 10:2x）。
- 新增：`tests/test_contract_task_r02tail.py` **5 passed**（熔断三态/并行通道语义+降级顺序/fan_out 并行重叠）。

### ④ STREAM_VIA_GRAPH 开关不受影响
开关分发代码零改动（router.py 未触碰）。单测 `test_switch_on_routes_to_graph_adapter` / `test_switch_off_falls_back_to_legacy_path` PASS（r02 套件内）；另 8010 实测 `STREAM_VIA_GRAPH=false` 回退（10:22）：帧序 `start→retrieval→token(delta)×235→done(code:0)` 等同、done.data 七字段齐全、日志仅见旧路径 `decide_agent_plan 规则决策命中（0-LLM）`、该窗口 `graph_stream` 命中=0（grep 实证）；旧路径检索同样吃到本批修复（同一 `retrieve_three_channel`：degraded='rerank_sidecar_unavailable' 且无 2s sidecar 烧损）。实例用完 taskkill 关闭。

## §5 环境注记（诚实申报）

1. **8000/3000 今日未在运行**（本会话开始时探测即无监听）——未启动、未触碰，无"禁重启"冲突；全部实测走 8010 临时实例（用完即关）。
2. **Neo4j（192.168.85.101:7687）今日 DOWN**（9-14 基线当日为 UP，r02_8010.log"Neo4j 连接成功"）：今日 graph 段数字为熔断快速失败口径；UP 场景下修复③的收益是结构性的（串行 sum→并行 max，graph 耗时全额移出关键路径，只要 graph≤milvus 即完全隐藏）。
3. **rerank sidecar（8601）今日与 9-14 基线同为 DOWN**（旧日志同款 ConnectError）——即编排者 3.38-3.6s 基线同样含 ~2.05s sidecar 烧损；本批把它消除。
4. 双跑复跑首轮曾 Segfault（BGE 加载后，疑似强杀 8010 后 CUDA 上下文残留竞态）；GPU 静置后复跑正常，全程无写入（冻结文件 md5 未变）。
5. 工作区中 `app/chat/tool_calling.py` 等既有改动属 R12 会话（TOOL_DECISION_MODE），**未纳入本批 commit**。

## §6 硬性守则自检

1. 禁 DB 直写：全程无 SQL 写入✅
2. SSE 契约冻结：帧格式/字段零改动（graph_stream 仅加观测日志）✅
3. 禁改前端/contracts：未触及✅
4. 禁 Playwright：requests/httpx/pytest✅
5. 检索参数与语义：hyde=True/top_k=12/5/0.40 未动（`sixnode_retrieval_params` 原样）；Jaccard knowledge 通道复跑 1.000✅
6. 旧路径行为：`retrieve_three_channel` 为两路径单一事实源，修复对两侧等价生效；旧路径契约测试 PASS✅
7. commit/报告：`feat(r)/R02-tail-ttft` + 本报告✅

## §7 遗留与建议

1. **LLM 首 token ~1.9s**（编排者分解的另一半）非本批靶，首 token 波动大（3.8~10.8s，strong 402 降级 fast 环境同 R02 登记），建议维持 task29 批判②口径跟踪。
2. skill registry 首扫（318 项，~1-3s）发生在进程首个请求，建议后续并入启动预热（`app.core.warmup`），属冷态优化，独立小任务。
3. sidecar 熔断冷却窗（60s）到期后单请求会再付一次连接失败代价（现 1s 封顶）——如需彻底消除，运维侧拉起 8601 sidecar 即回到最优路径（HTTP 重排 + 事件循环零阻塞）。
