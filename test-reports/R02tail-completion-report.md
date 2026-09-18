# R02-tail 完工报告：TTFT 检索段优化（start→retrieval）

- 执行：ZCode-R02-tail ｜ 完工：2026-09-15 ｜ 工作区 `E:\stu\project\stu\EduAgent实施手册`
- 任务：profile→优化 start→retrieval 段（编排者活体基线 3.38-3.6s，目标 ≤2s 或对齐旧路径同段水平）
- 交付 commit：`feat(r)/R02-tail-ttft` = **`fbcb778`**（主体 13 文件；注：本批新增 config.py 配置段 17 行（`RERANK_CONNECT_TIMEOUT`/`RERANK_SIDECAR_COOLDOWN_S`）因共享工作区竞态被并行 R12 会话的 `509496d` 连带先行提交，已生效于 HEAD，归属以本说明为准）
- 复跑：`test-reports/r02tail-ttft-probe.py`（8010 临时实例）、`scripts/eval/r20b_dualrun_probe.py`（Jaccard 复跑）、`tests/test_contract_task_r02tail.py`（新增 5 单测）
- **C-01 复测补充（2026-09-19，W-NEXT-R02TAIL-001 第二轮派单）：LLMSWITCH+R12 落地后的双路径真实流式 TTFT 复测 + 灰度记分卡 → 见文末「§C-01」章节**（首 token P95 未达冻结预算，检索段大幅优于预算；逐项拆解与口径裁定建议在内）

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
7. commit/报告：`fbcb778`（feat(r)/R02-tail-ttft）+ 本报告✅
8. **工作区竞态登记**：本会话工作期间，并行 R12 会话提交 `509496d`（R12-llm-tool-decision）将本批 config.py 新增段（17 行）连带入库——该段内容为本批所写且已验证生效（8010 实测连接超时 1s 生效），归属以 commit message 与本报告为准；本批 commit 未纳入 R12 的 tool_calling.py 等文件。

## §7 遗留与建议

1. **LLM 首 token ~1.9s**（编排者分解的另一半）非本批靶，首 token 波动大（3.8~10.8s，strong 402 降级 fast 环境同 R02 登记），建议维持 task29 批判②口径跟踪。
2. skill registry 首扫（318 项，~1-3s）发生在进程首个请求，建议后续并入启动预热（`app.core.warmup`），属冷态优化，独立小任务。
3. sidecar 熔断冷却窗（60s）到期后单请求会再付一次连接失败代价（现 1s 封顶）——如需彻底消除，运维侧拉起 8601 sidecar 即回到最优路径（HTTP 重排 + 事件循环零阻塞）。

---

# §C-01 复测补充：LLMSWITCH + R12 落地后双路径真实流式 TTFT 复测 + 灰度记分卡

- 执行：W-NEXT-R02TAIL-001（C-01 编排者逐断言独立实证验收）｜ 2026-09-19 ｜ 分支 `feature/opt-waves`
- 派单背景：R02 流式进图后活体 TTFT 5.27~5.32s > 冻结预算 4.51s（+18%）→ R05（删旧路径）冻结。此后两项变量落地：①LLMSWITCH（答案主模型 deepseek-flash）②R12 exact-pin（双跑 Jaccard 0.8533→1.0）。本批在两变量落地后的 HEAD 复测。
- 测量对象 HEAD：`baa6e0a`（开工时 rev-parse 实测）｜ 交付 commit：`test(r)/R02tail-C01` = **`61f2161`**（9 文件：探针脚本+data 产物×3+报告+证据日志×4）
- 红线自检：未删旧路径、未动 STREAM_VIA_GRAPH（两值分别实测）、未执行 R05、未触 app/**、contracts/**、config.py、tests/**

## §C-0 结论速览（供编排者直读）

| 口径 | 新图路径（STREAM_VIA_GRAPH=true） | 旧路径（=false） | 冻结预算 4.513s 判定 |
|---|---|---|---|
| **首 token P50**（start→首 token） | **2.707s** | 2.828s | 双双达标 |
| **首 token P95** | **6.262s** | 4.805s | **双双未达**（新 +38.8%，旧 +6.5%） |
| **检索段 P50**（start→retrieval，R02-tail 优化段） | **1.388s** | 1.271s | 大幅优于预算 |
| **检索段 P95** | **1.696s** | 1.623s | **达标**（预算的 37.6%；新旧差 +0.074s=噪声级） |
| 逐轮配对差（新−旧，首 token） | mean +0.054s / median +0.185s | — | 图路径典型情况≈零额外开销 |
| 跨路径 docs Jaccard（SSE retrieval 帧逐轮配对） | **55/55=1.0** | 同左 | R12 结论独立旁证 ✅ |

**一句话结论**：R02-tail 优化过的检索段在新图路径上完全健康（P95 1.70s ≪ 4.51s，且与旧路径无显著差）；首 token P95 超标**不是图路径结构性开销**——同轮旧路径首 token P95 同样超冻结预算（4.80>4.51），两实例 `[LLM-stream]` 首 chunk 分布几乎相同（P50 1.49/1.55s，P95 4.53/4.73s，max 7.9/7.2s），超标根因=deepseek-flash 流式首 chunk 供应商方差，属两路径共有的环境项。**冻结预算 4.51s 在「首 token 口径」下连旧路径都压不住；在「检索段口径」（W0 探针原口径）下双路径均大幅达标**——口径裁定属用户/编排者（本探针只报数，两种口径均已给出）。

## §C-1 测量环境（一次性独立实例 :8011，用后即清；共享 8000 零接触）

| 项 | 值 | 证据 |
|---|---|---|
| 实例 | uvicorn app.main:app --port 8011 ×2 次（graph 轮→杀→legacy 轮→杀），8011 端口用后无监听 | `test-reports/r02tail-c01-8011-*.log` |
| 共享 8000/3000 | 全程未重启未触碰（生产实例零扰动；测量流量全部指向 8011） | 本声明 + 8000 进程 PID 全程未变 |
| STREAM_VIA_GRAPH | true/false 各一实例；路径分发 grep 实证：graph 实例 `graph_stream` 命中 58 / `decide_agent_plan` 0；legacy 实例 0 / 61 | 两实例日志 grep 计数 |
| temp=0 | 实例 env `LLM_TEMPERATURE=0` 显式钉死；路由 RULE_ROUTING_ENABLED=True（0-LLM 纯正则，日志「规则决策命中（0-LLM）」） | 实例日志 |
| 同一 LLM | 两路径答案流均 `model="strong"`→`deepseek-flash`（新图路径 sixnode 固定 strong；旧路径由本探针请求体显式传 model="strong"，schemas 默认 fast 被覆盖） | 实例日志 `[LLM-stream] … (model=deepseek-flash)` ×116/122 |
| thinking-disabled | **流式不注入（as-built，LLMSWITCH 设计决策：`call_chat_stream` 不调用注入，单测钉死）**——派单词「thinking-off」仅对非流式成立，如实登记差异 | generator.py:207 + LLMSWITCH 报告 §6 |
| 嵌入 | 派单允许的 `EMBED_BACKEND=cpu` 实际语义=「非 cuda → cloud-first」（warmup.py:156）；**云端嵌入被 SSRF 出站门拒绝**（dashscope 不在白名单，graph 实例 118 次 `[W-NEXT-EXE-SSRF-002]`）→ 实际两路径均回退本地 BGE-M3 CUDA（同机同模型同空间），口径一致 | 实例日志；此环境事实使「cpu 指令」对有效嵌入路径无实际影响（P0-2 自批判） |
| 共享依赖恢复 | 开工时 Redis 6379 / rerank sidecar 8601 均 DOWN（LLMSWITCH P0-2 同款环境缺损，会致 TTFT 虚高 3×）→ 已按其运行态移交恢复：Redis（tools/redis）+ sidecar 8601（cuda，/health model_loaded=true）——属共享基础设施恢复，非 8000 重启；用后保留运行（对齐 LLMSWITCH 移交态，8000 生产实例亦受益） | 本批操作日志 |
| GPU | 8.2GB 总量中 8000 生产占 ~4.6GB + sidecar 1.1GB；BGE-M3 两实例均成功本地 CUDA 加载（唯一一次失败见 §C-4 P0-3） | nvidia-smi + 实例日志 |
| FAST 配额 | ark 周配额 429（AccountQuotaExceeded，LLMSWITCH P0-5 同款，2026-09-21 00:00 重置）——仅影响记忆抽取旁路（落 degraded 非阻塞）与工具子代理决策 fail-fast；答案主链（deepseek-flash）零 429 | 实例日志 429 计数 60/33 |
| 确定性 | 每路径 3 预热轮（吸收 BGE/Milvus 冷启动，不入统计）+ 55 测量轮（无 RNG 固定轮转 8 knowledge+2 chitchat+1 tool ×5 循环，镜像 W0 样本构成方向）；**测量轮零降级、零 error 帧、done code 全 0** | results JSON 逐轮 rows |

## §C-2 双路径 TTFT 数字（n=55/路径，2026-09-19 06:31~06:50）

| 指标 | 新图路径 | 旧路径 | 预算对照 |
|---|---|---|---|
| start→retrieval P50 / P95 / max | 1.388 / 1.696 / 2.017s | 1.271 / 1.623 / 2.258s | 检索段 P95 = 预算的 37.6% |
| start→首 token P50 / mean / P95 / max | 2.707 / 3.259 / 6.262 / 9.475s | 2.828 / 3.204 / 4.805 / 9.470s | 首 token P95：新 +38.8%、旧 +6.5% |
| LLM 首 chunk（实例日志 [LLM-stream]）P50 / P95 / max | 1.49 / 4.53 / 7.88s（n=58） | 1.55 / 4.73 / 7.21s（n=61） | 供应商项两路径同分布 |
| knowledge 子集首 token P50 / P95 | 3.061 / 6.306s | 2.520 / 4.580s | 同上结构 |

**尾部归因（逐轮配对，同计划同序）**：新图 >5s 共 6 轮 vs 旧 3 轮；其中 tool 查询「查一下 2 的 20 次方」两路径同轮双超（6.26/9.47s）；「后备干部梯队」长 query 在图轮 4 次命中 5~9.5s（该 query 提示长、生成答案长）；配对差中位 +0.185s。两路径 max 几乎逐位相同（9.4749/9.4697）——尾部为 LLM 供应商方差与重 query 特性，非路径结构差。**登记一项口径差异（非本批缺陷）**：图路径 answer 节点前有 reflect 节点与节点间调度（~几十 ms 级，node_arrivals 日志可查），已含在上数字中，未发现秒级图内额外段。

**产物**（rn2 同款，`scripts/eval/data/r02tail_runs/`）：`r02tail-ttft-graph-results.json` / `r02tail-ttft-legacy-results.json`（逐轮明细，含帧序/docs/degraded/逐 token 数）+ `r02tail-ttft-dualrun-summary.json`（分位数+门槛判定+55 对配对 Jaccard）。复跑：`scripts/eval/r02tail_ttft_dualstream.py --label graph|legacy --rounds 55` + `--summarize`。

## §C-3 灰度五条件记分卡（contracts/reshape-r-eval-draft.json dualrun_gate_R02b）

| # | 条件 | 现状 | 判定 |
|---|---|---|---|
| 1 | intent 分歧率 < 5% | R12 复验（commit `90f7391`，入库证据）：**0%**（0/100，exact-pin 后 tool/learning 残差 18→0）；RN2 会话跨验重跑（2026-09-19 00:50，git d0fc59b 时代，工作区未入库旁证）0%；本批 C-01 独立旁证：SSE 帧配对 Jaccard 55/55=1.0 | **✓** |
| 2 | docs Jaccard > 0.9 | 同上两轮 **1.0**（100/100 全等；p95=1.0）+ 本批独立旁证 55/55=1.0 | **✓** |
| 3 | P95 TTFT 不劣化超阈值（冻结=旧 P95 4.103×1.1=4.513s） | **按首 token 口径：未达**（新 6.26s +38.8%；旧 4.80s +6.5%——旧路径亦超，超标根因=LLM 首 chunk 供应商方差，两路径共有）；**按检索段口径（W0 探针原口径）：达标**（新 1.70s vs 旧 1.62s，差 +4.6% 噪声级） | **✗/✓ 分歧于口径——需用户裁定** |
| 4 | 连续 3 天满足上述 | 未开启灰度窗口（W0/R02/R12/RN2/本批均为单日单批） | **✗ 待时间窗** |
| 5 | 累计样本 ≥ 1000 | 双跑口径累计 ~300+（100×3 轮）+ 本批 55×2（真实流式，非双跑门槛口径）；未达 1000 | **✗ 待灰度期累积** |

**R05（删旧路径）解锁差距（结构化，供编排者转用户）**：
1. **条件③口径裁定（唯一非时间项）**：冻结预算由 W0 探针「start→首检索完成」代理推导，与活体「start→首 token」口径天然错位（后者多含 LLM 首 chunk 1.5~4.7s 供应商项）——按首 token 口径连旧路径都不达标，门槛失去区分两路径的能力。裁定选项：a) 以检索段口径判定（两路径已大幅达标）+ 首 token 作为观察项；b) 维持首 token 口径→需先做 LLM 首 chunk 提速（候选：流式也注入 thinking=disabled，需改 generator.py+补 reasoning delta 帧审计，属用户裁决的新变更批，非本批范围）；c) 预算改锚定为「同轮旧路径实测×1.1」（本轮=5.29s，图 6.26 仍未过，尾部 3 轮重 query 主导）。
2. **条件④⑤（纯时间投入）**：开启灰度期连续 3 天双跑（R20-b 探针每日 1 轮×3）+ 累积 ≥1000 样本——无代码缺口，需真实窗口排期。
3. R05 本身=用户裁决项，本批未执行、未预置任何删除。

## §C-4 P0 自批判（5 条）

1. **P0-1 预算口径错位贯穿始终，本报告若只报一个数字就会误导**：4.51s 预算源自 W0 探针检索代理口径，而活体超标（5.27~5.32）与本次复测均为首 token 口径——两口径相差一整个 LLM 首 chunk 项。若我只报「检索段 1.70s 达标」会掩盖「首 token 6.26s 超标」；只报后者会掩盖「旧路径 4.80s 同样超标、门槛已失去区分度」。处置：双口径并列+根因分解（LLM 首 chunk 分布两路径同分布为铁证），裁定权交还编排者。
2. **P0-2 `EMBED_BACKEND=cpu` 指令对有效嵌入路径无实际影响（指令语义落空）**：cpu 在 warmup.py:156 的语义只是「非 cuda→cloud-first」，而云端嵌入被 SSRF 出站门全部拒绝（118 次），两实例实际均回退**本地 CUDA BGE-M3**——与派单设想的「cpu 嵌入」不同，但两路径同机同模型同空间，对比口径成立。教训：环境变量语义必须读到生效分支（对齐 LLMSWITCH P0-1 教训），SSRF 白名单使 cloud-first 在本机形同虚设本身也值得登记（生产 8000 同样处于「云端必拒→本地回退」态）。
3. **P0-3 legacy 首次测量实例在本地 BGE 加载后死亡（CUDA 上下文竞态前科复现），第一轮 legacy 数据作废**：强杀 graph 实例后 2s 内启动 legacy 实例，BGE-M3 cuda 加载完成即静默消失（日志无 traceback，进程退出）——与 R02tail §5.4「强杀 8010 后 CUDA 残留竞态→Segfault」同款。处置：GPU 静置 75s 后重启+热探针验证存活再跑全量；作废轮仅 warmup 1 轮（ret 8.10s 含 Milvus 冷超时），未混入任何统计。教训：同 GPU 上先后强杀/新起重模型进程必须留静置窗，且重启后先做存活探针。
4. **P0-4 本批 55 轮样本的 P95 对「3 个重查询轮次+供应商抖动」高度敏感**：图路径 >5s 的 6 轮中 4 轮是同一长 query（后备干部）+1 轮 tool query 两路径双超——P95=6.26s 与 4.80s 的差主要由图轮运气（该 query 命中供应商慢窗口）贡献；若换一天重测，双路径 P95 可能互换。样本构成中 tool 轮仅 5 轮（P95 尾部由 tool/重 query 主导时 n=5 的分位数不稳）。缓解：已给出逐轮配对差（中位 +0.185s）与 LLM 首 chunk 大样本分布（n=58/61）作为比 P95 更稳的口径；灰度期 3 天累积才是最终判据。
5. **P0-5 两路径测量处于不同 wall-clock 窗口（06:31~06:37 vs 06:42~06:50）**：实例切换（杀→起→预热）导致两路径非同时测量，供应商负载漂移不可排除（LLMSWITCH P0-2 同类环境漂移风险）。缓解：检索段对比（provider 无关段）两路径 P95 差仅 +0.074s，说明机器侧环境稳定；LLM 项差异无法用本设计排除，已用配对差与同分布证据限定结论强度。更优设计（同实例双请求交织或双端口并行）需两实例同抢 GPU/连接池，会引入新扰动，未采用——如实登记取舍。

## §C-5 批判承接核对（R02-tail 登记项承接）

| 登记项（tracker R02 验收 / R20-b 批判） | 本批处置 |
|---|---|
| 「TTFT 活体超标=登记尾巴，复测=R02-tail 任务（归 W3）」 | **本批即该复测**：双路径 55 轮真实流式复测完成，数字+口径分歧+根因分解交编排者（§C-2/§C-3） |
| C-b「TTFT 1.10× 贴线风险，灰度期必须持续监控」 | 监控执行：检索段两路径 P95 1.70/1.62s（贴线风险已在检索段消除）；新风险面（LLM 首 chunk 供应商方差）已量化登记（§C-4 P0-4） |
| R02 验收④「灰度门 TTFT 项未过→旧路径保留，R05 冻结至达标」 | 未动旧路径、未执行 R05；解锁差距清单化交用户（§C-3） |
| 其余登记项 | 无其他指向本批的承接项（本轮派单即 C-01 验收本身） |

## §C-6 资产消费证据

| 派单具名资产 | 消费方式 |
|---|---|
| kickoff-R20b-single.md | 确定性设计/样本构成方向/TTFT 代理口径背景读取 |
| scripts/eval/r20b_dualrun_probe.py | TTFT 代理口径、`_pct` 百分位算法照抄、边界样本逐字复用（EDGE_CASES 子集）、Jaccard 算法复用 |
| test-reports/r02tail-ttft-probe.py（上一轮 R02-tail 仪器） | SSE 逐帧计时测法照抄（start→retrieval / start→首 token），扩展 docs 捕获 |
| scripts/eval/data/rn2_runs/rn2-dualrun-*.json | 产物格式模板（summary+results 双 JSON 结构对齐） |
| contracts/reshape-r-eval-draft.json | 灰度五条件原文（dualrun_gate_R02b）→ 记分卡逐条对照 |
| AGENTS.md | 测试账号、启动范式、教训 2/3/9、限流 429 awareness |
| tracker（.opencode/plans/critique-backlog-tracker.md）R02 验收段 | 活体 5.27~5.32s/预算 4.51s 原文、R02-tail 登记项承接核对 |
| R02/R02tail/LLMSWITCH/R12 完工报告 | 预算推导链、检索段优化现状、thinking 流式不注入设计、FAST 429 周期、CUDA 竞态前科 |
| test-reports/dualrun-baseline.md（工作区 d0fc59b 版，未入库） | 记分卡条件 1/2 旁证（标注来源与未入库属性，未纳入本批 commit） |

## §C-7 复跑命令

```bash
cd edu-agent
# 1) 共享依赖（若 DOWN）：tools/redis/redis-server.exe + .venv/Scripts/python.exe -m uvicorn app.rerank_service.main:app --port 8601
# 2) 一次性实例（graph 轮）：
EMBED_BACKEND=cpu LLM_TEMPERATURE=0 STREAM_VIA_GRAPH=true .venv/Scripts/python.exe -m uvicorn app.main:app --port 8011 > logs/x.log 2>&1 &
.venv/Scripts/python.exe scripts/eval/r02tail_ttft_dualstream.py --label graph --rounds 55
# 3) 杀实例 → 静置 ≥60s（CUDA 竞态，见 P0-3）→ 以 STREAM_VIA_GRAPH=false 重启 →：
.venv/Scripts/python.exe scripts/eval/r02tail_ttft_dualstream.py --label legacy --rounds 55
# 4) 杀实例 → 汇总：
.venv/Scripts/python.exe scripts/eval/r02tail_ttft_dualstream.py --summarize
```

产物：`scripts/eval/data/r02tail_runs/r02tail-ttft-{graph,legacy}-results.json` / `r02tail-ttft-dualrun-summary.json`；证据日志 `test-reports/r02tail-c01-*.log` ×4；本报告 §C-01 章节。
