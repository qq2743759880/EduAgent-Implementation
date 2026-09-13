# EduAgent 源码审计：AI 助手 / LangGraph / 记忆 / 技能资产域

- 审计日期：2026-09-13；审计方式：只读源码（无运行、无美化、无猜测），全部结论带 file:line 证据
- 后端根：`edu-agent/app/`；行号以当前工作区文件为准
- 总问题数：**23 条**（P0×2 / P1×5 / P2×11 / P3×5），亮点 5 条

---

## 一、AI 助手 / chat 实况架构图（带 file:line）

### 1.1 入口与两条互不相同的链路

```
POST /api/chat/stream（SSE，前端主路径）          POST /api/chat（非流式）
  router.py:245 chat_stream_sse                    router.py:218 chat_non_stream
        │                                                │
  service.py:517 chat_stream                       service.py:331 chat_answer
        │                                                │
  ┌─ run_agent_turn（flows/agent.py:218）──┐        ┌─ run_agent（ai/graph.py:775）─────────┐
  │  普通 Python 函数，非 LangGraph：        │        │ 真正的 9 节点 LangGraph 图：           │
  │  · decide_agent_plan(agent.py:73)       │        │  graph.py:606 build_graph             │
  │    - 规则路由优先(agent.py:91-97,        │        │  graph.py:662 StateGraph(AgentState)  │
  │      rule_router.py:63 正则)            │        │  START→route→skill→compact→           │
  │    - RULE_ROUTING_ENABLED=True 时       │        │  context_edit→plan→fan_out→merge→     │
  │      LLM 决策/tool_plan 不可达          │        │  reflect→answer→END                   │
  │  · retrieve_three_channel 检索          │        │  checkpointer=PlainRedisSaver         │
  │    (agent.py:242-251)                   │        │  (graph.py:761 compile)               │
  └─────────────────────────────────────────┘        └───────────────────────────────────────┘
        │                                                │
  与 MCP 并行：service.py:554 mcp_future           guard 防过载闸仅此路径：graph.py:790-817
   = run_chat_tool_calls（tool_calling.py:217        docs/tool_results 恒返回空：
     启发式正则选工具→mcp.executor.call_tool          graph.py:825-828
     tool_calling.py:265-271）                        记忆写：service.py:496-500 enqueue_turn
        │
  生成：generate_stream（generator.py:546）
   → _ChatClient.call_chat_stream_with_retry
     (generator.py:244，线程池 queue 桥接 569-603)
   失败→规则答案按 2 字符/10ms 假流式
   (generator.py:613-618)
        │
  SSE 事件：router.py:283-354
   start(286)→retrieval(291)→token(305, {"delta":delta})
   →done(350, data 内嵌 {code:0,message:"ok",data})
   →error(314, 可区分码 _map_stream_exception:89-129)
```

### 1.2 9 节点 LangGraph 图的真实拓扑（graph.py:606-694）

```
START → route ──chitchat──→ answer ──→ END
          │ (route_gate graph.py:255-260)
          └─ 其他意图 → skill(graph.py:201) → compact(graph.py:328)
                        → context_edit(graph.py:390) → plan(graph.py:301)
                        → fan_out(graph.py:493) → merge(graph.py:501)
                        → reflect(graph.py:513)
                        → (reflect_gate graph.py:518-524) sufficient=false 回 compact（≤MAX_REFLECT_ITERATIONS=2, config.py:200）
                        → answer → END
```

- 拓扑锁定 + 启动 fail-fast 自检：graph.py:565-600（EXPECTED_SIXNODE_NODES/EDGES 常量比对，不一致 RuntimeError）
- **六核心节点是薄壳，真实逻辑在 SixNodeHarness**（graph.py:250-537 薄壳委托 `_default_harness()`；sixnode.py:32-313 真实现）。HARNESS_IMPL=sixnode 可插拔（config.py:462，harness/base.py:21）
- LangGraph 要素核对：
  - StateGraph/条件边/add_messages reducer：真用（graph.py:31,662,684,692；AgentState graph.py:57-89）
  - checkpointer：真挂（graph.py:761 `compile(checkpointer=saver)`，PlainRedisSaver 见 §二）
  - 中断恢复（interrupt/human-in-loop）：**图内无 interrupt()**；HITL 状态机是独立模块 hitl_gate.py（四步 explain→propose→approve→execute，hitl_gate.py:16-20），不挂在 LangGraph 图上
  - 真实 LLM 编排行为被三层"跳过 LLM"优化大幅旁路：
    - route：规则路由 0-LLM（sixnode.py:67-77），LLM 路由仅 RULE_ROUTING_ENABLED=False 时可达
    - fan_out：knowledge 意图直连检索 0-子代理-LLM（sixnode.py:151-215，KNOWLEDGE_DIRECT_RETRIEVAL_ENABLED config.py:188）
    - reflect：摘要非空即跳过 judge LLM（sixnode.py:268-272）
    - 子代理 turn-1 确定性工具预执行（runner.py:315-352）

### 1.3 模型路由 fast/strong（双源）

- 档位选择：`_ChatClient._base_url/_headers/_model_name`（generator.py:175-198）：strong→`LLM_STRONG_BASE_URL/KEY`（DeepSeek），fast→`LLM_FAST_*`（火山 ark），缺省回退同源 `LLM_BASE_URL`
- 默认模型名：`LLM_MODEL_FAST="qwen-flash"` / `LLM_MODEL_STRONG="qwen-plus"`（config.py:164-165）
- 使用点：route/judge=fast（sixnode.py:90,279）、answer=strong 失败降 fast（sixnode.py:305-312）、子代理按 definitions.yaml model 字段（runner.py:63，learning=strong）、决策=fast（agent.py:116）
- 重试：按错误类型退避 + 模型错误 FAST↔STRONG 互切一次（generator.py:200-244，core/retry.py 分类）
- 流式：阻塞生成器→线程池 queue 桥接（generator.py:569-603），60s 无增量超时降级（596-598）

### 1.4 Prompt 组织（无模板文件，全部 Python 字符串常量）

- chat 提示词：`app/chat/prompts/__init__.py`（RAG_SYSTEM_PROMPT:15-32 / CHAT_SYSTEM_PROMPT:54-59 / FALLBACK_NO_DOCS:72 / HISTORY_TURN_TEMPLATE:86），`.format()` 注入
- 图内提示词：ROUTE_SYSTEM_PROMPT（graph.py:231-238）、REFLECT_SYSTEM_PROMPT（graph.py:509-510）、ANSWER_SYSTEM_PROMPT（graph.py:530-532）硬编码常量
- 子代理 system prompt：`subagents/definitions.yaml`（search/tool/learning/memory 四定义，含蒸馏指令）
- 前缀缓存优化：`ensure_min_prefix` 把静态前缀撑到 ≥2048 token（sixnode.py:41-55；runner.py:299-304）；决策前缀 deferred 模式只放 name+summary（agent.py:103，tool_specs）

### 1.5 上下文管理（历史裁剪/压缩）

- DB 历史窗口：`_history_window` 最近 N 轮（service.py:205-218）→ 仅用于生成器 prompt（stream 路径）
- 图内历史：LangGraph checkpoint 线程的 messages 累积（add_messages）
- 三梯队：context_edit（轻量删工具对保前缀，context_edit.py:26-33）→ compaction（>6000 token 压缩至 ≤6000 留最近 6 轮，compaction.py:747-846，config.py:209-211）→ 锚定闸门 ANCHOR_ROUND=3 闸门前字节零改动（compaction.py:377,765-770，config.py:261）
- compact 产物被下游真实消费：context_edit_node 以 compact 精简流为基底（graph.py:400-417），plan 把编辑后上下文注入子代理 input（sixnode.py:118-134）
- 记忆召回注入：fan_out 的 memory 子代理 / knowledge 直连路径 recall_topk→摘要并入 merged_context（sixnode.py:180-197；graph.py:460-472）

---

## 二、记忆 + checkpoint 实况

### 2.1 三层记忆（user_memory 域，位于 `app/ai/memory/`，非独立域）

| 层 | 实现 | 证据 |
|---|---|---|
| 事实源 | MySQL `user_memory_event` 事件溯源（append-only、valid_to 盖章、HEAD=唯一有效行），MEMORY_EVENT_ENABLED=True 默认 | event_persistence.py:11-25,47-60；persistence.py:213-216 工厂 |
| 向量召回 | MemoryVectorStore 降级链 milvus(BGE-M3 1024 维真实语义)→redis(HSET+ZSET)→in-memory；embedding 失败降级 char 2-gram 哈希并标 degraded_reason | vector.py:82-128（SemanticEmbedder）、169-215（降级链）、44-79（DeterministicEmbedder） |
| 写入路径 | 对话结束 enqueue_turn→纯规则 detect_memories（正则抽"记住X/纠正/目标/偏好"，importance≥4）→MemoryWriteQueue（Redis LPUSH `edu:mem_queue`，config.py:342）→后台消费者 store.write | ingest.py:23-102；service.py:116-131；queue.py:34-56 |

- 与 chat 结合：
  - 写：两路径结束时 `asyncio.create_task(enqueue_turn(user_id, query))`（service.py:496-500 非流式；683-688 流式）——**只喂用户 query，assistant 回复不入记忆**
  - 读：仅六节点图消费——fan_out memory 子代理 recall_topk top-3（sixnode.py:180-197）、learning 子代理 recall_profile（graph.py:474-484）。**流式主路径无任何记忆召回**
- 遗忘：run_forget 时间衰减软删 + 超容量淘汰最低分（store.py:143-186，score.py 评分）；Dream 巩固：LLM 4 阶段升维合并 + 分布式锁（dream.py:1-40，dream_lock）
- API：/api/memory/rewind、/history/{id}、/api/memory/admin/dream/run（memory/router.py:51-90，main.py:529 挂载）

### 2.2 checkpoint：`app/ai/checkpoint_redis.py` PlainRedisSaver

- 用途：原生 Redis（无 RediSearch）上复刻 InMemorySaver 语义 + 逐线程 pickle 快照落 Redis（`edu:ckpt:{thread_id}`，TTL 3600s，graph.py:709），实现 durable execution（kill 后同 thread_id 续跑不重复已完成节点，nodes_executed trace 随 checkpoint 持久化，graph.py:171-175）
- 调用方：唯一——graph.py:697-718 `_make_checkpointer()` → graph.py:761 编译挂载；Redis 不可用降级 None + `record_degraded("redis")` 指标
- 已加固点（属实）：
  - HMAC-SHA256 签名信封 + 恒定时间校验 + 不可信快照丢弃走重建（checkpoint_redis.py:30-40 设计、102-147 实现、208/232 开关读取）
  - thread_id 分片锁串行化读-改-写，防并发 100 resume 丢快照（150-175, 254-291）
  - 连接初始化全局锁防连接泄漏（178-195）

---

## 三、技能/资产调用实况（有真 skill 层，非虚设）

- **有独立 skill 框架**：`app/ai/skills/`（registry/trigger/loader/runtime/fork_exec/verify 六模块）
  - 注册表：扫描 `D:\.ai-hub\skills`（环境变量 AI_HUB_SKILLS_DIR 可覆盖）+ 项目 `.claude/skills` 下全部 SKILL.md，按目录索引，解析失败也计入（registry.py:21-24,47-80）
  - 触发三式（对齐 Claude Code）：`/skill-name` 手动（trigger.py:41-50）、paths glob 条件（54-78）、description Jaccard≥0.10 自动（82-108）；`disable-model-invocation` 不参加自动匹配（97）
  - 渐进式披露：description 清单常驻、body 按需 load_body（loader.py:39-56）
  - fork 执行：context:fork 委托 task92 run_subagent 独立上下文 + allowed-tools 轮次预授权门（fork_exec.py:13-33）
  - 接入对话决策链：graph.py:201-223 skill_node（route 后 plan 前），命中 body 注入 skill_context→plan 子代理 input（sixnode.py:114,126）与 answer prompt（sixnode.py:296-298）
  - 局限：纯启发式触发（decide 的 llm 参数无人注入，trigger.py:112-153）；触发结果**没有落任何 API/前端**——用户在 chat 里无法看到"命中了哪个技能"
- **资产调用 = MCP 工具**：`app/mcp/`（executor/registry/router/retry_loop/deferred 等 11 模块）。chat 侧真实调用点：
  - 六节点图 fan_out 的 call_tool 服务→`mcp_executor.call_tool_with_retry`（graph.py:447-458，换参→换工具→熔断闭环）
  - 流式 run_chat_tool_calls→`mcp_executor.call_tool`（tool_calling.py:265-271），但工具选择是**启发式正则**（只认 add/ping/echo/list_alphabet 类演示工具，tool_calling.py:97-189），MCP_TOOL_MAX_TRIES 默认 1 次（186-188）
- 其他"资产"调用：RAG 三通道检索（Milvus dense/sparse+BM25+图谱，retriever.py:1-11）作为 search_knowledge 工具被图与子代理复用；recommender/mindmap 是纯 MySQL/算法实现，不经 skill/MCP

---

## 四、其他 AI 功能一句话实况

| 功能 | 实况 | 证据 |
|---|---|---|
| recommender | 真实现：冷启动/协同过滤/图谱遍历三路加权融合（0.30/0.25/0.30/0.15）+ 反馈闭环，MySQL 无 LLM | engine.py:15-18 权重常量、_load_profile:52-70 |
| mindmap | 真实现：MySQL graph_node/graph_edge 生成 ECharts 风格导图（Neo4j 已被 MySQL 图替代），含掌握度状态映射 | builder.py:3-14,38 |
| progress | 真实现：视频打点批量去重聚合/作业考试提交/进度面板，纯 SQL 统计 | service.py:17-30 |
| quiz | **占位**：10 题 mock 题库 + 6 题型规则判分，解析为"模板 + RAG 占位" | quiz/service.py:6-9（"mock 题库/占位"自述） |
| vocab | 真实现（无 LLM）：分级词库 + SM-2 间隔重复 + daily 计划 + recall | vocab/service.py:3-5 |
| coding | 半实现：Piston HTTP 真实运行代码（3s 超时→mock 兜底），但 hint 是本地规则"生产可切 LLM" | coding/service.py:3（Piston）、394（hint 本地规则） |
| math | **占位**：自述"P5 math 占位 service：3 道内置题 + 规则校验 + 可选 LLM 回退" | math/service.py:2 |

---

## 五、交叉验证结论

1. **chat 工具调用接 MCP executor：是**。两条路（图内 call_tool_with_retry graph.py:452；流式 call_tool tool_calling.py:265），但流式的"何时调工具"由正则启发式决定，非 LLM。
2. **LangGraph 节点复用 RAG 检索：是**。search_knowledge 服务与 knowledge 直连快路径都调 `retrieve_three_channel`（graph.py:431-445；sixnode.py:161-165），与 /api/chat/search 同一实现（service.py:300-310）。
3. **流式主路径与 LangGraph 无关**（service.py:556-568 走 flows/agent.run_agent_turn 普通函数）——这是本次审计最重要的一处架构实况。

---

## 六、自曝问题清单（23 条）

### P0（2 条）

1. **记忆写队列消费者生产环境永不启动 → 三层记忆写入链路整体失效**。lifespan（main.py:66-205）从未调用 `start_memory_worker()`（memory/service.py:75，全仓无生产调用方）；而 queue.py:7 明文声称"由应用 lifespan 启动（service 门面）"。后果：chat 每轮 `enqueue_turn` LPUSH 进 `edu:mem_queue`（service.py:498,686；queue.py:47）后无人消费，user_memory 永不落库、recall_topk 恒空、Dream 自动调度与 HITL 过期扫描同样不启动（service.py:85-93 绑定在 start_memory_worker 内）。记忆系统仅测试环境（pump_once/显式 start）存活。严重度：P0。

2. **前端唯一主路径 /api/chat/stream 完全绕过 LangGraph，图的所有能力（checkpoint 续跑/子代理编排/HITL/记忆召回）对真实用户不生效**。流式走 run_agent_turn 普通函数（service.py:556-568）+ generate_stream（service.py:592-601）；9 节点图仅服务非流式 /api/chat（service.py:350-357）。宣传口径的 "LangGraph durable execution" 在主链路上是摆设。严重度：P0。

### P1（5 条）

3. **流式路径 LLM 工具决策是死代码**：`execute_tool_plan`（flows/agent.py:151）全仓无调用方；且默认 RULE_ROUTING_ENABLED=True（config.py:187）时 decide_agent_plan 直接 return、永不产出 tool_plan（agent.py:91-97）→ 流式工具调用全靠 tool_calling.py:97-189 的玩具正则（add/ping/echo/alphabet），LLM×MCP 决策链不可达。严重度：P1。

4. **防过载闸只护非流式路径**：guard.acquire/release 仅存在于 graph.run_agent（graph.py:790-817）；流式 chat_stream→generate_stream 无任何并发准入/排队（service.py:517-701 无 guard 引用）→ 主路径可无限并发直打 LLM，与 task26 防过载设计目标相悖。严重度：P1。

5. **非流式 API 永远丢失检索引用**：run_agent 返回硬编码空 `"docs": [], "graph_entities": [], "tool_results": []`（graph.py:825-828）→ chat_answer 组装的 RagAnswerResponse.docs 恒空（service.py:364-367）；检索结果只剩每行 120 字符的摘要（sixnode.py:167-171）并入 merged_context，引用溯源在 API 层断裂（旧版回退路径反而有完整 docs）。严重度：P1。

6. **flows/langgraph_agent.py 整文件死代码（500 行）**：无任何模块 import 它（全仓 grep 仅命中其自身）；模块导入即 `build_agent_graph().compile()`（langgraph_agent.py:446）。且文件内留有 `user_id` 硬编码兜底 1 的越权隐患写法（langgraph_agent.py:239,283 `int(state.get("user_id", 1) or 1)`），若日后被复用将违反"禁止兜底 user_id=1"安全红线。严重度：P1。

7. **pickle 反序列化信任面依赖单一布尔开关**：PlainRedisSaver 读路径 `pickle.loads`（checkpoint_redis.py:243）虽有 HMAC 信封加固（126-147），但 `CHECKPOINT_SIGN=False` 一键回退裸 pickle（config.py:226；checkpoint_redis.py:208-211,241-242=RCE 面复原）；且签名密钥缺省回退 JWT_SECRET、与鉴权密钥共享（checkpoint_redis.py:109-115，仅 WARN 一次）。严重度：P1。

### P2（11 条）

8. **无 session 的非流式请求共享 per-user checkpoint 线程**：`thread_id = session_id or f"task24-{user_id}"`（graph.py:785）→ 同用户所有匿名请求在一条 LangGraph 线程上用 add_messages 无限累积历史（跨请求上下文污染；仅 TTL 3600s 兜底，graph.py:709）。
9. **chat_answer 在 USE_AGENT_LOOP=False 时 UnboundLocalError**：`plan` 仅在 use_agent 分支内赋值（service.py:350-375），`if plan is None`（service.py:376）在 use_agent=False 时直接 NameError；chat_stream 版本有 `plan = None` 初始化（service.py:540），非流式版本漏了——配置门控后的潜伏崩溃。
10. **规则路由与 LLM 路由的设计意图相矛盾**：rule_router.classify_intent 返回 None 表达"未覆盖→LLM 兜底"（rule_router.py:63-78 docstring），但 sixnode.route 把 None 直接吞成默认 knowledge、不再走 LLM（sixnode.py:71）→ 默认配置下 LLM 意图路由彻底不可达，chitchat 误判为 knowledge 时会执行一次无意义检索。
11. **skill 触发无数量/长度上限**：description Jaccard 阈值低至 0.10（trigger.py:83），skill_node 对全部命中 skill 逐个 load_body 无 cap 注入（graph.py:216-222），再复制进每个子代理 input（sixnode.py:126）与 answer prompt（sixnode.py:298）→ 多命中长 SKILL.md 时上下文与 token 成本失控。
12. **skill 根路径硬编码 Windows 绝对路径**：`D:\.ai-hub\skills` 与 `E:\stu\project\stu\EduAgent实施手册\.claude\skills` 写死在源码（registry.py:22-24，后者无环境变量覆盖）→ Linux/容器部署后扫描静默为空（registry.py:57-58 skip），skill 层无告警地退化为恒空。
13. **记忆抽取纯模板正则、只吃 user query**：detect_memories 仅 4 组正则（ingest.py:23-46），importance<4 过滤（service.py:125-127）→ 非模板句式的记忆信号永不入库；enqueue_turn 只传 req.query（service.py:498,686），assistant 答案内容不参与记忆形成。
14. **merge 节点"去重"按 summary 前 40 字、无冲突标注**：`key = summary[:40]`（sixnode.py:249-251）前缀相同即误删；docstring 宣称的"冲突标注"实为纯文本拼接 `- [subagent] summary`（sixnode.py:252-253）。
15. **记忆 API 越层访问私有成员**：`store._persistence.fetch_entity(...)`（memory/router.py:44）绕过 MemoryStore 封装直接摸持久层，封装契约被 router 打穿。
16. **子代理 turns 计数的潜在 NameError**：`turns=min(turn + 1, spec.maxTurns)`（runner.py:415）中 `turn` 来自 for 循环变量（runner.py:354）；若 spec.maxTurns≤0（definitions.yaml 配置失误）循环体不执行，`turn` 未定义即引用。
17. **SSE start→retrieval 之间可静默 >10s**：retrieval 帧要等 `await mcp_future`（service.py:554,590）与检索完成后才发（router.py:291-299）；MCP/检索慢时用户在 start 后长时间无任何帧（无心跳/进度事件），TTFT 体验塌陷。
18. **LLM 失败后的"假流式"前最长白等 60s**：流式 60s 无增量才超时降级（generator.py:596-598），降级规则答案再按 2 字符/10ms 模拟流式吐出（generator.py:613-618）——最坏情况用户盯着空屏一分钟。
19. **图路径与非流式回退路径的历史语义不一致**：图路径历史来自 checkpoint 线程累积（AgentState messages），回退路径来自 DB `_history_window`（service.py:345-347→generator history_turns）——同一会话在两条路径下 LLM 看到的上下文不同源。

### P3（4 条）

20. **reflect 回边导致 nodes_executed trace 重复失真**：reflect_gate=false 回 compact（graph.py:692），_record 再追加一轮 "compact/context_edit/plan/..."（graph.py:171-175），checkpoint 内节点 trace 与真实执行轮次混叠，durable "不重复执行" 验证口径被污染。
21. **quiz/math 为占位实现却挂在正式路由前缀下**（main.py:495-501；quiz/service.py:6-9 自述 mock；math/service.py:2 自述占位），前端可正常调用拿到 mock 数据，无"演示数据"标识字段。
22. **skill registry 每请求全量 O(N) 触发匹配无缓存**：get_skill_registry 缓存了扫描（graph.py:184-189），但 skill_node 每请求对全部 skills 跑 tokenize+Jaccard（graph.py:216→trigger.py:82-108），124+ skills 时属可测但无谓的每请求开销。
23. **两套 chat 决策/路由逻辑并行漂移**：六节点图（sixnode.route 规则路由）与流式 decide_agent_plan（agent.py:91-97 规则决策）各自维护一份意图规则调用，SSE 与非流式对同一 query 可能给出不同 intent/need_search 判定，行为不一致无契约约束。

---

## 七、亮点清单（5 条，带证据）

1. **PlainRedisSaver 的并发与供应链加固是真功夫**：thread_id 分片锁把「super().aput()+落盘」整段串行化防旧快照覆盖（checkpoint_redis.py:276-291）、连接初始化全局锁防泄漏（178-195）、HMAC 信封恒定时间校验+不可信快照丢弃重建+回滚开关三件套（102-147）。
2. **SSE 两段式错误模型完整可区分**：建连前同步 HTTP、建连后 `event:error` 且错误码按超时/401/429/5xx/连接类精细映射（router.py:89-129），落库失败发 CHAT_PERSIST_FAIL 并补带 degraded 的 done 收束不静默（router.py:320-347）；token 字段 `{"delta": delta}` 与前端契约（AGENTS.md 实测口径）一致。
3. **上下文管理三梯队真实闭环**：context_edit 轻量删工具对保前缀签名（context_edit.py:26-33）→ compaction 重量压缩 ≤6000 留 6 轮（compaction.py:747-846）→ ANCHOR_ROUND 锚定闸门冻结区保护 prompt cache（compaction.py:377,765-770）；且压缩产物被 plan 节点真实消费注入子代理（sixnode.py:118-134），非观测摆设。
4. **子代理上下文隔离 + artifact 蒸馏符合 Anthropic sub-agent 范式**：每个子代理独立 messages/system/工具白名单/maxTurns，崩溃重试只动本地循环（runner.py:267-418）；完整工具原文落 Redis artifact（TTL 1h）只回 ≤2000 token 摘要（runner.py:382-407），>1500 token 工具输出走 distill 一行结论（runner.py:385-392）。
5. **记忆事件溯源模型设计完整**：append-only + valid_to 盖章 + 单 HEAD 不变量 + 检索强制过滤废弃版本（event_persistence.py:11-25；store.py:97-100），rewind/consolidate 向向量库同步增删（store.py:199-266），trace_id 全事件审计。

---

## 八、判定结论

- **「LangGraph 真实度」一句话判定**：**"图是真图、用是半用"——9 节点 StateGraph + 条件边 + Redis checkpointer + 拓扑 fail-fast 是货真价实的 LangGraph 工程化（非套壳），但默认配置下规则路由/直连快路径/启发式 judge 三层旁路使其多数请求只跑 1 次 LLM，且前端唯一的流式主路径压根不经过这张图**。
- TOP5 严重问题：
  1. P0 记忆写队列无消费者，记忆写入生产整体失效（main.py:66-205 vs memory/service.py:75）
  2. P0 流式主路径绕过 LangGraph，图能力对真实用户不生效（service.py:556-568）
  3. P1 流式 LLM 工具决策死代码，工具调用靠玩具正则（agent.py:91-97,151；tool_calling.py:97-189）
  4. P1 防过载闸不护流式主路径（graph.py:790-817 vs service.py:517-701）
  5. P1 非流式响应检索引用恒空 + flows/langgraph_agent.py 500 行死代码残留越权写法（graph.py:825-828；langgraph_agent.py:239,283,446）
