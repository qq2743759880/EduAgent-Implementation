# EDU 项目批判基准清单（基准源：vault②「agent架构」）

> 用途：以 vault② 卡片为基准，对 EduAgent 的 agent 架构做批判性对标。
> 基准库：`E:\stu\project\Obsidian\agent架构`（操作契约 AGENTS.md v1.4）。
> 机验：`bash scripts/vault-lint.sh` 已复跑，**退出码 0**（PASS，2 个非阻塞警告：⑤跨库引用为 lint 对规则说明文字本身的误报、⑥4 文件含 [待补] 存量）。
> 依据卡片：arch-rag / arch-orchestration / arch-memory / arch-context / arch-evals / arch-plan-exec / arch-skill-philosophy / arch-aci / arch-security / arch-workflow（域卡，均为 hub 索引页）；F-C01-002-langgraph、F-C06-001-mem0、F-C06-002-graphiti、F-C06-003-letta、F-C07-001-llama_index、F-C03-001-claude-code；P-001/P-002/P-003；S-001/S-002；M-001（记忆横评）、M-004（编排横评）。
> 置信度规范：判据默认 EXTRACTED（蒸馏自卡片正文 claim 台账，代码级溯源）；INFERRED 单独标注并写依据；UNVERIFIED 不入判据（依 AGENTS.md 铁律 2）。

---

## 一、评判维度与基准判据

### ① RAG（索引/检索/重排/注入/评估）——10 条

1. RAG 管道应显式分段为「索引 → 检索 → 查询引擎 → 响应合成」三/四段式，各段接口化、可独立替换（LlamaIndex 的 Index/Retriever/QueryEngine/ResponseSynthesizer 四件套，Index 提供 as_retriever()/as_query_engine()/as_chat_engine() 统一出口）。[F-C07-001]
2. 索引层不应只有扁平向量一种——基准支持 10+ 索引类型（VectorStoreIndex/SummaryIndex/TreeIndex/KeywordTableIndex/KnowledgeGraphIndex），按查询形态选索引。[F-C07-001]
3. 摄取侧应有独立流水线（Reader→NodeParser→MetadataExtractor→Embedding→VectorStore），支持缓存与并行，失败可重入。[F-C07-001]
4. 分块策略可插拔且与文档形态匹配：SentenceSplitter/TokenTextSplitter/MarkdownNodeParser/CodeSplitter，chunk_size/chunk_overlap 显式配置（Settings 全局或按索引覆盖）。[F-C07-001]
5. 检索参数完备：top_k、similarity threshold 截断、后处理器链（SimilarityPostprocessor 阈值过滤 / KeywordNodePostprocessor / LongContextReorder 长上下文重排 / CohereRerank 精排）——重排序是标配环节而非可选项。[F-C07-001]
6. 查询侧应有查询变换/分解能力：SubQuestionQueryEngine（复杂问题拆子查询）、HyDE 类查询转换、MultiStepQueryEngine 多步推理。[F-C07-001]
7. 响应合成多策略：Refine（逐节点精炼，长上下文）/ TreeSummarize（树状自底向上）/ CompactAndRefine，按上下文长度与任务选合成器。[F-C07-001]
8. 检索应为混合检索：向量语义为主 + BM25 关键词为辅（mem0 对记忆文本做 lemmatize_for_bm25 双通道）；图谱记忆场景用 RRF / NodeDistance / CrossEncoder 三配方融合。[F-C06-001] [F-C06-002]
9. 检索结果必须带分数与可溯源元数据（LlamaIndex 返回 NodeWithScore；mem0 search 提供 explain 参数输出分数详情），注入 LLM 的每条内容可回溯到源。[F-C07-001] [F-C06-001]
10. 【INFERRED】查询与入库 embedding 必须同模型同版本（依据：mem0/LlamaIndex 均将 embedding 抽象为统一 embed 接口并在管道内复用同一实例；此条同时是 EDU 已实证教训——查询/入库 embedding 不同模型会导致召回崩坏）。[F-C06-001] [F-C07-001]

### ② 多智能体编排（LangGraph 形态/图结构/checkpoint/人机环）——10 条

1. 新功能先过复杂度阶梯：单次调用+检索/示例 → workflow 五模式（chaining→routing→parallelization→orchestrator-workers→evaluator-optimizer）→ agent；只在可证明改善结果时升级，"为显得智能而用 agent"是反面教材。[P-001] [S-001]
2. agent 循环必须有显式停止条件：完成判据 + 最大迭代数，否则无限循环烧钱。[P-001] [S-001]
3. 复杂多轮控制流用显式状态图（节点/边/条件边/入口出口）而非隐式管道；条件边承担动态分支与循环（"返回工具调用则执行工具后回模型，否则结束"）。[F-C01-002]
4. 状态 schema 显式定义（TypedDict/Pydantic），且每个字段有明确更新语义（通道：LastValue 最新值覆盖 / Binop 累加 / Topic 发布订阅 / EphemeralValue 超步后清除）——节点返回部分更新而非全量状态，由引擎合并。[F-C01-002]
5. 必须有 checkpoint 持久化：每个执行步后自动保存状态快照，thread_id 会话隔离，后端分开发（Memory）/文件（Sqlite）/生产（Postgres）三级，且有 conformance 一致性测试套件约束后端行为。[F-C01-002] [M-004]
6. 必须支持中断恢复（interrupt）：节点内暂停执行返回中断值，人工输入后从断点继续——长时间任务与人工在环的基础设施，而非业务代码手搓。[F-C01-002]
7. 必须支持时间旅行：从任意历史 checkpoint 恢复、修改历史状态后分支重跑（update_state）——计划回滚与错误恢复能力。[F-C01-002]
8. 多 agent 协作有命名模式可循：Supervisor（中央节点调度 worker）/ Swarm（agent 间转移控制权），以图结构/子图嵌套实现，模块可独立可视化（Mermaid 渲染）。[F-C01-002] [M-004]
9. 控制流和 prompt 必须自有，不让框架托管——框架快速冲到 70-80% 后客户面前不够用、被迫逆向工程重写是 100+ 构建者的共同教训。[P-001] [S-002 因子2/8]
10. 流式输出分档可观测：values（全状态）/ updates（节点增量）/ debug（调试）/ messages（token 级透传），调试与生产各取所需。[F-C01-002]

### ③ 记忆系统（分层/检索/遗忘；mem0/graphiti/letta 核心机制）——10 条

1. 记忆写入应是「提取-决策」管线而非原始消息直存：LLM 单次调用提取关键事实并决定 ADD/UPDATE/DELETE（mem0 V3 五阶段：context gathering→existing memory retrieval→LLM extraction→batch embed→hash dedup）。[F-C06-001] [M-001]
2. 遗忘是软删除而非物理删除，保留记忆演化历史：mem0 expiration_date 过期隐藏、graphiti 边失效（旧关系矛盾时标记 expired_at，valid_at/expired_at 时序属性）、letta Git 历史永久保留。[F-C06-001] [F-C06-002] [F-C06-003] [M-001]
3. 去重机制须显式选型并知晓代价：MD5 hash 精确去重（低成本、无法识别同义）vs LLM 语义去重（识别同义实体、高成本且可能不一致）——两者都做"现有记忆 + 本批次内"双重去重。[M-001]
4. 会话/租户隔离必须在 API 层强制：三级隔离键（user_id/agent_id/run_id）或 group_id 图分区，且 search 类接口拒绝顶层实体参数、强制走 filters，从接口设计上防跨会话泄露。[F-C06-001] [F-C06-002] [M-001]
5. 防幻觉设计：召回的现有记忆 ID 先映射为整数索引再给 LLM，提取结果返回后映射回真实 UUID——LLM 只见整数 ID，无法编造不存在的记忆 ID。[F-C06-001]
6. 记忆管线内 LLM 失败必须显式抛错（LLMError，调用方决定 fallback/retry），禁止静默返回空列表——静默失败是 V2→V3 修复的真实事故。[F-C06-001]
7. 记忆范式三选一按需，非替代关系：向量检索快（mem0）/ 图谱可推理——实体关系+时序问答（graphiti）/ 文件系统+Git 可回滚可审计（letta）；选型依据是"要相关性、要关系推理、还是要可追溯"。[M-001]
8. 原始上下文与结构化记忆分离存储：EpisodicNode 存原始片段快照、EntityNode/EntityEdge 存 LLM 抽取结果（graphiti）；关系库存原始消息、向量库存提取记忆（mem0）——上下文与记忆边界清晰。[F-C06-001] [F-C06-002]
9. 结构化抽取用强类型约束减少幻觉：entity_types/edge_types 接受 Pydantic 模型定义，LLM 输出强制结构化解析；GLiNER2 类轻量 NER 可作低成本预筛选。[F-C06-002]
10. 重量级记忆写入必须异步化：graphiti add_episode 是多阶段多次 LLM 调用（extract→dedupe→embed→invalidate→communities），官方明确建议后台顺序执行防图谱状态不一致——写延迟与读延迟须分开治理。[F-C06-002] [M-001]

### ④ 上下文工程（压缩/预算/纪律）——10 条

1. 主动决定什么进上下文（Own your context window），不让框架/工具默认行为代劳；每步之后先问"上下文里应该剩什么"而非"还能加什么"。[P-002] [S-002 因子3]
2. 错误压缩后再回填：蒸馏成一行可行动原因+建议才进上下文，全量错误日志/整个文件"以防万一"式灌注是明确反面教材。[P-002] [S-002 因子9] [P-003]
3. 小而专注：一个子任务一个独立上下文窗口，不做万能大 agent；长会话连续干多件不相关的事是反面教材。[P-002] [S-002 因子10]
4. agent 做成无状态归约器：状态外置到文件/数据库，上下文随时可从状态重建。[P-002] [S-002 因子12]
5. 预取上下文：任务开始时批量取齐可能需要的材料，不在主循环里反复取。[P-002] [S-002 因子13]
6. 进展评估的 ground truth 来自环境（工具结果/代码执行产物），不信 agent 自我汇报"我觉得进展顺利"。[P-002] [S-001]
7. 长对话分层记忆：旧对话自动摘要 + 最近 N 轮保原文（ChatSummaryMemoryBuffer 模式），token_limit_fn 按窗口动态截断。[F-C07-001]
8. 系统提示多层聚合组装：工具定义 / 环境信息（cwd/OS/状态）/ 记忆 / 技能 / 角色指令分层注入（fetchSystemPromptParts 模式），而非单块巨型 prompt。[F-C03-001]
9. 压缩有显式边界标记：会话压缩点打 CompactBoundary 消息，标记上下文截断边界，压缩后语义可恢复。[F-C03-001]
10. 记忆分常驻与按需两层：persona/human 类记忆块常驻系统提示，大容量文件记忆（MemFS）按需通过工具调用读取，不占窗口。[F-C06-003]

### ⑤ 工具与 MCP（ACI 设计法则/schema/回填/安全）——10 条

1. ACI 投入不低于 prompt 投入：Anthropic 自述做编码 agent 时"优化工具的时间超过优化整体 prompt 的时间"；工具成功率低时先改工具再改 prompt。[P-003] [S-001]
2. 工具 I/O 格式贴近模型自然形态：markdown 代码块优于 JSON 转义；整文件重写优于行号 diff——diff 要求精确计数行数，恰是模型易错点。[P-003]
3. Poka-yoke 防呆参数设计：改参数让错误难以发生（实测：相对路径改绝对路径后 20 次调用 0 次路径失败）。[P-003] [S-001]
4. 工具文档按"给初级工程师"标准写：示例用法 + 边界情况 + 相似工具区别——模型对工具的全部认知来自这段描述。[P-003]
5. 错误返回本身可行动：错误信息就是 prompt，报错原文不压缩直接扔回上下文是反面教材。[P-003]（联动 P-002 因子9）
6. 工具经统一接口注册与调度（名称/描述/参数 schema/统一执行上下文），输出强制 schema 校验（registerStructuredOutputEnforcement 模式）。[F-C03-001]
7. 工具调用前权限检查内建：CanUseToolFn + PermissionMode（只读/按需确认/全自动可切换），危险工具弹确认，用户可选始终允许/拒绝。[F-C03-001]
8. 危险操作人工审核走框架能力：interrupt 在工具执行前暂停、确认后执行（LangGraph 形态），与权限模式双保险。[F-C01-002]
9. 工具结果结构化闭环回填：tool_calls（name/args/id）→ ToolMessage 结果按 id 对应回填，错误也被捕获为 ToolMessage 让模型自行调整策略。[F-C01-002]
10. 工具并行执行受执行引擎约束（超步内并行 tool_calls），MCP 作为一等公民接入（专用 MCP 工具与连接管理/认证：MCPTool/McpAuthTool；记忆层也可直接以 MCP server 形态暴露）。[F-C01-002] [F-C03-001] [F-C06-002]

### ⑥ skill 与资产调用（skill 组织哲学/评测）——6 条（本域卡片最薄，如实从简）

1. 技能可发现再加载：DiscoverSkillsTool 与 SkillTool 分离——先枚举可用技能、再按需加载定义，避免全部技能常驻上下文。[F-C03-001]
2. 技能通过系统提醒注入生效（非 per-project 记忆块），加载即注入使用说明。[F-C03-001] [F-C06-003]
3. 技能与子 agent 均为声明式目录定义（agents/ / skills/ 目录 + AgentDefinition），非硬编码注册。[F-C03-001]
4. 子 agent 委派有上下文预算：主 agent 经 AgentTool 委派任务，子 agent 有独立 context-budget 管理，隔离主窗口。[F-C03-001] [F-C06-003]
5. 技能与记忆可共享但解耦：shared-memory-skills 模式——技能操作记忆有统一入口，技能系统本身不绑定记忆实现。[F-C06-003]
6. 【INFERRED】平台级技能资产应标准化+跨平台适配（依据：arch-skill-philosophy hub 页将 superpowers 定位为"14 标准化开发工作流技能×10 平台"的生态枢纽，但 F-C10-001 内容卡未在本次必读范围，判据深度受限）。[arch-skill-philosophy]

### ⑦ 评估与可观测（轨迹/评分器/回放）——9 条

1. 生成质量评分器分维度内建：Correctness（1-5 分）/ Relevancy（相关性）/ Faithfulness（忠实度=幻觉检测）/ Groundedness（事实接地）/ Guideline（自定义准则）/ PairwiseComparison（成对比较）。[F-C07-001]
2. 检索质量与生成质量分开评估：RetrieverEvaluator 输出 hit_rate / mrr / ndcg 检索指标，不与答案评分混同。[F-C07-001]
3. 评估数据集标准化且可持久化：LabelledRagDataset（query/referenced_contexts/reference_answer）支持保存/加载/导出，评估可回归。[F-C07-001]
4. 批量评估有运行器：BatchEvalRunner 并行跑多评估器×多样本，汇总出报告——评估是批量工程而非单次手测。[F-C07-001]
5. 可观测双层事件模型：CallbackManager（on_llm_start/end、on_retriever_start/end、on_tool_start/end 等细粒度钩子）+ Instrumentation span 事件系统（OTel 兼容、开放标准、不绑单一 SaaS）。[F-C07-001]
6. token 消耗与成本核算内建而非事后补：TokenCountingHandler / cost-tracker / token_tracker（含输入/输出/成本）三例同构。[F-C07-001] [F-C03-001] [F-C06-002]
7. 会话 transcript 完整持久化且可重放（recordTranscript + 会话发现/历史/消息重放），调试可回到任一次真实会话。[F-C03-001]
8. 记忆变更有审计维度：Git log/diff/blame 审计每次记忆变更（letta 独有），配合 pre/post 钩子与 GPG 签名验证提交真实性——记忆系统也应有"变更历史"级别的可观测。[F-C06-003] [M-001]
9. 基础设施行为有一致性测试：checkpoint-conformance 套件约束各持久化后端行为一致——自研状态层/存储层应有同等一致性验收。[F-C01-002] [M-004]

---

## 二、卡片自身的局限（批判知识库，如实）

1. **域卡全部是 hub 索引页，无领域知识本体。** 10 张域卡（arch-rag 等）均由 build-domain-hubs.py 幂等生成的双链聚合页，自身零判据；所有实质内容在 F/P/S/M/A 卡中。本清单的蒸馏密度完全取决于内容卡覆盖。
2. **arch-evals / arch-plan-exec 域最薄。** arch-plan-exec hub 仅挂 4 张 F 卡、无 M/A/P 卡；arch-evals 无任何 M/A/P 卡。计划-执行分离、LLM-as-judge 等主题没有专卡，判据只能从 LangGraph/LlamaIndex 卡的对应分节旁证。
3. **skill 域（arch-skill-philosophy）只有索引没有内容消费。** P 卡 0、A 卡 0；superpowers/mcp-servers/openclaw 仅 hub 链接，本次必读清单未含 F-C10 内容卡——⑥域仅 6 条判据且最后一条只能 INFERRED。
4. **记忆效果评估在知识库内部就是空白。** 三张记忆 F 卡的 arch-evals 分节一致承认"OSS 版无标准化召回率/准确率基准"（mem0 evaluation/ 目录基本为空；graphiti 仅 prompts/eval.py+token_tracker；letta 靠集成测试）——批判 EDU 记忆评估时，知识库自身给不出更高基准，只能给"该建什么"的方向。
5. **安全域无独立方法论卡。** arch-security hub 无 P/A 卡，判据只能从 claude-code（运行时权限）与 letta（Git 签名）间接蒸馏；prompt injection、越权、数据外泄、多租户穿透等教育场景高敏主题无专卡。
6. **P/S 卡存在未闭环"待补"。** P-001 待补各框架在此问题上的实际选择；P-002 待补真实框架 compaction 实测策略；P-003 待补各框架工具 schema 写法对比；S-002 仅基于 README 蒸馏、12 因子主页未逐一蒸馏。这些判据是"原则级"而非"实现级"。
7. **claude-code 卡是 source-leak 通道（Tier3）。** 无官方 git 历史、无官方文档/DeepWiki 交叉验证（对照验证节自述），claim 虽标 EXTRACTED 但交叉验证强度弱于其他 F 卡；引用其对标时需留意版本时效与泄露源偏差。
8. **UNVERIFIED claim 已按规范隔离但提示边界。** mem0 平台版"评估+可观测性"能力为厂商自证（UNVERIFIED 禁入正文）、letta 的 RAM/disk 隐喻可能已随 v0.31 演进——涉及"平台版能兜底"的论断不可用作 EDU 判据。
9. **可观测平台无深度卡。** Langfuse/Opik/Phoenix 仅出现在 hub 链接（F-C09），未在本次必读范围；⑦域判据主要从 LlamaIndex/claude-code 蒸馏，缺"平台级 trace 聚合/跨实例"基准——恰是 EDU 待办中 O1-②③（OTLP 真实后端/跨实例聚合）的对标盲区。
10. **判据以结构性为主，无量化性能基准。** M-001/M-004 的"待补"均注明延迟/成本量化对比需独立基准测试，当前为管道设计推断——本清单能批判 EDU"缺什么机制"，不能直接批判"性能没达标"（后者须另立实测基准）。
11. **RAG 向量库层无 F 卡。** EDU 实际使用向量库（BGE-M3 + CUDA），但 vault 对 Chroma/pgvector/Milvus 等具体向量库无独立画像卡（28/30+ 集成仅是 mem0/LlamaIndex 卡内的目录计数），RAG 判据落在管道层而非存储层选型。

---

## 三、建议 EDU 对标的具体框架机制清单

| # | 机制 | 来源卡 | EDU 对标点 |
|---|---|---|---|
| 1 | LangGraph checkpointer：PostgresSaver + thread_id 会话隔离 + 每步自动快照 | [F-C01-002] | chat 多轮会话状态恢复；Redis 队列任务断点续跑 |
| 2 | LangGraph interrupt 中断恢复 + update_state 时间旅行 | [F-C01-002] | 教学流程人工审核点（如作业批改结果确认后继续）；出错回滚重跑 |
| 3 | LangGraph 条件边 + 子图 + Supervisor/Swarm 模式 | [F-C01-002] [M-004] | 多 agent 编排（出题/批改/辅导 agent 分工）的图结构范式 |
| 4 | mem0 V3 管线：LLM 提取-ADD/UPDATE/DELETE 决策 + MD5 双重去重 + expiration_date 软遗忘 | [F-C06-001] [M-001] | 学习者画像记忆的写入管线与遗忘策略 |
| 5 | mem0 UUID→整数映射防幻觉 + LLMError 显式抛错 | [F-C06-001] | 记忆 ID 交给 LLM 的防编造设计；记忆管线失败不静默 |
| 6 | mem0 三级隔离（user_id/agent_id/run_id）+ filters 强制 | [F-C06-001] [M-001] | 学生/教师/班级多租户记忆隔离的接口级防泄露 |
| 7 | graphiti 混合搜索 3 配方（RRF/NodeDistance/CrossEncoder）+ 边失效时序衰减 | [F-C06-002] | EDU 已用 MySQL 图替代 Neo4j——知识点图谱检索融合配方与知识演化（旧知识失效标记） |
| 8 | letta MemFS + Git 版本化 + worktree 隔离 + 钩子/签名 | [F-C06-003] [M-001] | 教师/管理员配置与画像数据变更的可审计、可回滚（对齐 EDU 合规诉求） |
| 9 | LlamaIndex 评估器组：Faithfulness/Relevancy/Correctness + RetrieverEvaluator(hit_rate/mrr/ndcg) + BatchEvalRunner + LabelledRagDataset | [F-C07-001] | EDU RAG 质量回归测试体系（当前接口验收以 requests/pytest 为主，缺 RAG 质量维度） |
| 10 | LlamaIndex IngestionPipeline + 多索引类型 + 后处理器链（LongContextReorder/CohereRerank） | [F-C07-001] | 课程资料摄取流水线缓存/并行；检索精排环节 |
| 11 | claude-code 权限系统（CanUseToolFn/PermissionMode）+ 计划模式（只读规划→确认→执行）+ 文件历史快照回滚 | [F-C03-001] | agent 工具分级授权（对齐 EDU TOOL_DEFERRED 灰度与 admin 角色守卫思路）；写操作先快照 |
| 12 | claude-code fetchSystemPromptParts 多层系统提示聚合 + CompactBoundary 压缩边界 | [F-C03-001] | EDU chat SSE 的系统提示组装与长会话压缩 |
| 13 | claude-code AgentTool/DiscoverSkillsTool 子 agent 委派 + context-budget | [F-C03-001] [F-C06-003] | 技能调用与子任务隔离，防主会话上下文膨胀 |
| 14 | 12-factor：无状态归约器（因子12）+ 错误压缩回填（因子9）+ 预取（因子13）+ HITL 走工具调用（因子7） | [S-002] [P-002] | EDU agent 服务无状态化（对齐现有 Redis/MySQL 状态外置路线）；工具报错回传 SSE 前压缩 |
| 15 | S-001 复杂度阶梯 + ACI 法则（Poka-yoke/格式贴近模型/文档像给初级工程师写） | [S-001] [P-001] [P-003] | EDU 每个 agent 化新功能的准入检查单；工具 schema 审查清单 |

---

## 附：产出口径

- 判据总数：65 条（①10 / ②10 / ③10 / ④10 / ⑤10 / ⑥6 / ⑦9）
- INFERRED 判据：2 条（①-10 embedding 同模型、⑥-6 技能生态标准化），其余 63 条 EXTRACTED（蒸馏自卡片正文与 claim 台账）
- UNVERIFIED：0 条入判据（mem0 平台版能力、letta RAM/disk 隐喻已按铁律 2 隔离，见第二节第 8 条）
- 机验：`bash scripts/vault-lint.sh` 退出码 0（2026-09-13 复跑实证）
- 本文档为批判基准（判据来自知识库），非 EDU 现状审计；EDU 侧对标结论须另做独立实证
