# R02 完工报告：流式主路径进 LangGraph（dev-plan-reshape-r W2）

- 执行：ZCode-R02 ｜ 完工：2026-09-15 ｜ 工作区 `E:\stu\project\stu\EduAgent实施手册`
- 会话背景：接手 2026-09-14 中断的上一 R02 会话（遗留 r02.lock + 未提交 TDD 半成品）；本会话逐行审查其改动后**补齐/修复 6 处**（见 §3），全部验证独立重跑。
- 交付 commit：`feat(r)/R02-stream-graph`（主体）+ `fix(r)/R02-legacy-test-pin`（旧路径测试钉开关）+ `fix(r)/R02-eval-safeio-import`（eval 脚本 _safeio 双模式导入，修 test_e1 收集阻断）

---

## §0 四件套结论速览

| # | 任务 | 状态 | 核心证据 |
|---|---|---|---|
| 1 | 执行体切换（graph.astream 适配层 + STREAM_VIA_GRAPH 开关） | ✅ | 8010 实测五事件帧序 start→retrieval→token(delta)×301→done 壳 code:0；开关 false 回退旧路径实测等同（§5） |
| 2 | guard 移植 + Redis 槽 TTL 自愈 | ✅ | 流式主路径 acquire/release 成对（单测断言异常路径也 release）；真 Redis 实证残留槽满仍拒+拒绝路径 TTL 刷新自愈（§4.2） |
| 3 | thread_id 修复（R02-c） | ✅ | 同用户两笔匿名请求 → Redis `edu:ckpt:anon-{uuid}` 两键不同（grep 级实证，§4.3） |
| 4 | 检索参数对齐 + run_agent 空 docs 回填 | ✅ | 图内检索默认 hyde=True/top_k=12/final_max_k=5/cutoff=0.40 对齐旧路径；双跑复验 knowledge 通道 docs Jaccard=1.000（n=82）；非流式返回体真实 docs（单测） |

---

## §1 双跑复验数字（R20-b 探针原脚本重跑，seed=20260914，100/100 valid，unstable=0）

复跑命令：`.venv/Scripts/python.exe scripts/eval/r20b_dualrun_probe.py`（r20b_* 冻结文件只读未动；重跑产物另存 `scripts/eval/r02-dualrun-summary.json` / `r02-dualrun-results.json`；冻结 `dualrun-summary.json`/`dualrun_results.json`/`dualrun-baseline.md` 已按 md5 恢复原样，samples.json 重跑前后 md5 相同 `d5c2c2b6…`）。

| 指标 | R20-b 冻结基线 | R02 复验（参数对齐后） | 门槛 |
|---|---|---|---|
| intent 分歧率 | 0%（0/100） | **0%**（0/100，分源全 0） | <5% ✅ |
| docs Jaccard mean | 0.6411 | **0.8533**（p50=1.0，=1 共 82 条，<0.5 共 18 条，=0 共 8 条） | 参考 >0.9，**未达**，逐样本归因见 §1.1 |
| need_search 分歧（报告项） | 0% | 0% | — |
| 答案语义 30% 抽检（非门槛） | 27/30 equivalent | 27/30 equivalent（judge_failed=0） | — |

### §1.1 Jaccard 逐样本归因（如实报告，机验可复现）

对 `r02-dualrun-results.json` 100 样本按 (source, new_intent) 分组：

| 分组 | n | Jaccard mean | 判定 |
|---|---|---|---|
| knowledge（eval_set32 32 + chat_history 34 + edge_chitchat 6 + edge_tool 4 + edge_knowledge 6） | **82** | **1.000（min=1.00）** | 参数对齐后**逐条完全一致** |
| tool / learning（chat_history 12+4 + edge_tool 2） | 18 | 0.25 / 0.083 / 0.0 | 结构性分歧（见下） |

- **参数差异面已闭合**：knowledge 通道（六节点直连检索快路径）82/82 条 Jaccard=1.0——R20-b 根因（图内硬编码 use_hyde=False/top_k=8/cutoff=0.2 vs 旧路径 True/12/0.40）修复生效，旧新两路径对同一 query 现在产出**逐位相同**的 docs。
- **残差 100% 集中在 tool/learning 意图**：这 18 条全部走子代理编排（sub_n=3），其检索 query 是 plan 节点的任务输入串（逐字证据：`new_q0="基于问题给出检索要点（问题：X）\n\n[历史上下文（经 context_edit 编辑…）]"`），而旧路径检索用原 query——属 R20-b 基线已登记的 P2-23 结构性分歧面（dev-plan v1.1 W3/R12「LLM 工具决策接管」处理），**不是 R02 参数对齐范围**，强行归一反而要在 R02 提前动子代理编排（超范围、风险）。此项交由 R02-b 灰度期/W3 继续跟踪。
- 结论：mean 0.8533 未达 0.9 的缺口 = 18 条子代理结构样本；**参数对齐覆盖面（82 条 knowledge）收敛度=100%**。

## §1.2 TTFT（R02-d 预算）

探针口径（与冻结基线同仪器）：旧=决策完成→检索完成；新=start→hook 首检索完成（口径本身不对称：旧路径的 decide_agent_plan 决策耗时**不计入**，新路径的 route/skill/compact/context_edit/plan 全管线**计入**；探针 docstring 自认"近似口径"）。

| 口径 | 旧 P50/P95 | 新 P50/P95 | 预算判定 |
|---|---|---|---|
| 全量 100（与冻结基线同口径） | 3.401 / 4.017s | 3.466 / **4.520s** | 对冻结阈值 4.103×1.10=4.513s：+0.15%（4.520 vs 4.513，贴线）；对同轮重测旧 P95×1.10=4.419s：超 2.3% |
| **knowledge 直连快路径**（n=82，即 R02-d 指定的"图内快路径"） | 3.350 / 4.115s | 3.421 / **4.053s** | **PASS：4.053 ≤ 4.115×1.10=4.527，且 new P95 < old P95（ratio 0.985）** |
| 子代理编排样本（n=18，tool/learning） | P95 3.758s | P95 4.655s | 尾部差唯一来源（+0.85~1.1s/条：子代理 runner 装配 + memory recall embedding 并行链），W3/R12 结构面 |

**优化义务履行**：按"超了先优化图内快路径"执行——排查了 compact_node 的 make_fast_llm（纯闭包构造，非瓶颈）、skill 触发扫描（ms 级）、PlainRedisSaver 逐超步快照（durable 功能件，禁砍）。结论：**直连快路径已无劣化（反快 1.5%），整体 P95 贴线部分 100% 由子代理结构样本贡献**，R02 范围内不存在不砍功能可收敛的杠杆；如实上报交编排者裁（建议 R12「决策超时预算/子代理编排」承接）。
**生产形态补证（8010 实测）**：新路径 start 帧**立即**发出（适配层先发 start 再执行图），旧路径 SSE 响应头要等决策+检索+MCP 全部完成后才开始——用户可感知 TTFT 新路径反而更优（日志：`ttft_retrieval_ms=3535~5822, ttft_first_token_ms=5397~9052`，`edu-agent/logs/r02_8010.log`）。

---

## §2 执行体切换（四件套①）

- 入口分发：`app/chat/router.py` chat_stream_sse — `settings.STREAM_VIA_GRAPH`（config.py，默认 **True**）True→`flows/graph_stream.py graph_stream_sse`；False→原 `service_chat_stream` 逐字节不动。
- 适配层 `graph_stream.py`：`g.astream(state, config, stream_mode=["updates","custom"])` 双通道消费——updates（节点更新）驱动 retrieval 帧（fan_out 携带 `state.retrieval` 真实检索产物）；custom（节点内 StreamWriter，`sixnode._stream_answer_tokens`，configurable.stream_tokens 逐请求门控）驱动 token 帧；token 先于 retrieval 到达时缓冲重放（保帧序）；chitchat 直连按旧路径口径发空 docs retrieval 帧。
- SSE 契约冻结未改（contracts/reshape-a.json hash 不变）：token 帧 `{"delta": ...}`、done 帧内嵌 `{code:0,message:"ok",data:{...}}`、两段式错误模型（建连前同步 HTTP / 建连后 `event:error` 可区分码）、落库失败 error(CHAT_PERSIST_FAIL)+降级 done 兜底——逐字段与旧 router `_gen` 对齐（sse.py 单一实现，router 保留同名 re-export，历史测试契约不破）。
- 落库/审计/记忆 ingest 收敛为 `service.make_stream_finalize` 工厂，新旧路径单一事实源（防 P2-23 漂移）。
- P2-9 顺带修复：`service.chat_answer` 的 `plan = None` 前置初始化（USE_AGENT_LOOP=False 不再 UnboundLocalError，单测覆盖）。
- 兜底加固（本会话补）：answer 节点静默回退阻塞生成（custom writer 不可用/未吐 token）时，适配层把 `state.final_answer` 补发为 token 帧再收束——不丢答案（单测 `test_graph_stream_flushes_state_answer_when_no_custom_tokens`）。MCP 并行预取改 `asyncio.ensure_future`（对齐旧路径 create_task 编排）+ 异常路径取消悬挂任务（消灭"coroutine never awaited"）。

## §3 本会话对上一会话半成品的补齐/修复清单（全部独立验证）

1. `tests/test_contract_task_r02.py` 4 处 `lambda: fake` 同步 mock → async（`await _ensure_agent_graph()` TypeError 根因），并修 error 测试脚本构造（单事件 raise_at=1 永不触发→0）与错误码断言（弱断言改 LLM_AUTH 精确断言）。
2. Redis TTL 单测用归一化 URL（localhost→127.0.0.1 task39 口径）——原写法误判 Redis 不可用而 skip，现真 Redis 实跑 PASS。
3. 旧路径契约测试 `tests/test_chat_stream_error.py` 钉 `STREAM_VIA_GRAPH=False`（其 mock 的是旧路径 service_chat_stream；新默认开关下被绕过打到真 LLM——HEAD vs 改动全量对账中**唯一**真回归，4 条）。
4. `_safeio` 双模式导入（5 个 eval 脚本）：`try: from _safeio … except ImportError: from scripts.eval._safeio …`——修 `test_contract_task_e1.py` 以包导入时的 ModuleNotFoundError 收集阻断（上一会话遗漏提交 `_safeio.py` 本体，一并入库）。
5. graph_stream.py：MCP ensure_future + finally 取消；final_answer 补发兜底（§2）。
6. 新增单测：final_answer 补发兜底 1 条（R02 套件 15→16 条）。

## §4 验收实证（自证，可复跑）

### §4.1 pytest
- R02 新增套件：`tests/test_contract_task_r02.py` **16 passed**（开关分发/图路径五事件契约/chitchat 空帧/帧序缓冲重放/错误码映射+guard 成对/guard 拒绝语义/thread_id 匿名隔离×3/检索参数对齐+capture 回填/run_agent docs 回填/guard TTL×2/P2-9/final_answer 兜底）。
- 相关域组合：r02+chat_stream_error+chat_delete+agent_loop+task24(图)+task26(guard)+guard_queue_degrade+perf_guard+task39+checkpoint_hmac = **102 passed, 1 skipped**。
- 全量对账（零新增失败）：全量 tests/（除 performance/integration）改动后 76 failed/872 passed vs stash 后 HEAD 73 failed/860 passed；差集仅 §3-3 的 4 条（修复后归零）+1 条 HEAD 挂而本次过的 MCP live 抖动。剩余 73 条失败两轮逐条同集合=存量环境依赖（live-8000 登录限流 429/Milvus 外机/全量跑事件循环污染），与 R02 无关（task20/21/22 单跑隔离全绿已验证）。

### §4.2 guard 移植 + TTL 自愈
- 流式主路径 acquire 在 start 帧后、release 挂 finally 双兜底（astream 异常/断连/图前异常均成对；guard 拒绝=友好提示作为 token 流出+degraded_reason，不 5xx，与 run_agent 拒绝语义一致——单测断言 `acquires==1 and releases==1`，拒绝路径 `releases==0`）。
- Redis 槽 TTL：`_ACQUIRE_USER_LUA`/`_ACQUIRE_LUA` 原子 INCR+EXPIRE（无条件刷新，含超限拒绝路径），`GUARD_SLOT_TTL=600`。真 Redis 实证：预置无 TTL 残留槽=2（=上限）→ acquire 拒绝 ✓ → 拒绝后 `TTL(key)∈(0,600]` ✓（崩溃残留 600s 内自愈，不再永久卡死用户）。单测 `test_guard_ttl_heals_stale_slot` 真实跑通（非 skip）。

### §4.3 thread_id / checkpoint 键 grep 实证
`resolve_thread_id`：有 session 用 session_id；匿名每请求 `anon-{uuid4().hex}`（task24-{user_id} 全仓清除）。8010 实测（student 登录、session_id=null 连发两笔）：

```
edu:ckpt:anon-214040cc58a847bc9350fe3a1e48ef24
edu:ckpt:anon-dd94886423ff42f2b9bf6f07317c21ee
```
两笔匿名请求 → 两个独立 checkpoint 键（Redis SCAN 实证，复跑脚本 `test-reports/r02-sse-probe.py`；帧级证据 `test-reports/r02-sse-contract-capture.json` / `test-reports/r02-ckpt-keys.json`；旧路径回退复跑脚本 `test-reports/r02-legacy-probe.py`）；GWT「同用户两笔匿名请求 checkpoint 键不同且互不可见历史」PASS。8010 日志 thread_id 与 Redis 键逐一对账一致。

### §4.4 开关回退实测（STREAM_VIA_GRAPH=false）
8010 以 env `STREAM_VIA_GRAPH=false` 重启：同一 student 账号流式请求 → `start→retrieval→token(delta)×281→done(code:0)` 帧序与字段契约**等同**；日志仅见 `flows/agent decide_agent_plan 规则决策命中（0-LLM）`，`graph_stream` 零命中（grep -c = 0）——旧路径行为回归 PASS（unit 层另有 `test_switch_off_falls_back_to_legacy_path` 分发断言）。

---

## §5 KB 对标章节（硬守则⑦）

### F-C01-002 LangGraph（通道语义 / checkpointer / 中断）

| KB 判据 | 本实现落点 | 判定 |
|---|---|---|
| 通道语义：状态字段默认 LastValue（最新值覆盖），messages 用 add_messages（Binop 追加） | `AgentState`（graph.py:57-95）：messages=add_messages；新增 `retrieval` 字段=LastValue 一次覆盖（fan_out 写、run_agent/适配层读，一次检索一覆盖，无多写者冲突）；适配层 `final_updates[node]` 按节点合并亦 LastValue 口径 | 对齐 |
| 流模式：values/updates/debug/messages 四种；token 级流式走消息增量 | 用 `stream_mode=["updates","custom"]`：updates 驱动 retrieval 帧；token 走 **custom 通道**（节点内 `get_stream_writer()` 推 `{"type":"token","delta"}`）——对应 KB「自定义节点内流式旁路」，token 增量不进 state/不污染 checkpoint（P-002 因子 3：主动决定什么进上下文） | 对齐（custom 为官方 stream 机制，非 hack） |
| checkpointer：BaseCheckpointSaver 逐线程快照、thread_id 线程隔离、每超步后保存 | PlainRedisSaver（原生 Redis 复刻 InMemorySaver 语义）经 `compile(checkpointer=saver)` 挂载不变；本次 thread_id 修复使「线程隔离」语义真正成立——匿名请求不再共享 `task24-{user_id}` 单线程无限累积（修复前=隔离语义形同虚设）；checkpoint 键 Redis grep 实证 | 对齐（修复后才算真对齐） |
| 中断恢复/时间旅行（interrupt/checkpoint 续跑） | durable execution 语义保留（nodes_executed 随 checkpoint 持久化）；图内仍无 interrupt()（HITL 独立模块）——与基线一致，不属 R02 范围（R11-F HITL 承接） | 部分对齐（现状如实） |

### P-002 上下文纪律（五纪律）

| 因子 | 落点 | 判定 |
|---|---|---|
| 3 Own your context window | token 增量走 custom 通道旁路状态——对话状态只留语义完整消息，逐 token 噪声不进 checkpoint | 落实 |
| 9 Compact errors into context | LLM 失败经 `_llm_call` 统一 record_degraded + 节点级 degraded_reason（一行原因进 state），错误不整段灌入 | 已有，保持 |
| 10 Small, focused agents / 多任务不共用会话 | **本次核心对标**：thread_id 每匿名请求独立 uuid=「一件任务一个窗口」；修复前同用户所有匿名请求共用一线程无限累积=该因子反面教训的活标本 | 本次修复主体 |
| 12 Stateless reducer | 图状态外置 Redis checkpoint，进程重启同 thread_id 可续跑（durable） | 保持 |
| 13 Pre-fetch context | MCP 工具摘要并行预取（ensure_future 与图执行并行，retrieval 帧前收口），不在循环里反复取 | 对齐旧路径编排 |

## §6 硬性守则逐条自检

1. **禁 DB 直写**：全程未手写 SQL 改数据；落库仅经既有 make_stream_finalize ORM 路径（与旧路径同源）。✅
2. **SSE 契约冻结禁改**：contracts/reshape-a.json 未动（git status 干净，hash `30aeddbe…` 不变）；五事件字段逐字段对齐（§2/§4.4）。✅
3. **禁改 edu-api.js/public/*.html/contracts**：未改任一前端文件（工作区中 admin-rag-upload.html 的既有改动属其他会话，未纳入本批 commit）。✅
4. **禁 Playwright**：全部验证用 httpx/requests/curl/pytest。✅
5. **现状自证**：接手即逐行审查遗留改动 + HEAD/改动双跑全量对账定位真回归（§3-3），差距（TDD 半成品）先修后验。✅
6. **禁重启 8000/3000**：两实例全程未动（8000 独立登录冒烟通过）；验证全走 8010 临时实例（dev 形态，用完 taskkill 关闭，两阶段分别验证图路径/旧路径）。✅
7. **KB 对标**：§5。✅
8. **commits/报告**：见顶部 commit 列表与本报告。✅

现场纪律：r02.lock 开工即在（上一会话建立，本会话接续），完工即删；r20b_* 冻结文件零改动（dualrun-baseline.md mtime 仍为 2026-09-14，summary/results md5 级恢复原样）；KB 卡只读。

## §7 遗留与移交

1. **Jaccard 0.853 vs 0.9 门槛**：残差全在 tool/learning 子代理检索 query 结构（plan 任务输入串直作检索 query）——建议 R12/W3 接管（子代理 search 的 q 应取用户问题本体而非任务串）；R02 范围内已把参数面收敛到 knowledge 通道 100%。
2. **TTFT 全量口径贴线**（4.520 vs 冻结阈值 4.513，+0.15%）：口径不对称（旧侧不计决策耗时）+ 尾部由子代理样本贡献；直连快路径已反快。建议灰度期（R02-b）以生产形态 start 帧即时性+同口径探针双指标持续观察。
3. **复验轮 strong 模型 402 Insufficient Balance**：答案生成降级 fast（与 R20-b 基线轮同环境），语义抽检非门槛指标，双侧一致不受影响；复跑前若充值，语义数字可能变化（如实注明）。
4. eval_set32 双键 golden / C-R-EVAL 基线不受本批影响（未动检索底层，仅对齐图内调用参数）。
