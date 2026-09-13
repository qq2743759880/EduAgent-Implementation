# KB 深读①：编排与多智能体（vault② 13 卡精读报告）

> 精读对象：E:\stu\project\Obsidian\agent架构（vault②），已先读该库根 AGENTS.md（v1.4，铁律：溯源必带/置信度三级/禁编造）。
> 卡片清单：F-C01-001~003、F-C02-001~007、M-004、M-005、P-001，共 13 张，逐卡一节。
> 外链实读记录：Anthropic《Building Effective Agents》（WebFetch 成功）；12-factor-agents README + Factor 8（GitHub 直连被拒 ECONNRESET/ECONNREFUSED，经代理 127.0.0.1:7897 curl 成功）；generative_agents retrieve.py/reflect.py/cognitive_modules 目录（代理 curl 成功，含公式级核验）；agbench README、camel benchmarks/gaia.py（HTTP 200 复核）；AutoGen README "Maintenance Mode"（行 14-21 实证）；crewai testing 文档（HTTP 307 跳转可达）。DeepWiki 对照页未重读（各卡内已含 HTTP 200 实测记录，见各卡"对照验证"节）。
> EDU = EduAgent（FastAPI 8000 + LangGraph 9 节点图 + Milvus RAG + MCP 工具 + chat SSE `POST /api/chat/stream`）。

---

## 1. F-C01-001-langchain

**核心定位**：通用 LLM 应用编排框架，"一切皆 Runnable"（LCEL `|` 管道）+ v1 Agent middleware 架构，145k★。

**机制细节**（卡内 file:line 引用）：
- LCEL Runnable 协议：`libs/core/langchain_core/runnables/base.py`（5718 行，最大文件），Runnable/RunnableSequence/RunnableParallel/RunnableLambda/RunnableBranch，六种执行方式 invoke/batch/stream/ainvoke/abatch/astream。
- v1 Agent middleware：`libs/langchain_v1/langchain/agents/factory.py`（84KB create_agent 工厂）+ `middleware/` 10+ 中间件（context_editing / human_in_the_loop / model_call_limit / model_fallback / model_retry / pii / shell_tool / provider_tool_search），另有 `_subagent_transformer.py`（子 Agent 转换）。
- classic AgentExecutor：`langchain_classic/agents/agent.py`（1569 行）单体 ReAct 循环，与 v1 并存（迁移期 API 不稳定）。
- 容错四层：`runnables/retry.py`（324 行，RunnableRetry 指数退避）+ `runnables/fallbacks.py`（597 行，with_fallbacks 降级链）+ timeout config + v1 rate_limiters。
- 状态管理弱项：无 checkpoint、无显式状态（arch-checkpoint 域简评"无独立检查点机制"），上下文靠 MessagesPlaceholder 运行时注入。

**卡内链接内容摘要**：
- 卡内全部为 repo 锚点（pinned commit e670c7a03b），本地 clone 精读；DeepWiki 对照页 HTTP 200、725KB，结论一致（卡内已验证，本次未重读）。
- 30 天复扫标注：HEAD 漂移至 d5d7cc56ab，star 146113，L1 微漂移。

**评估与可观测**：callbacks/ + tracers/（LangChainTracer 发 LangSmith）+ classic evaluation/（QAEvalChain/TrajectoryEvalChain，v1 迁移中）；平台级评估依赖 LangSmith（独立 SaaS）。卡内明确"调试困难（管道组合后错误定位难）"为缺点。

**对 EDU 的可执行判据**：
1. 重试/降级/限流必须做成 LangGraph 节点外的横切层（middleware 思想），禁止把 model_retry/fallback 逻辑写进 9 节点业务代码——LLM 调用统一走"带指数退避 + with_fallbacks 备用模型 + 超时"的调用封装。
2. EDU 的 deepseek 主模型 + strong 备模型（402 余额不足场景）正是 model_fallback 降级链模式：fallback 触发必须产出观测事件（次数/原因），接入 OTLP。
3. 面向学生数据的节点出口加 PII 过滤中间件（pii middleware 同构），学生个人信息不得原样进入 LLM 请求体。
4. 引入模型前先在 model-profiles 式配置表登记上下文窗口/能力，切模型只改 provider 配置不改图代码。
5. 记住其"管道调试难"教训：EDU 每个 LangGraph 节点的输入输出摘要必须落 trace（对应 LangSmith 的职责），验收时用 trace 断言而非只看最终回答。

---

## 2. F-C01-002-langgraph

**核心定位**：状态图编排引擎——StateGraph 显式节点/边/条件边 + Pregel 超步执行 + Checkpoint 时间旅行，41k★，EDU 当前编排层同款。

**机制细节**：
- StateGraph：`libs/langgraph/langgraph/graph/state.py`（1692 行），TypedDict/Pydantic 状态 schema，add_node/add_edge/add_conditional_edges；条件边在 `graph/_branch.py`（210 行）；MessageGraph `graph/message.py`（369 行）。
- 执行引擎：`pregel/main.py`（3972 行）+ `_algo.py`（1351 行），超步并行、超步间检查点屏障；远程执行 `pregel/remote.py`（1187 行，LangGraph Platform）。
- 状态管理：10 种 Channels（LastValue 最新值覆盖 / Binop 累加 / Topic 发布订阅 / EphemeralValue 超步后清除 / NamedBarrierValue / UntrackedValue 等），节点返回部分更新字典，由 Channel 语义合并。
- Checkpoint：独立 4 包（checkpoint / checkpoint-sqlite / checkpoint-postgres / checkpoint-conformance），`BaseCheckpointSaver.put/get/list`，thread_id 会话隔离 + checkpoint_id 时间旅行 + `interrupt()` 中断恢复（`pregel/_checkpoint.py` 291 行）；卡内标注"interrupt 具体实现待精读"、"libs/prebuilt 目录空，create_react_agent 位置 UNVERIFIED"。
- 流模式 4 种：values/updates/debug/messages（token 级流式走 messages）。

**卡内链接内容摘要**：repo 锚点（pinned 81bf17b231）+ DeepWiki HTTP 200 对照一致；本次补查未发现卡外新链接。30 天复扫：HEAD 漂移至 e539ac122f，star 41452。

**评估与可观测**：debug 流模式（`pregel/debug.py` 265 行）+ 图可视化（`_draw.py` 278 行 Mermaid）+ checkpoint 元数据含执行追踪；无独立评估框架（依赖 LangSmith 或自定义节点）。

**对 EDU 的可执行判据**：
1. Checkpointer 必须上生产后端（PostgresSaver 或等价 MySQL 自适配），开发环境才允许 MemorySaver——EDU 聊天会话要 thread_id=会话 ID 隔离 + 断线续跑，这是 LangGraph 的核心差异化，不用等于白选。
2. 9 节点图的列表型状态字段（如检索文档列表、消息历史）必须显式声明 `Annotated[list, operator.add]`（Binop 通道），否则默认 LastValue 覆盖会静默丢数据——验收时构造两轮检索断言列表累加。
3. 危险 MCP 工具执行前用 `interrupt()` 暂停等人工确认（对应 admin 审核场景），恢复走 `invoke(None, config={"thread_id":...})`；interrupt 路径要有契约测试。
4. 路由函数集中收口（对齐 `_branch.py` 的做法），每个条件边可独立单测；禁止在节点内部 if-else 散写跳转。
5. 验收补充 updates/debug 流模式断言：EDU 的 SSE 只暴露 token（messages 模式），内部测试应断言每超步的节点级 updates，用于定位"哪个节点退化"。
6. 利用 `get_graph().draw_mermaid()` 把 9 节点图固化进文档，图结构变更时 diff 可见。

---

## 3. F-C01-003-eino

**核心定位**：字节 CloudWeGo 的 Go 生态 LLM 框架，三层架构 Components+ADK+Composition，主仓接口与 eino-ext 实现分离，12.9k★。

**机制细节**：
- 三层：Components（7 大组件接口 document/embedding/indexer/model/prompt/retriever/tool，主仓空实现）+ ADK（`adk/`：agent_tool.go / callback.go / call_option.go / cancel.go）+ Composition（`compose/`：chain.go / branch.go / chain_branch.go / chain_parallel.go / dag.go / checkpoint.go / agentic_tools_node.go / component_to_graph_node.go）。
- 编排模型：Chain 线性 / Branch 条件 / Parallel 并行 / DAG 通用有向无环图，组件可互转图节点，工作流可整体暴露为 agent 的 Tool（README："exposed as tools for agents"）。
- 容错：`compose/checkpoint.go` 持久化恢复 + `checkpoint_migrate_test.go`（检查点格式迁移测试）+ `adk/cancel.go` 四种取消测试（cancel_edge / cancel_multicall / cancel_recursive / cancel_stream_race）+ Go 惯例错误返回。
- Agent 模式：`flow/agent/react/`（ReAct）+ `flow/agent/multiagent/host/`（Multi-Agent Host）；Runner 事件流 `runner.Query(ctx,prompt)` 返回事件迭代器 `iter.Next()`。
- 对照验证：DeepWiki 404（Tier3），人工抽验 4/4 claim 对本地 clone 全中（README.md L17/L20-22、go.mod L1）。

**卡内链接内容摘要**：全部为 cloudwego/eino 锚点（pinned 9d983b36），本地 clone E:/stu/tools/eino 已 go mod download 验证 importable；无外部文章链接。

**评估与可观测**：无独立 eval 框架（主仓无 evals/）；可观测靠 adk/callback.go 回调钩子对接外部监控（OTel/Prometheus 需自接）；checkpoint_test/checkpoint_migrate_test 是机验资产。

**对 EDU 的可执行判据**：
1. 借鉴"检查点带版本 + 迁移测试"：EDU 的会话/checkpoint 序列化格式必须带版本号字段，格式演进时跑迁移测试（对齐 checkpoint_migrate_test），否则升级即毁存量会话。
2. SSE 断连取消测试按 eino 四场景对齐：边界取消 / 多调用取消 / 递归（子代理）取消 / 流式竞态取消——EDU 的 chat SSE 目前只测了正常流，断连取消是验收盲区。
3. "组件可暴露为 Tool"模式：EDU 的 Milvus 检索节点应同时注册为 MCP tool（admin-rag 已有雏形），一套实现两个入口，验收时两边契约都要测。
4. EDU 全 Python 栈，Eino 本身禁止引入（无 Go 微服务场景，M-004 结论同）。

---

## 4. F-C02-001-autogen

**核心定位**：微软多智能体对话框架——6 种 Agent 类型 + 3 种团队编排 + 5 种上下文策略 + 终止条件机制 + Magentic-One 编排器，60.8k★，**已进官方 Maintenance Mode**。

**机制细节**：
- 三层团队编排：Agent 层（`_assistant_agent.py` 1429 行 / `_code_executor_agent.py` 725 行 / `_user_proxy_agent.py` 198 行人工代理 / `_society_of_mind_agent.py` 250 行内部子团队 / `_message_filter_agent.py` 160 行消息过滤）→ 团队层（`teams/_group_chat/` RoundRobin / Selector（LLM 决定发言者）/ Swarm 控制权转移）→ 编排器层（`autogen-ext/agents/magentic_one/` Orchestrator 任务分解+调度+聚合）。
- 上下文：`autogen-core/model_context/` 5 策略——Buffered / 基础 / HeadAndTail（保头尾弃中段）/ **TokenLimited（默认，按模型窗口动态截断）** / Unbounded。
- 终止条件：`conditions/_terminations.py`——TextMention / MaxMessage / TokenUsage / Timeout，可 AND/OR 组合，`team.run()` 每轮检查。
- 通信：消息列表 + TeamResult（messages 全历史 / termination_reason / cost token 统计）；无 checkpoint（会话持久化需用户自存 messages）。
- 安全：DockerCodeExecutor 容器沙箱（推荐）/ Local / Jupyter；_security 密钥掩码；auth 认证模块。

**卡内链接内容摘要**：
- 更新记录实测（2026-09-10）：README 明示 "AutoGen is now in maintenance mode…New users should start with Microsoft Agent Framework"，迁移指南 learn.microsoft.com/agent-framework/migration-guide/from-autogen/。**本次代理 curl 独立复核成功**：README 行 14 有 Maintenance Mode 徽章、行 19-21 原文一致——卡内 claim 实证为真。
- agbench 基准包 URL 本次复核 HTTP 200。

**评估与可观测**：agbench（受控初始条件下反复运行预定义任务，Docker 依赖）是 C02 少数原生 eval harness；_telemetry 模块 + TeamResult cost；多 Agent 消息流调试困难是卡内明示缺点。

**对 EDU 的可执行判据**：
1. **终止条件四件套是硬门槛**：EDU 任何多步循环（批改 agent、RAG 重试、未来多 agent）必须同时具备"完成判据文本 + 最大消息/迭代数 + token 上限 + 超时"四类终止，缺一不收——这是防无限烧钱的结构性保证（P-001 亦背书）。
2. 上下文默认策略取 TokenLimited 同构：按模型窗口动态截断（结合 model-profiles 登记的窗口值），长对话 HeadAndTail 保系统提示+最近轮次。
3. 禁止引入 autogen 做新组件（Maintenance Mode 已实证）；如需多 agent 对话概念参考，读代码不动依赖。
4. 会话级 cost 统计学 TeamResult：EDU 每次会话记录 token 消耗与终止原因入库，验收报告必须带成本字段。
5. LLM 生成代码一律 Docker 沙箱执行，禁本地直跑。

---

## 5. F-C02-002-hermes-agent

**核心定位**：Nous Research 的自改进单助手 agent——唯一内置 closed learning loop（技能自创建/自改进/知识持久化/历史搜索/用户建模），多平台 gateway + 七沙箱后端，243k★（C02 最高）。

**机制细节**：
- 编排：单 agent 事件驱动工具循环（`hermes_cli/main.py` 入口 + `agent/agent_init.py` 生命周期 + `agent/agent_runtime_helpers.py` 工具调度）+ 隔离子代理并行 + RPC 脚本"把多步管线折叠为零上下文消耗的单轮" + cron 定时 + 多平台 gateway 单进程（Telegram/Discord/Slack/WhatsApp/Signal/CLI，跨平台会话连续）。
- 上下文四层：FTS5 会话全文搜索 + LLM 摘要跨会话召回 / Honcho 辩证用户建模 / 技能库自 enrich / 工具集 lazy 装载（`tools/lazy_deps.py`）。
- 会话：SQLite 持久化 + `--resume/--continue` 恢复 + `agent/activity_tracking.py` 活动追踪。
- 安全：审批三件套（`approvals_suggest.py` / `approval_mode.py` / `approval_transport.py`）+ `--safe-mode` 限制危险操作 + `--yolo` 显式跳过 + 七后端（local/Docker/SSH/Singularity/Modal/Daytona/Vercel）+ 凭证不暴露给 LLM/日志 + **pyproject.toml 全部直接依赖 ==X.Y.Z exact-pinned**（Mini Shai-Hulud 蠕虫后收紧）。
- 对照验证：DeepWiki 404，人工抽验 3/3 对本地 clone 全中。

**卡内链接内容摘要**：repo 锚点（pinned ee84ccd8）+ pyproject.toml:19（exact-pinned 实锚）；无外部文章。本次未重读其外链。

**评估与可观测**：activity_tracking + `hermes insights/monitoring/logs` + `hermes doctor/verify` 健康检查；无独立评估基准（卡内 arch-evals 标"待确认"）。

**对 EDU 的可执行判据**：
1. EDU requirements 依赖改 exact-pinned（==X.Y.Z）并提交锁文件——供应链防投毒，hermes 的教训已现实发生过。
2. MCP 工具调用分三级权限：默认审批（教师确认）/ safe-mode（只读降级）/ 自动（白名单内），映射到 EDU 的 admin 守卫三段。
3. 学习会话历史建全文索引 + LLM 摘要（FTS5 同构，EDU 可用 MySQL fulltext 或 ES）：学生/教师能搜"上次类似问题怎么讲的"，而非只看最近 N 轮。
4. 多步教学管线（如出卷：抽知识点→生成→校验）封装为"RPC 式单轮脚本"降低上下文消耗——多步折叠是一等公民模式，不是补丁。
5. 启动自愈（early venv self-heal）思想：EDU 后端启动时自检依赖/向量库连接，失败时给出可恢复指引而非裸栈。

---

## 6. F-C02-003-metagpt

**核心定位**：角色驱动多智能体"软件公司"框架——16 个 Role 类 + 43 个 Action + Environment 消息总线，把人类 SOP 编码进协作流程，70.3k★，**开源停滞（约 8 个月无推送）**。

**机制细节**：
- 编排：角色绑定 Action 集合（`metagpt/roles/` 16 文件实测），SOP 流水线 需求→PRD→架构→任务拆解→编码→测试；Environment 类（2 文件）共享消息总线，发布/订阅路由。
- 通信协议：Message 类带 `role/content/cause_by/send_to` 四字段——**cause_by 记录消息由哪个 Action 触发，实现执行链路可追溯**（arch-aci/arch-observability 双域引用）。
- 记忆：`metagpt/memory/` 短期对话历史 + LongTermMemory 向量检索；角色记忆隔离、经 Environment 选择性共享。
- 容错：Action 层 max_retry 重试 + provider 层 fallback 备用模型 + QAEngineer→Engineer 自动修复回路。
- 检查点：项目产出物（PRD/设计/代码）落文件系统支持恢复。

**卡内链接内容摘要**：repo 锚点（pinned 11cdf466）+ DeepWiki HTTP 200 对照一致（补充 v0.8 Data Interpreter）。更新记录实测：pushed_at=2026-01-21，docs.metagpt.io 双通道复测 HTTP=000 不可达，2 个 CVE 未修复（CVE-2026-19060/CVE-2026-5972），无官方维护宣告（M-005 中标 INFERRED）。

**评估与可观测**：cause_by 链路追溯 + exp_pool/ 实验池 A/B + management/ 任务进度跟踪；无独立 eval 框架（M-005 判：论文用 HumanEval/MBPP，非内置 CLI，"工具冻结"）。

**对 EDU 的可执行判据**：
1. 消息/中间产物必带 `cause_by` 式溯源字段：EDU 的 SSE 事件、trace span、会话消息都记录"由哪个节点/动作产生"，事后能重建执行链（对齐现有 event: start|retrieval|token|done|error 协议）。
2. 禁止引入 MetaGPT 依赖（停滞+CVE 未修）；其 SOP 思想可用于"教学内容生成流水线"：大纲(计划)→讲义(执行)→习题(执行)→质检(评审)的角色-动作分离建模。
3. Action 级 max_retry 配置化：每个 LLM 动作的重试次数是配置不是硬编码。
4. 产出物即检查点：批改报告/生成课件等中间产物实时落盘，崩溃后从产物恢复而非重跑全流程。

---

## 7. F-C02-004-chatdev

**核心定位**：聊天驱动的虚拟软件公司——Chat Chain 阶段链式编排（需求→设计→编码→测试→文档），YAML 可配置阶段增删重排，34.2k★。

**机制细节**：
- 编排：`workflow/` 执行引擎（阶段调度/角色配对/消息路由/产出物收集）+ `entity/graph_config.py` Chat Chain 图配置；每阶段由固定角色对对话完成，比 MetaGPT 更轻量。
- 上下文：Phase 级独立对话历史，**Phase 切换时摘要压缩传递关键信息**（`entity/messages.py`）+ 自动截断。
- 通信：消息对象 role/content/phase/metadata；`entity/tool_spec.py` 工具调用规范（名称/描述/参数 schema，函数调用接口）。
- 会话/检查点：Chat Chain 执行状态落文件系统，支持阶段级恢复；`server/` REST API 远程会话管理 + 异步任务。
- 容错：Phase 失败**回滚到上一阶段** + Programmer↔Tester 反馈循环自动修复。

**卡内链接内容摘要**：repo 锚点（pinned 4fb2db0）+ DeepWiki HTTP 200 一致（补充 Communicative Agents 论文背景，卡内标注"论文与代码对应关系待精读"）。

**评估与可观测**：server/ 状态查询 + frontend/ 进度展示 + Phase 级执行日志；check/ 代码质量检查；无独立 eval 框架（M-005 判：论文有 executability 1-4 量表，非内置 CLI）。

**对 EDU 的可执行判据**：
1. 教学流程编排外置 YAML/配置驱动（Chat Chain 模式）：9 节点图的节点顺序、提示词版本、阶段开关不放死在代码里，改流程不发版。
2. 节点间传递用"摘要压缩"策略：前一节点产物过长时先摘要再入下一节点 prompt（Phase 间摘要传递同构），防 9 节点链上下文线性膨胀。
3. 阶段级回滚：RAG 生成链失败时回滚到上一稳定节点产物，而非整图重跑（省 token、P95 友好）。
4. 工具 schema 独立成 spec 文件（tool_spec 同构）：EDU 的 MCP 工具定义与实现分离，便于契约测试。

---

## 8. F-C02-005-generative-agents

**核心定位**：斯坦福小镇社会模拟鼻祖（UIST 2023 Best Paper）——25 个 agent 的三层认知架构（记忆流+反思+计划），22.1k★，**学术停滞（约 2 年无推送）**。

**机制细节**：
- 编排：时间 tick 驱动（`reverie/backend_server/reverie.py`），每 tick 所有 agent 并行"感知→记忆→反思→计划→行动"；maze.py 地图 + path_finder.py A* 寻路。
- 记忆流：所有经历按时间排序，每条带创建时间/最近访问/重要性评分（1-10，LLM 评 poignancy）。
- **检索公式（本次代理 curl 源码实证，retrieve.py）**：recency = `recency_decay ** i`（按时间序指数衰减，145 行）；三项各自归一化到 [0,1]（232-236 行）；总分 = `recency_w*recency*gw[0] + relevance_w*relevance*gw[1] + importance_w*importance*gw[2]`（247-249 行，relevance 为 cos_sim，194 行）；排序取 top-k（128 行 `reverse=True)[:x]`）。
- **反思触发（reflect.py 实证）**：`reflection_trigger()` = 累计重要性计数 `importance_trigger_curr <= 0` 且有事件/思绪时触发，反思后重置为 `importance_trigger_max`——即"重要性累积过阈值就反思提炼高层洞察"。
- 计划：日计划（粗粒度时间块）递归分解为行动序列，环境变化时动态重排；计划本身写入记忆流成为后续上下文。

**卡内链接内容摘要**：repo 锚点（pinned fe05a71）+ 论文《Generative Agents: Interactive Simulacra of Human Behavior》；DeepWiki HTTP 200 一致。本次新增实读：retrieve.py（284 行全文核验公式）、reflect.py（触发函数）、cognitive_modules 目录清单（converse/execute/perceive/plan/reflect/retrieve 六模块）。

**评估与可观测**：论文级评估——控制实验（有/无反思/计划对比）+ 100 人 believability 人类评估 + 端到端社会传播任务；前端 Phaser.js 可实时观察 agent 记忆/计划/反思；无内置 eval CLI。

**对 EDU 的可执行判据**：
1. **Milvus RAG 排序不能只有 cos 相似度**：对齐三因子公式，检索分数 = w1*cos 相似度 + w2*时间衰减(指数) + w3*内容重要性（教材标注/使用频次），权重可配置——这是本轮精读中唯一拿到公式级实证的记忆机制，直接可抄。
2. 学习画像更新用"重要性累计阈值触发反思"：学生错题/薄弱点累计到阈值才触发一次画像重 summarization，而非每次会话都重算（省 LLM 调用）。
3. 计划写入记忆流：给学生生成的学习计划本身作为可检索上下文，后续辅导能引用"你上周的计划"。
4. 只借鉴思想，禁止引入其依赖（2 年停滞、研究级代码质量）。

---

## 9. F-C02-006-camel

**核心定位**：双 Agent 角色扮演协作框架——Inception Prompting 引导 AI User/AI Assistant 自主对话，societies/ 扩展大规模社会模拟，17.7k★。

**机制细节**：
- 编排：双角色对话循环（AI User 提需求反馈=计划侧，AI Assistant 执行=执行侧），系统提示词结构化注入角色（role description/task/constraints）；`camel/societies/`（2 文件）社会模拟。
- LLM 抽象：`camel/models/` 59 文件最大子目录，统一 Model 接口（chat/embed/stream）+ 模型路由和 fallback。
- 记忆：`camel/memories/` 5 文件——ChatHistory / LongTermMemory（向量检索）/ MemoryRetriever，agent 间记忆隔离。
- 容错：models/ 层 fallback + `caches/` 语义缓存+精确缓存（减少失败影响与成本）+ 模拟 agent 故障重初始化。
- 通信：消息对象 role/content/metadata，`environments/` 管理 TaskEnvironment/SocietyEnvironment 的注册、路由、状态同步。

**卡内链接内容摘要**：repo 锚点（pinned 8c791b7）+ DeepWiki HTTP 200 一致（补充 CAMEL 论文背景与 v0.2.x Society 演进；"Inception Prompting 技术细节待精读"为卡内待补）。本次复核 camel/benchmarks/gaia.py HTTP 200。

**评估与可观测**：**camel/benchmarks/ 内置基准模块**（gaia.py/apibank.py/nexus.py/ragbench.py/browsecomp_*，examples/benchmarks/ 有运行入口）——C02 中少有的框架内置 eval；profiling/ + caches 统计 + data_collectors/ 对话数据收集。

**对 EDU 的可执行判据**：
1. 角色 prompt 结构化三段式（role description / task / constraints）固化到 EDU 的教学 agent 提示词模板规范，模板入库可 diff。
2. 建 LLM 语义缓存层（camel caches 同构；EDU 已有 task39 缓存实证 322.6ms→5.3ms，扩展到语义级缓存命中"换说法同问题"）。
3. 学 camel 建 `benchmarks/` 目录：RAG 检索质量、批改准确率的评测脚本随仓入库可重跑（对应 test-reports 可重跑纪律）。
4. 双 agent 裸对话模式工具能力弱（M-005 判），不作为 EDU 执行侧方案。

---

## 10. F-C02-007-crewAI

**核心定位**：角色驱动+流程编排的多智能体框架——Crew(团队)+Agent(role/goal/backstory)+Task(expected_output)+Process(sequential/hierarchical)+Flow(DAG)，58.4k★，高活跃（日更级）。

**机制细节**：
- 三层编排：Crew 核心（`lib/crewai/src/crewai/crew.py` 2490 行，调度 Agent 完成 Task，支持顺序与 manager 层级分配）+ Flow 运行时（`flow/runtime/__init__.py` 4015 行，DAG：条件/循环/并行/子流程，可视化 interactive.js 2513 行）+ Agent 执行器（`experimental/agent_executor.py` 3361 行，ReAct 循环）。
- 上下文三层：Agent 记忆（`agent/core.py` 2155 行，短期对话+长期持久化，可跨 agent 共享）+ Task 上下文（description/expected_output/context 注入提示词，结果传递）+ Crew 共享状态。
- 主类复核：候选池原列 C01，按决策树⑨复核改 C02（对话驱动 vs 流程驱动是它和 autogen 的分型轴）。
- 通信：无独立消息总线——靠 Task 输出传递 + Crew 共享状态。
- 安全：工具沙箱（代码执行工具 Docker 隔离）+ 密钥环境变量管理不暴露给 agent 上下文。

**卡内链接内容摘要**：repo 锚点（pinned a53ecc17）+ DeepWiki HTTP 200；`crewai test` CLI 官方文档 docs.crewai.com/en/concepts/testing.md（卡内 curl HTTP 200；本次复核 307 跳转可达）。

**评估与可观测**：**官方内置评测命令 `crewai test -n 5 -m gpt-4o`**：多次迭代运行 Crew，输出任务完成率/token/延迟指标表——C02 最易用的原生 eval harness；Task expected_output 可程序化验证输出；Flow 可视化。

**对 EDU 的可执行判据**：
1. **每个 LangGraph 节点定义 expected_output（可程序化断言的期望输出契约）**——crewAI 的 Task 三件套思想：EDU 9 节点各节点输出应有 schema+验收断言，不是"看着像就行"。
2. 提供一键评测命令（对标 `crewai test`）：EDU 应有 `python scripts/eval_chat.py -n 5` 之类的多轮评测入口，输出完成率/token/延迟表，接进验收报告。
3. role/goal/backstory 三元组用于教学 agent 人设（讲师/助教/出题官）提示词模板规范化。
4. crewAI 本身不引入：EDU 已有 LangGraph，Crew+Flow 双范式只增学习成本（卡内缺点原话"Flow 与 Crew 双范式学习成本"）。
5. hierarchical 模式的 manager 开销警示：若未来 EDU 上多 agent，必须有明确的"谁分派"成本预算，默认顺序流程。

---

## 11. M-004-c01-orchestration-matrix

**核心定位**：C01 三框架横评（langchain vs langgraph vs eino）——9 维×3 列矩阵，全部 EXTRACTED 回溯三张 F 卡，解决"通用编排框架怎么选"。

**机制细节**（矩阵格结论）：
- 图编排形态谱系：LCEL 管道（隐式、无循环）→ StateGraph 状态图（显式、循环+持久化）→ eino Composition 五模式（Chain/Branch/Parallel/DAG/Checkpoint）。
- 状态管理三态：langchain 无显式状态（包装器传递）；langgraph 10 种 Channels 显式语义；eino context.Context 贯穿 + checkpoint.go。
- 容错对照：langchain=RunnableRetry+fallbacks 装饰器层；langgraph=引擎内重试+checkpoint 故障恢复；eino=cancel.go 四场景+checkpoint 迁移。
- 数据口径纪律：EXTRACTED 才入格；厂商数字 UNVERIFIED 禁入正文；本矩阵无独立实验。

**卡内链接内容摘要**：纯回溯 F-C01 三卡（溯源节逐卡列 file:line）；无外部新链接。

**评估与可观测**："评估维度"行指出：langgraph 有 checkpoint-conformance 一致性测试套件（后端实现的机验资产）、图可视化调试；langchain v1 迁移中评估模块位置未定。

**对 EDU 的可执行判据**：
1. 30 秒口径背书 EDU 选型正确："Python 复杂状态机/多 agent 工作流选 langgraph"——EDU 是多轮循环+条件路由+持久化场景，StateGraph 是对的层，不要再叠第二套编排。
2. 两层容错都要：节点内 LLM 调用用 langchain 式 retry/fallbacks 装饰器；图级故障恢复用 langgraph checkpoint——二者不互斥（矩阵"容错机制"行对照）。
3. 语言生态决定选型的纪律：EDU 若出现 Go 侧服务才评估 eino，当前全 Python 栈判定不引入。
4. 选型表必须有"数据口径"声明：评估 EDU 组件时区分 EXTRACTED（代码实测）与厂商宣传数字，禁把厂商基准直接写进验收。

---

## 12. M-005-c02-multiagent-matrix

**核心定位**：C02 七框架横评——11 架构维 + 2 生产维（**框架原生 eval 工具 CB-18** + **上游活跃度 CB-16**），架构对比而非选型矩阵，含协作范式谱系（对话/流程/模拟/助手四分）。

**机制细节**（矩阵级结论）：
- 协作范式谱系：对话驱动（autogen：3 种团队模式+终止条件 / camel：双角色 Inception）、助手驱动（hermes：单 agent+子代理+闭环学习）、流程驱动（MetaGPT 16 角色 SOP / ChatDev 阶段链 / crewAI 角色+任务+流程）、模拟驱动（generative_agents 时间 tick+认知架构）。
- HITL 对照：autogen UserProxyAgent+MessageFilter、hermes 审批三件套+七沙箱最强；MetaGPT/ChatDev/camel 无独立审批系统。
- **CB-18 eval 工具列**（判定口径=官方可执行评测入口，论文方法与第三方评测不计）：有=autogen agbench / hermes hermes-compression-eval+terminalbench / camel benchmarks/ / crewai `crewai test`；无（工具冻结/需自建 harness）=MetaGPT、ChatDev、generative_agents。
- **CB-16 活跃度列**（2026-09-10 GitHub API 实测）：日更级=hermes/crewAI/camel；中=ChatDev(1.5 月)；低=autogen(5 月,官方 Maintenance Mode)；停滞=MetaGPT(8 月,INFERRED,2 CVE 未修)；学术停滞=generative_agents(2 年)。

**卡内链接内容摘要**：矩阵内嵌 4 个 eval 工具 URL（全部 curl 实测 HTTP 200，标注实测日期）+ 7 个活跃度 URL；本次独立复核：agbench README 200、camel gaia.py 200、crewai docs 307 可达、**AutoGen README 行 14-21 Maintenance Mode 原文实证**——卡内 claim 全部为真。

**评估与可观测**：本矩阵即"评估方法论"本身——它把"框架在公开榜单的分数"（CB-15，判永久空转废弃）改造成"官方给什么 harness 测自己的 agent"（CB-18），并叠加活跃度维护风险（CB-16），三者合成生产选型依据。

**对 EDU 的可执行判据**：
1. **任何新依赖入库前查两列：有没有原生 eval harness + pushed_at 是否 <3 个月**——按此判据 autogen/MetaGPT/generative_agents 三者均不进 EDU 依赖树（已实证停滞/维护模式）。
2. EDU 组件选型报告必须含"用什么 harness 测"小节：没有可复现评估闭环的组件，验收视为未完成（对齐 vault 铁律"独立实证"）。
3. EDU 是"单 agent + 工具循环 + 图编排"形态，不处在多 agent 协作范式内——若未来引入多 agent，先按谱系明确选哪种（对话/流程/模拟/助手），拒绝混用两套范式。
4. HITL 最强参照是 hermes 审批三件套 + autogen UserProxy：EDU 教师确认流要对齐"默认审批可降级、危险操作必确认、消息可过滤"。

---

## 13. P-001-workflow-vs-agent

**核心定位**：复杂度阶梯决策卡——单次 LLM 调用 → workflow 五模式 → 自主 agent 的第一道分叉规则，源自 Anthropic 与 12-Factor 两个权威来源。

**机制细节**（决策规则本体）：
1. 先问"一次调用 + RAG + 好示例能否解决"，能则结束。
2. 步骤可枚举、要求一致 → workflow，按复杂度递增五模式：prompt chaining(可加 gate) → routing → parallelization(sectioning/voting) → orchestrator-workers(子任务动态定) → evaluator-optimizer(生成-评审循环)。
3. 步数不可预知、必须看环境反馈 → agent，且必须定义**停止条件（完成判据 + 最大迭代数）**。
4. 任何一级都**自己写控制流和 prompt，不让框架托管**（S-002 因子 2/8 + S-001 框架调试性警告）。

**卡内链接内容摘要**（本次两源均实读）：
- S-001 https://www.anthropic.com/engineering/building-effective-agents （WebFetch 成功）：workflow=预定义代码路径编排 LLM，agent=LLM 动态决定流程；五模式要点与适用场景全表（orchestrator-workers 与 parallelization 的关键区别是子任务不预设）；不该用的情形（检索+示例优化单次调用即可 / 任务需可预测）；框架建议——抽象层掩盖 prompts 难调试，"对底层机制的错误假设是客户出错的常见原因"，用框架必须读其底层代码；三大原则：简单、透明、把 ACI 当 HCI 打磨。
- S-002 https://github.com/humanlayer/12-factor-agents README + Factor 8（直连被拒，代理 curl 成功）：核心原话实证——"most of the products billing themselves as AI Agents are…mostly deterministic code, with LLM steps sprinkled in at just the right points"；12 因子清单（NL→工具调用 / own your prompts / own your context window / tools are structured outputs / 统一执行态与业务态 / launch-pause-resume / 用工具调用联系人类 / **own your control flow** / 错误压缩入上下文 / 小而专的 agent / 任意触发 / 无状态 reducer）；Factor 8 原文：特定工具调用应成为"跳出循环等人类响应"的理由，自定义控制结构（子代理/分支/重试/评估器），并点名"每个 AI 框架最被需要的功能是可中断"。
- 卡片本体为 vault① 迁移留痕（2026-09-07），跨库引用走显式文本。

**评估与可观测**：本卡是决策模式卡，评估含义是"反例清单"：为显得智能用 agent 干 workflow 的活（零收益付延迟成本）、全押框架冲到 70-80% 后被迫逆向工程重写、agent 无停止条件无限烧钱。

**对 EDU 的可执行判据**：
1. 对 9 节点图做一次"阶梯审计"：逐节点判定属于单次调用/固定 workflow/真 agent 循环——判定为固定步骤的节点禁止内部再放 LLM 自主循环（如检索改写节点应是 routing/chaining，不是 mini-agent）。
2. 图中唯一的自主循环（生成-校验-重试类）必须显式携带停止条件：完成判据 prompt + max_iterations + token 上限 + 超时，写进节点配置可审。
3. 控制流与 prompt 自持：EDU 的 prompt 模板集中版本化管理（可 diff/可回滚），不散落在框架封装深处；升级 LangGraph 版本前先读其底层变更（"错误假设是客户出错常见原因"）。
4. ACI 当 HCI 打磨：MCP 工具的 name/description/参数 schema 按"给模型用的 UI"标准写并做评审——工具描述质量直接决定调用正确率。
5. 可中断性排进路线图（Factor 8 点名）：教师可随时打断生成并重定向，对应 SSE cancel + graph interrupt 组合。

---

# TOP10 最锋利判据（本批 13 卡提炼，评审直接引用）

1. **【P-001】复杂度阶梯先审计再编码**：单次调用+RAG 能解决就不上 agent；能 workflow 化的步骤禁止 LLM 自主决策；任何 agent 循环必须自带停止条件（完成判据+max_iter+token 上限+超时）。EDU 动作：对 9 节点图逐节点做阶梯审计并留档。
2. **【F-C02-001 + P-001】终止条件四件套是 loop 硬门槛**：TextMention（完成判据）/ MaxMessage / TokenUsage / Timeout 四类终止缺一不收——autogen 用一个 `_terminations.py` 模块把它做成结构，EDU 的重试/生成循环照此收口。
3. **【F-C01-002】Checkpointer 必须生产化**：MemorySaver 只许开发环境；会话按 thread_id 隔离、断线续跑、interrupt 人工确认走 `invoke(None, thread_id)` 恢复；列表状态字段必须 `Annotated[list, operator.add]` 防静默覆盖。EDU 不用 checkpoint = 白选 LangGraph。
4. **【F-C02-005，公式级实证】记忆/检索排序必须三因子**：score = w1·relevance(cos) + w2·recency(指数衰减 recency_decay^i) + w3·importance(LLM 评分)，各归一化后加权，权重可配置——EDU Milvus 只按 cos 相似度排序判不合格（retrieve.py:145/232-236/247-249 实读核验）。
5. **【M-005 CB-18】选型必问"官方给什么 eval harness 测自己的 agent"**：无原生 eval 工具（MetaGPT/ChatDev/generative_agents）= 评估成本自担；有（agbench / camel benchmarks / crewai test）才可复现。EDU 动作：建 benchmarks/ 目录 + 一键评测命令，输出完成率/token/延迟表。
6. **【M-005 CB-16】上游活跃度是一票否决项**：pushed_at >3 个月或官方 Maintenance Mode 的依赖禁入新代码——已实证：autogen（README 行 14-21 维护模式）、MetaGPT（8 个月停滞+2 CVE 未修）、generative_agents（2 年学术停滞）。
7. **【F-C01-001】容错横切不内联**：retry（指数退避）/fallbacks（备用模型链）/timeout/rate_limit 做成节点外统一调用封装，降级触发必须产观测事件；EDU 的 deepseek→strong 降级链按此模式补观测与限流。
8. **【F-C01-003】取消四场景 + 检查点版本迁移**：SSE 断连取消测试须覆盖边界/多调用/递归/流式竞态（cancel.go 同构）；checkpoint 序列化格式带版本号+迁移测试——EDU 当前两项均为验收盲区。
9. **【F-C02-002】供应链与权限硬约束**：依赖 exact-pinned（==X.Y.Z）+ 锁文件；工具调用三级权限（默认审批/safe-mode/白名单自动），危险 MCP 工具必经教师确认——映射 EDU admin 守卫与 MCP 工具分级。
10. **【P-001 + F-C01-001】自持控制流与 prompt，ACI 当 HCI**：prompt 模板集中版本化可 diff；用框架必须读底层（S-001："错误假设是客户出错的常见原因"）；MCP 工具 schema 按给模型的 UI 标准评审；每节点定义 expected_output 可程序化断言（F-C02-007 Task 三件套同构）。

---
*精读完成时间：2026-09-13。逐卡机制均带卡内锚点；外链实读与不可达标注见文首；TOP10 可直接作为 EduAgent 编排层评审依据。*
