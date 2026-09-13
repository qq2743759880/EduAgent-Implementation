# KB 精读报告②：记忆/RAG/评估（vault②「agent架构」8 卡深读）

> 精读员产出，2026-09-13。对象：F-C06-001~004、F-C07-001、M-001、M-006、P-002（均全文精读，非标题扫读）。
> 方法合规：已先读 vault 根 AGENTS.md（铁律：溯源必带、置信度三级 EXTRACTED/INFERRED/UNVERIFIED、禁编造）。本报告只读不写 vault，产出落工程区。
> 验证增强：卡内标注的本地克隆（`corpus/repos/<name>/repo`）已实际打开核验评估目录/指标实现；GitHub 直连被网络拒绝（ECONNREFUSED），改用本地克隆等价验证；DeepWiki mem0 页 WebFetch 成功。
> **一句话总判**：8 卡把三种记忆范式（向量/图谱/文件+Git）+ 一套 RAG 框架 + 一套评估平台矩阵讲透了，但 **LOCOMO 在整个 vault 零命中**——记忆效果的标准基准体系是这批卡的最大空洞；唯一能落地的记忆基准 harness 是 cognee 的 eval_framework（本地实测，比卡内描述更丰富）。

---

## 一、F-C06-001 mem0——通用 agent 记忆层（扁平向量，V3 批量管道）

**1. 核心定位**：agent 的记忆层（memory layer for agents），"additive memory"增量记忆哲学——新消息经 LLM 提取关键事实后决定 ADD/UPDATE/DELETE，不覆盖旧记忆、保留演化历史。库（OSS）+平台双形态。pinned commit `dae67f74`，65,110★。

**2. 机制细节**（卡内溯源 repo:mem0/memory/main.py）：
- **写入管线 = V3 分阶段批量管道 5 阶段**（main.py:916 注释）：
  - Phase 0 context gathering：`db.get_last_messages(session_scope, limit=10)` 取最近 10 条消息作工作上下文（:919-921）
  - Phase 1 existing memory retrieval：查询嵌入 + `vector_store.search(top_k=10, filters)` 召回相关现有记忆（:925-931）
  - Phase 2 LLM extraction：**单次 LLM 调用**，`ADDITIVE_EXTRACTION_PROMPT` + `response_format=json_object`，同时完成"提取事实 + 决定 ADD/UPDATE/DELETE + 关联现有记忆"三件事（:940-969）；LLM 失败抛 `LLMError`（V3 对 V2 静默失败的修复）
  - Phase 3 batch embed：批量嵌入，失败降级为逐个嵌入（:994）
  - Phase 4/5：CPU 处理 + **MD5 hash 双重去重**（现有记忆 + 当前批次内，:1007-1024）
- **anti-hallucination**：Phase 1 召回的 UUID 映射为整数索引 `{str(idx): mem.id}`，LLM 只见整数 ID，防编造记忆 ID（:933-938）
- **遗忘**：`expiration_date` 软过期——过期记忆从 search/get_all 隐藏（`show_expired=True` 才显示），非物理删除（:788-789, :1389）
- **会话隔离**：user_id/agent_id/run_id 三级；`search()/get_all()` 拒绝顶层 entity 参数、强制 filters（`_reject_top_level_entity_params`，:1436），防跨会话泄露
- **检索**：向量为主 + BM25 为辅（`lemmatize_for_bm25`，:1026）；search API 默认 top_k=20 / threshold=0.1 / rerank=False；metadata filtering 14 种操作符（eq/ne/in/gt/wildcard/AND/OR/NOT…）
- **infer=True/False 取舍**：True=LLM 提取质量高但依赖 LLM；False=直接存原始消息、噪声大但零 LLM 成本
- 另有 `procedural_memory` 独立创建路径（需 agent_id，卡内标注待精读）

**3. 记忆效果评估与基准**（用户点名专题①）：
- 卡内原文（§arch-evals）：**"OSS 版评估框架较薄——evaluation/ 目录基本为空（无 .py 评估脚本），记忆效果评估主要在平台版提供"**，置信度 INFERRED，且列为待补项。
- **本次本地克隆实测（新增证据，解决该待补项）**：`find corpus/repos/mem0/repo/evaluation -type f` 返回**零文件**——evaluation/ 目录确认为空壳。卡内判断由 INFERRED 升级为 EXTRACTED。
- **LOCOMO / LLM-judge / hit-rate：卡内完全没有**。全 vault grep "locomo" 零命中；WebFetch DeepWiki mem0 页确认其目录树无任何 benchmark/评估章节。"mem0 平台版提供评估"仅 README/官网描述，卡内已标 UNVERIFIED（厂商自证）。
- 卡内给出的 OSS 侧唯一可调杠杆：search 的 threshold/top_k 调检索质量、infer 开关对比提取质量、ADDITIVE_EXTRACTION_PROMPT prompt 工程是关键调优点。

**4. RAG/索引/重排/向量库**：无自有索引/重排；检索即向量库 top-k + 可选 rerank 参数（rerank=True 走后端，具体 reranker 实现卡内未展开）。**向量库 = 28 个集成**（chroma/pinecone/qdrant/weaviate/milvus/pgvector/redis/mongodb/elasticsearch/faiss…，`repo:mem0/vector_stores/`），提供商无关统一接口 search/insert/delete——**只列举，无任何选型对比结论**。

**5. 卡内链接内容摘要**：
- GitHub blob/tree 链接（pinned commit）：网络拒绝未直读，已用本地克隆等价核验（见上）。
- DeepWiki 对照源 https://deepwiki.com/mem0ai/mem0 ：WebFetch 成功——页面为代码导览（Multi-Level Memory/Hybrid Retrieval/Temporal Reasoning 等功能描述），**无评估/LOCOMO 内容**；与卡内"对照验证一致"结论相符。
- 卡内注明 DeepWiki 为 Tier2 对照源（非官方文档 Tier1）。

**6. 对 EDU 的可执行判据**：
1. **EDU 的学习记忆层若自建，抄 V3 管道骨架**：取最近 10 条消息→向量召回 top_k=10 旧记忆→单次 LLM 调用输出 JSON 决定 ADD/UPDATE/DELETE→批量嵌入→hash 去重；不要为每条消息多次调 LLM。
2. **UUID→整数映射必须抄**：edu 后端让 LLM 决策记忆更新时，只暴露整数索引，返回后映射回真实 ID，杜绝 LLM 编造记忆 ID。
3. **会话隔离照抄三级 filters 强制**：EDU 多租户（student/teacher/admin）检索接口应拒绝顶层 entity 参数、强制 filters，从 API 层防跨学生数据泄露（对应 AGENTS.md 里 DEBUG 虚拟用户教训的同类风险面）。
4. **MD5 hash 去重不够用**：EDU 场景同义表述多（"张老师"="Teacher Zhang"），hash 只能精确去重；要么接受冗余，要么引入 graphiti 式语义去重（成本换质量）。
5. **遗忘用 expiration_date 软隐藏而非物理删**：课程结束后学习偏好记忆设过期，检索时过滤，保留审计能力。
6. **别指望 mem0 OSS 给你评估**：EDU 若采用 mem0 式记忆，评估必须自建（见 cognee/LlamaIndex 判据）。

---

## 二、F-C06-002 graphiti——时序知识图谱记忆层（四层节点 + 混合搜索）

**1. 核心定位**：把 agent 记忆建模为**带时间属性的知识图谱**而非扁平向量条目，解决"向量记忆答不了 A 和 B 什么关系、什么时候建立的"这类结构化推理问题。pinned `b943c9e8`，30,796★。

**2. 机制细节**：
- **四层节点**（nodes.py）：EntityNode（实体）/ EpisodicNode（片段，原始上下文快照，含 reference_time）/ CommunityNode（社区聚类）/ SagaNode（长篇事件链摘要）；**多层边**（edges.py）：EntityEdge（带 valid_at/expired_at）/ EpisodicEdge / HasEpisodeEdge / NextEpisodeEdge / CommunityEdge
- **写入 = 6 阶段管道**（graphiti.py:980-1060）：extract_nodes（LLM 抽实体，支持 Pydantic entity_types 强类型约束）→ extract_edges → dedupe_nodes/dedupe_edges（**LLM 语义去重**，识别同义实体/矛盾关系）→ 批量嵌入 → **edge invalidation**（新关系矛盾时旧边标 expired_at）→ build_communities（可选）
- **遗忘 = 边失效**：expired_at 非物理删除，保留记忆演化史；时序衰减天然内建
- **巩固 = 社区检测 + Saga 摘要**：实体自动聚类、事件链自动摘要
- **检索 = 混合搜索 3 配方**（search_config_recipes.py）：EDGE_HYBRID_SEARCH_RRF（倒数排名融合，无中心节点默认）/ EDGE_HYBRID_SEARCH_NODE_DISTANCE（中心节点距离重排，有 center_node_uuid）/ COMBINED_HYBRID_SEARCH_CROSS_ENCODER（交叉编码器精排，高级 search_() 默认，OpenAIRerankerClient）；search_() 另支持 BFS 原点、时间范围/实体类型/社区过滤；默认 num_results=10，以当前时间做时序相关性参考
- **多租户 = group_id 图分区**（NodeNamespace/EdgeNamespace 物理隔离），search 可传 group_ids 跨分区
- **成本警告**：add_episode 多次 LLM 调用，官方 docstring（:1056-1058）明确"run as a background process + each episode added sequentially and awaited"；FalkorDB 并发丢连接（INFERRED），本地开发建议 Neo4j
- GLiNER2 轻量 NER 可替代/预筛 LLM 抽实体，降成本

**3. 记忆效果评估与基准**（专题①）：
- 卡内原文（§arch-evals）："OSS 版评估框架较薄但有基础组件——prompts/eval.py 提供评估提示词模板，token_tracker.py 追踪 token 消耗（输入/输出/成本），telemetry/ 事件捕获；无标准化记忆召回率/准确率基准"。
- **本次本地实测**：graphiti_core/prompts/eval.py 含 `EvalResponse(is_correct: bool, reasoning: str)` 与 `QAResponse`（"how Alice would answer the question"）——即**布尔判定+推理链的 LLM-as-judge 模板**，可用于"给定剧情问答→judge 判对错"的记忆评估回路，但仓库未内置标准基准集。待补项（tests/ 是否有评估测试）未在卡内闭环，本次未深挖 tests/ 全目录。
- LOCOMO/hit-rate：卡内与 vault 均无。

**4. RAG/索引/重排/向量库**：后端是 **4 图数据库**（Neo4j/FalkorDB/Kuzu/Neptune，driver/ 目录），向量与图谱混合检索；**重排是卡内少有的 explicit 实现**——CrossEncoder（OpenAI reranker）做语义精排 + NodeDistance 做图距离重排 + RRF 做多路融合。这三种重排配方是全 vault 最完整的重排方法论。

**5. 卡内链接内容摘要**：GitHub pinned blob/tree 链接（网络拒绝，本地克隆等价核验通过：nodes.py/edges.py/eval.py 均在）；DeepWiki 对照 https://deepwiki.com/getzep/graphiti 卡内记录 2026-09-08 HTTP 200、结论一致（本次未重复抓取）。

**6. 对 EDU 的可执行判据**：
1. **EDU 需要"知识点间关系"类问答（先修关系/教师-课程-班级归属）才上图谱记忆**；纯事实记忆用向量层（mem0 式）即可，图谱写入成本高一个数量级。
2. **图谱写入必须走后台顺序队列**：EDU 若引入 graphiti 式抽取，add_episode 等价物应挂到已有的 Redis 队列（task39/R1-③ 已闭环真 Redis），严禁在 chat 请求线程内同步抽取。
3. **遗忘用"边失效"模式**：EDU 的课程-教师关系变更时旧关系标 expired_at 而非删除，支持"上学期谁教这门课"回溯——教学场景强需求。
4. **重排三配方可直接移植**：EDU RAG 现无重排，最低成本先上 RRF（向量+BM25 两路融合，无需训练），有余力再上 CrossEncoder 精排（graphiti 默认组合）。
5. **实体抽取用 Pydantic 强类型约束**：edu 域实体（Course/Teacher/Student/KnowledgePoint）先定义 schema 再抽取，减少幻觉，这也是评估时判对错的依据。
6. **评估起步方案**：抄 eval.py 的 `is_correct+reasoning` judge 模板，构造"剧情→问题→答案→judge"小回路，配合 token_tracker 控成本。

---

## 三、F-C06-003 letta——有状态 agent 框架（MemFS 文件系统 + Git 版本化记忆）

**1. 核心定位**：原 MemGPT；把记忆建模为**可版本化的文件系统**（Markdown 存 `~/.letta/agents/<agentId>/memory/`，整目录是 Git 仓库），OS 隐喻 main context=RAM / external memory=disk。注意卡内已澄清：代码在 `letta-ai/letta-code`（v0.31.13，TypeScript），`letta-ai/letta` 已是 landing page。pinned `2f0fb7c1`，24,699★。

**2. 机制细节**：
- **MemFS**：memory-filesystem.ts（21KB），MEMORY_FS_ROOT=".letta"；agent 通过 write_file/edit_file/read_file/list_directory/search_file_content 工具读写记忆
- **Git 版本化**：memory-git.ts（61KB）提供 commit/branch/merge/diff/log/status；记忆变更自动 commit；**worktree 隔离**（memory-worktree.ts 18KB）支持不同会话/任务并行记忆分支实验，Git merge 解决冲突；**Git 钩子 + GPG 签名**（memory-git-hooks.ts 13KB / memory-git-signing.ts）支持记忆变更审计与提交验证
- **块记忆**：标准 agent 用 persona/human 块（memory.ts，MEMORY_BLOCK_LABELS=["persona","human"]，从 .mdx 模板加载），创建时注入系统提示；READ_ONLY_BLOCK_LABELS 标只读块
- **检索 = 文件系统遍历**（非向量语义搜索）：检索质量依赖 agent 的工具调用策略而非搜索引擎；另有 Gemini 专用 search-file-content/read-many-files 工具适配（INFERRED 由命名推断）
- **遗忘 = 目录限制**：MEMORY_TREE_MAX_LINES/CHARS/CHILDREN_PER_DIR 防记忆树过大；无显式过期，Git 历史永久保留
- **上下文边界**：max-context.ts 管窗口上限；块记忆常驻提示词，MemFS 按需工具读取不常驻
- 完整平台：28 子目录（channels/cron/queue/sandbox/skills/lsp…），有主循环（工具调用循环），非纯记忆库

**3. 记忆效果评估与基准**（专题①）：
- 卡内原文（§arch-evals）："OSS 版评估框架较薄——integration-tests/ 目录包含集成测试（memory-filesystem.sync.integration.test.ts…），评估主要通过集成测试间接衡量记忆系统正确性，无标准化记忆召回率/准确率基准。**记忆可追溯性是 letta 的独特评估维度——Git log/diff/blame 可审计每次记忆变更，这是 mem0/graphiti 不具备的**"。
- **本次本地实测（发现卡-码偏差）**：本地克隆**无 integration-tests/ 目录**；记忆相关测试实际位于 `src/memory-confinement.test.ts`、`src/memory-constraints.test.ts`（记忆约束/边界测试）。卡内引用的具体测试文件路径在本 pinned 克隆中未复现——判定为卡内 INFERRED 级偏差（clone 时点或目录结构差异），不影响"GIT 审计=替代评估维度"的核心结论。
- letta 无 LOCOMO 类基准；卡内"操作系统隐喻"自评 UNVERIFIED（MemGPT 时代哲学，可能已演进）。

**4. RAG/索引/重排/向量库**：**无向量库、无索引、无重排**——letta 用"agent 主动翻文件"替代检索系统，是三种记忆范式中唯一不依赖嵌入模型的。检索效率是它的明确短板（卡内缺点第一条）。

**5. 卡内链接内容摘要**：GitHub pinned 链接（本地克隆核验：memory-git.ts/memory-worktree.ts/src 测试均在，integration-tests/ 不在）；DeepWiki 对照 https://deepwiki.com/letta-ai/letta-code 卡内记录一致（本次未重复抓取）。

**6. 对 EDU 的可执行判据**：
1. **教学 agent 的"教案/讲义类记忆"适合 letta 模式**：教师侧知识以 Markdown 文件+Git 管理，人类可读可编辑可回滚——比向量记忆更适合教师手动维护。
2. **给 EDU 学习记忆加审计层不必上 Git**：mem0 式向量记忆缺审计，EDU 合规要求（家长/校方查"AI 给孩子记了什么"）可借 letta 思路：每次记忆变更落一张 append-only 变更表（等价 git log），检索仍走向量。
3. **worktree 隔离=记忆 A/B 实验模式**：EDU 调记忆策略时，新策略在分支上跑，验证后 merge——避免直接污染学生主记忆。
4. **文件检索效率教训**：EDU 课件库若上万文件，绝不能用"agent 翻目录"当主检索；文件模式只适合小而重要的核心记忆（<几百条）。
5. **目录大小限制值得抄**：给每学生记忆设 MAX_LINES/CHARS 硬上限，防长学期累积后上下文爆炸。
6. **记忆变更可挂钩子**：记忆写入触发 pre/post 钩子做敏感内容审查（EDU 场景的未成年人内容安全刚需）。

---

## 四、F-C06-004 cognee——可编程记忆引擎（memify 管道 + 图/向量双存储）

**1. 核心定位**："memory is a programmable interface"——记忆是可定制的提取→处理→存储→检索管道；多数据库适配器（4 图库 + LanceDB 向量 + 关系库）+ 混合检索 + MCP 原生 + 分布式。pinned `e93a4f0c`，30,639★，MIT，freshness=hot（pushed 2026-09-06）。与 mem0（简单 API）/graphiti（纯时序图谱）/letta（文件+Git）定位互异、可组合。

**2. 机制细节**：
- **memify 管道**（memify_pipelines/ + tasks/memify/）：提取→分块→嵌入→存储→索引，每步可组合/替换/扩展
- **双存储**：图（ladybug adapter 3968 行/Neo4j 2543 行/Neptune 1554 行/postgres_demo 1437 行，**内置 Kuzu 嵌入式图库**零外部依赖）+ 向量（LanceDBAdapter 1534 行）+ 关系库（元数据），统一适配器接口运行时切换
- **混合检索**（modules/retrieval/）：hybrid_retriever（向量+BM25+图谱）+ **code_retriever.py 1643 行（AST 级代码结构检索）** + brute_force_triplet_search
- **上下文三层**：SessionManager（会话恢复/多会话隔离）+ 全局上下文索引（所有实体关系统一索引，跨会话全局检索、防重复不一致，支持增量更新）+ 记忆注入（按 token 限制选最相关记忆）
- **接口四层**：MCP 服务器（cognee-mcp 独立子包）+ REST（api/v1/remember/remember.py 1464 行）+ Python API（cognee.add/search/update）+ CLI
- **分布式**：distributed/ + cognee_db_workers/ 工作进程，管道步骤可分布执行
- DeepWiki 复验（卡内 2026-09-09 裁决一致）：ECL 管道 / remember-recall-forget-improve / 图-向量-关系三库 / 混合检索（Graph 4.2+Vector 4.3+Agentic 4.6）/ MCP 2.4 / 分布式 10.7

**3. 记忆效果评估与基准**（专题①——**本卡是全 vault 唯一有实装记忆基准 harness 的卡**）：
- 卡内原文（§arch-evals）："eval_framework 提供记忆质量评估框架，支持检索质量评估（**准确率/召回率/MRR/NDCG**）、记忆一致性评估、管道性能评估；基准测试（evals/）支持与其他记忆框架（mem0/graphiti）对比评估"。
- **本次本地克隆实测（重大增补，部分纠正卡内表述）**：
  - `cognee/eval_framework/README.md`：定位 "Reproducible, one-command **memory-quality benchmarking**"，四步链 **corpus building → question answering → evaluation → dashboard**；一行跑基准 `cognee eval --benchmark HotPotQA --engine direct_llm --limit 5`；**seed=42 确定性采样**保证可复现；重依赖（DeepEval 引擎/HTML dashboard/数据集下载）放可选 `cognee[eval]` extra，核心包零侵入。
  - **内置基准集**（benchmark_adapters/）：**HotPotQA、Musique、TwoWikiMultiHop**（多跳问答）、Dummy、logistics_system；README 明示 **LongMemEval** 注册后即可接入（vault 内最接近 LOCOMO 定位的基准钩子）。
  - **评估双引擎**：`direct_llm`（直连 .env LLM）或 `deepeval`（DeepEval 框架）。
  - **实际指标**（evaluation/metrics/ + deep_eval_adapter.py 实测）：**ExactMatch(EM)、F1、ContextCoverage、Rubric、correctness（GEval，LLM-judge）、contextual_relevancy（DeepEval ContextualRelevancyMetric）**；统计上带 **bootstrap_ci（10000 次重采样，95% 置信区间）**；beam/eval/metrics/ 另有 **beam_rubric、kendall_tau**（排序一致性）与 run_sweep 参数扫描。
  - **⚠️ 纠错**：卡内写的"MRR/NDCG"在全仓 grep 中**零命中**——cognee 实际没有 MRR/NDCG 实现，卡内该句系超出代码证据的推断（应降级为 INFERRED 或改为 EM/F1/coverage）。这是本次精读发现的**卡内事实性偏差之一**。
  - QA 检索默认引擎：`cognee_graph_completion`（图谱补全式问答）。

**4. RAG/索引/重排/向量库**：图+向量双存储、混合检索多策略可配权重；向量库默认/主推 **LanceDB**（嵌入式），图库默认可零依赖 Kuzu。无独立 reranker 模块（区别于 graphiti 的 CrossEncoder 配方与 LlamaIndex 的 postprocessor 生态）。

**5. 卡内链接内容摘要**：GitHub pinned 链接（本地克隆核验通过且深度超出卡内——eval_framework 目录树/README/metrics 实现均已读）；DeepWiki 对照 https://deepwiki.com/topoteretes/cognee 卡内记录 2026-09-09 编排者复验一致。

**6. 对 EDU 的可执行判据**：
1. **EDU 记忆效果评估直接抄 cognee harness 四步链**：构造语料→生成问答→跑指标→出报表；EDU 版语料=学生-课程交互记录，基准题=课程知识点多跳问题（"该学生连续两周哪类题错误率最高"），指标起步 EM/F1+LLM-judge correctness。
2. **评估必须 seed 固定 + 置信区间**：seed=42 与 bootstrap_ci 是让"记忆策略 A vs B"结论可信的最低要求；EDU 的记忆优化迭代（RAG 调参）应照此建立回归基线，纳入现有 test-reports 独立实证体系。
3. **LongMemEval 是比 LOCOMO 更可得的替代**：cognee 已留适配钩子；EDU 长期记忆评估优先挂 LongMemEval 类长程基准，而非自造。
4. **内置 Kuzu 的"零外部依赖图库"值得 EDU 评估**：AGENTS.md 记载 task35 已用 MySQL 图替代 Neo4j——若未来需图记忆，嵌入式 Kuzu 比再运维一个 Neo4j 务实。
5. **全局上下文索引防记忆不一致**：EDU 学生画像（年级/偏好/薄弱点）多处引用时，统一索引+增量更新避免"两处画像矛盾"。
6. **AST 级 code_retriever 与 EDU 弱相关**（EDU 非代码库记忆场景），但"按结构而非纯文本分块检索"思想可迁移到课件结构化分块（章-节-知识点）。

---

## 五、F-C07-001 LlamaIndex——RAG 知识检索框架（Index/Retriever/QueryEngine 三段式）

**1. 核心定位**：RAG 专用框架（52,126★，RAG 第一大仓），数据连接优先：100+ readers / 30+ 向量库 / 50+ LLM / 10+ 索引类型；v0.10 多包分层（core/integrations/instrumentation），v0.12 Workflow 事件驱动。与 mem0 的分界（卡内 Disputed 节）：mem0=记忆即产品（自动实体级），LlamaIndex=RAG 即框架（文档级、手动管理）；**两者可组合**（LlamaIndex 做文档 RAG、mem0 做 agent 记忆层，互为 Memory 实现）。

**2. 机制细节**：
- **三段式**：Index（as_retriever/as_query_engine/as_chat_engine；VectorStoreIndex 414 行最常用）→ Retriever（VectorIndexRetriever top_k/similarity_cutoff、AutoMergingRetriever 层级自动合并、RecursiveRetriever 递归）→ QueryEngine（RetrieverQueryEngine 208 行；SubQuestionQueryEngine 子问题分解；HyDE 查询扩展；MultiStepQueryEngine）→ ResponseSynthesizer（Refine 逐节点精炼/TreeSummarize 树状摘要/CompactAndRefine 紧凑+精炼）
- **摄取管道**：IngestionPipeline 串联 Reader→NodeParser→MetadataExtractor→Embedding→VectorStore，带缓存与并行；分块 SentenceSplitter/TokenTextSplitter/MarkdownNodeParser/**CodeSplitter**
- **记忆五型**：ChatMemoryBuffer(137行，token 截断)/ChatSummaryMemoryBuffer(287行，旧对话摘要)/VectorMemory(167行)/ComposableMemory(组合多记忆源)/BaseMemory(748行，token_limit_fn)
- **上下文管理**：Settings 全局单例（chunk_size/chunk_overlap/llm/embed_model）+ TokenCountingHandler 统计 + token_limit_fn 动态截断——运行时灵活配置，无统一硬上限（与 codex 编译期硬上限相对）
- **后处理器（重排位）**：SimilarityPostprocessor（相似度阈值过滤）、KeywordNodePostprocessor、**LongContextReorder**（长上下文重排，抗 lost-in-middle）、**CohereRerank**
- **可观测性**：CallbackManager（on_llm_start/end、on_retriever_start/end…）+ Instrumentation 事件系统（OTel 兼容）+ Arize/Phoenix/Wandb 集成

**3. 检索评估指标——hit_rate/mrr/ndcg/faithfulness 具体做法**（专题③，本次本地代码实测，卡内只有一行提及）：
- **RetrieverEvaluator**（evaluation/retrieval/）：指标实现于 `evaluation/retrieval/metrics.py`——**HitRate**（metric_name="hit_rate"，:29，支持 use_granular_hit_rate 细粒度命中）、**MRR**（:96，use_granular_mrr，倒数排名求和 :146-158）、**NDCG**（:372，dcg/idcg 比值 :426-427）；注册表 :497-502 `{"hit_rate": HitRate, "mrr": MRR, ..., "ndcg": NDCG}`；**DEFAULT_METRIC_KEYS = ["hit_rate", "mrr"]**（notebook_utils.py:9）——即官方默认双指标是 hit_rate+mrr，ndcg 需显式启用。
- **标准基准**：`evaluation/benchmarks/beir.py` 集成 **BEIR**（EvaluateRetrieval 产出 NDCG@k/MAP/recall/precision，:96-103）——要"权威口径"用 BEIR，要"日常回归"用 hit_rate/mrr。
- **FaithfulnessEvaluator**（faithfulness.py:98）：LLM-judge 实现——DEFAULT_EVAL_TEMPLATE 逐条判断 "Information: {query_str} / Context: {context_str}" 是否被上下文支持（逐句 yes/no 汇总），并为 llama3:8b 本地模型内置特化模板（TEMPLATES_CATALOG）。
- **生成侧评估器全家桶**：CorrectnessEvaluator（1-5 分）、RelevancyEvaluator、GuidelineEvaluator（自定义指南）、PairwiseComparisonEvaluator（成对比较）、SemanticSimilarityEvaluator（embedding 相似度）、GroundednessEvaluator；**BatchEvalRunner** 批量并行；**LabelledRagDataset**（query/referenced_contexts/reference_answer）标准评估数据集格式。

**4. RAG/索引/重排/向量库**：10+ 索引类型（Vector/Summary/Tree/KeywordTable/KnowledgeGraph/ComposableGraph…）；30+ 向量库集成（vector_stores 集成目录，与 mem0 同样**只列举无选型对比**）；重排走 postprocessor（阈值过滤/关键词/长上下文重排/CohereRerank）。

**5. 卡内链接内容摘要**：GitHub pinned 链接（本地克隆核验通过：metrics.py/faithfulness.py/beir.py 行号均复核）；DeepWiki 对照 https://deepwiki.com/run-llama/llama_index 卡内记录一致；卡内另记 GWT-8 真实漂移检测（HEAD 漂移 1 commit 仅 README 删徽章，L1 微漂移不触发重蒸馏）——溯源纪律范本。

**6. 对 EDU 的可执行判据**：
1. **EDU RAG 检索评估最低配置 = hit_rate + mrr**（LlamaIndex 官方默认双指标）：用 admin-rag 现有题库构造 LabelledRagDataset 式标注集（query/应命中的课件 chunk/参考答案），跑 RetrieverEvaluator，接入 test-reports 回归。
2. **faithfulness 必测**：EDU 教学场景幻觉代价高，照抄其逐句 yes/no 模板（信息+上下文→是否被支持），对 chat SSE 输出抽样评 faithfulness，阈值卡线。
3. **LongContextReorder 是零成本优化**：EDU chat 常把多段课件塞上下文，检索后按相关性重排（重要信息放两端）可抗 lost-in-middle，无需新依赖即可自实现。
4. **分块策略对课件用结构分块**：MarkdownNodeParser 按标题分块优于固定 token 切分（课件天然有章-节结构）；代码类课件用 CodeSplitter。
5. **摘要记忆管长学期对话**：ChatSummaryMemoryBuffer 模式（旧对话摘要+近 N 轮原文）适配 EDU 跨学期辅导会话，替代无限追加。
6. **权威口径用 BEIR**：对外汇报/论文级结论用 BEIR 的 NDCG@10/MAP，日常迭代用 hit_rate/mrr——两套口径分开。

---

## 六、M-001-c06-memory-matrix——记忆框架 11 维横评（mem0 vs graphiti vs letta）

**1. 核心定位**：三记忆范式横评矩阵，中立性声明"格内结论全部回溯三张 F 卡代码级溯源，厂商数字 UNVERIFIED 不入正文"。sources=[F-C06-001/002/003]，不含 cognee（cognee 卡晚于本矩阵，属矩阵待补缺口）。

**2. 机制细节（矩阵增量信息，即三卡横向对齐后的锋利结论）**：
- **写入**：mem0 单次 LLM 调用 / graphiti 多次 LLM 调用（后台顺序）/ letta 无独立提取管道（工具调用即写入）
- **去重**：mem0 MD5 精确（不识别同义）/ graphiti LLM 语义（识别同义、成本高、可能不一致）/ letta 无显式去重（Git 留痕靠 agent 自判）
- **遗忘**：mem0 expiration_date 软隐藏 / graphiti 边失效 expired_at / letta 目录大小限制+历史永久
- **版本化**：mem0 无（更新覆盖）/ graphiti 时序属性半版本化 / letta Git 完整版本树可回滚
- **成本**：mem0 单调用低成本 / graphiti 高成本高推理力 / letta 成本含在主循环
- **评估行**：三者 OSS 均无标准化基准；letta 的 Git 审计是独特评估维度
- **30 秒口径**："向量检索快 / 图谱可推理 / Git 可回滚——三者非替代关系而是记忆范式选择"

**3. 记忆效果评估与基准**：矩阵明确"本矩阵无独立实验，全部数字来自 F 卡已验证溯源"，并把**"三者延迟/成本量化对比需独立基准测试""letta 文件遍历 vs 向量搜索的召回率/延迟对比""GLiNER2 vs LLM 抽取成本/准确率对比"全部列为待补**——即库内承认：记忆范式间**没有任何跨框架量化对比数据**。

**4. RAG/索引/重排/向量库**：矩阵"提供商生态"行仅转述三卡集成数（mem0 28 向量库 / graphiti 4 图库 / letta BYOK），**无 Milvus/Qdrant/pgvector/Weaviate 选型对比**。

**5. 卡内链接内容摘要**：无外部 URL，全部为 F 卡 ID 回溯（内部溯源链设计）。

**6. 对 EDU 的可执行判据**：
1. **EDU 记忆选型直接用 30 秒口径**：聊天助手事实记忆（学生偏好/进度）→mem0 式向量层；知识点关系推理→graphiti 式图谱；教师可维护知识→letta 式文件——EDU 三种都要但分场景，不要造"万能记忆"。
2. **写入成本决定架构位置**：EDU chat 在线链路只允许 mem0 式单 LLM 调用（或更轻）；graphiti 式多阶段抽取一律异步后台（接已有 Redis 队列）。
3. **矩阵待补项即 EDU 实验清单**：三范式延迟/成本对比在库内无人做过——EDU 若做记忆选型，先小样本实测写入延迟与 token 成本，别信任何厂商页。
4. **cognee 不在矩阵是缺口**：引用矩阵时注意其只覆盖三范式；cognee（可编程管道）需单看 F-C06-004。

---

## 七、M-006-c09-evaluation-matrix——评估/可观测平台横评（langfuse vs opik vs phoenix）

**1. 核心定位**：C09 三平台对比，解决"LLM 可观测性/评估平台怎么选"。sources=[F-C09-001/002/003]（三张 F 卡不在本次精读清单，本节仅依据 M-006 本体）。

**2. 机制细节（矩阵本体关键行）**：
- **langfuse**：OTel 原生摄入（OtelIngestionProcessor.ts 3864 行，gen_ai.* 语义约定）；Trace→Span→Generation→Observation 四层追踪模型；评分仓库 scores.ts 3365 行（人工/自动/模型评分）+ 数据集管理（生产追踪可导入为评估数据集）+ Prompt 版本管理/A-B；MIT 核心+EE 企业版；TypeScript/Next.js 全栈；34,353★
- **opik**：评估优先——**opik_optimizer/ 495 files（Prompt 优化/超参搜索/A-B/贝叶斯优化，三框架唯一）**；多语言 SDK 最丰富（sdks/ 5259 files，Python+TS）；Guardrails 后端（LLM 输出防护）；Apache-2.0 完全开源；Comet ML 背景；21,873★
- **phoenix**：**evaluators.py 3065 行（LLM-as-judge/规则评估/自定义）**；Playground 客户端 4321 行（多模型实时对比，三框架唯一）；MCP 原生（server/mcp/sql/parse.py 3333 行 Text-to-SQL）+ Agent 管理（3745 行）+ Trace DSL 过滤（3623 行）；Python 优先；**ELv2 协议（商业使用受限）**；11,346★
- 共同能力行：三平台都有"数据集 CRUD/版本/快照 + 生产追踪导入为评估数据集 + 评估回归和告警"

**3. 记忆效果评估与基准（专题①的平台侧答案）**：M-006 是"平台级 LLM-as-judge/数据集/回归"方法论来源——**LLM-as-judge 的工业化落点是 phoenix 的 evaluators.py（judge 评估器）与 opik 的 optimizer（用评估反馈做 Prompt/超参优化）**；数据集管理三平台一致支持"生产 trace→评估数据集"转化，这是线上数据反哺评估的通路。但注意：**M-006 通篇无 hit_rate/mrr/ndcg**——平台管 trace+judge，检索指标要靠 LlamaIndex 层产出再上报平台。

**4. RAG/索引/重排/向量库**：矩阵三行涉 RAG——langfuse/opik 的 SDK 均声明支持 LangChain/LlamaIndex 集成（自动埋点）；无向量库内容。

**5. 卡内链接内容摘要**：无外部 URL，全部 F 卡回溯；待补项含"三框架 OTel 兼容性对比""与 LangChain/LlamaIndex 集成深度对比"。

**6. 对 EDU 的可执行判据**：
1. **EDU 评估平台选型按矩阵口径**：要生产监控+OTel（EDU 已有 OTLP 待办 O1-②）→langfuse；要评估深度+Prompt 优化→opik；要交互调试+MCP→phoenix。EDU 的 OTel 路线与 langfuse 最顺。
2. **生产 trace 反哺评估集是免费标注**：EDU chat 的真实学生问题流，按三平台共性能力定期导出为评估数据集，替代人工造题。
3. **ELv2 协议注意**：phoenix 若进 EDU 商业交付需法务过目（禁止托管竞争服务条款）；langfuse MIT/opik Apache-2.0 无此忧。
4. **LLM-as-judge 用平台实现而非自研脚本**：judge 提示词版本化+人工抽检校准是平台已解问题，自研会陷入"judge 本身没评估"的无底洞。

---

## 八、P-002-context-discipline——上下文纪律（像管内存一样管上下文窗口）

**1. 核心定位**：模式卡（2026-09-05 自 vault① 迁入，内容原样保留）。主张：上下文是 agent 唯一工作内存，稀缺资源，必须主动管理而非被动堆积。

**2. 机制细节（卡内纪律全表）**：
- 来源 1 = S-002（12-Factor Agents）因子 3/9/10/12/13：**因子 3 Own your context window**（主动决定什么进上下文，别让框架默认行为替你决定）；**因子 9 Compact errors into context**（错误压缩成"一句可行动原因"再进上下文，全量日志污染窗口）；**因子 10 Small, focused agents**（一子任务一窗口，不做万能大 agent）；**因子 12 Stateless reducer**（agent 做成无状态归约器，状态外置、上下文可随时重建）；**因子 13 Pre-fetch context**（任务开始批量预取，不在循环里反复取）
- 来源 2 = S-001（Anthropic Building Effective Agents）：**每一步必须从环境获取 ground truth**（工具结果/代码执行）评估进展，真实反馈进上下文而非 agent 自我想象；规划步骤显式展示便于审查

**3. 记忆效果评估与基准**：无（模式卡，不涉基准）。但注意其与记忆三卡的隐含对齐：mem0 的"最近 10 条消息=工作上下文、提取事实=长期记忆"正是"own your window + 状态外置"的工程实现。

**4. RAG/索引/重排/向量库**：无直接内容；"pre-fetch context"与 RAG 检索时机的张力（预取 vs 按需检索）卡内未展开。

**5. 卡内链接内容摘要**：卡内引用为 vault 内部双链 S-002-12-factor-agents、S-001-building-effective-agents（源笔记，非本次清单，未展开精读）；无外部 URL。待补项："各真实框架的 compaction 实测策略（claude-code/opencode 画像蒸馏后增补）"。

**6. 对 EDU 的可执行判据**：
1. **EDU chat 每步先答"这一步之后上下文该剩什么"**：设计 chat 管线时以"删什么"为第一问题，不是"还要加什么"。
2. **工具报错进上下文前先压缩**：EDU 的 RAG 检索失败/LLM 超时错误，蒸馏成一行原因+建议再回填 SSE 流，不灌原始 stack。
3. **多任务不共用 session**：EDU 的 session_id 应绑定单一学习任务/答疑主题，跨主题开新会话（对应 chat SSE 契约的 session 语义）。
4. **状态外置可重建**：EDU 学生会话状态全部落库（已有 history 接口），任何时刻可从 DB 重建上下文——与现有架构一致，保持住。
5. **拒绝"自我汇报式"进展**：EDU 批处理任务（批量出题/批改）进度判定取真实产物计数，不信 agent 自述。

---

## TOP10 最锋利判据（跨卡浓缩）

1. **记忆三范式一句话选型**（M-001）：向量检索快（mem0）/图谱可推理（graphiti）/Git 可回滚（letta）——按问题类型选范式，非按流行度。
2. **mem0 V3 管道是在线记忆的工程上限模板**：单次 LLM 调用同时完成提取+ADD/UPDATE/DELETE 决策+旧记忆关联（main.py:916-1028）；在线链路记忆写入成本的天花板设计。
3. **UUID→整数 anti-hallucination 是必抄防骗术**（main.py:933-938）：凡让 LLM 引用已有记忆 ID，只暴露整数索引。
4. **graphiti 重排三配方是全 vault 最完整重排方法论**：RRF 融合（无中心节点）/NodeDistance（有中心节点）/CrossEncoder 精排（高级默认）——可直接移植到任何 RAG。
5. **LOCOMO 在整个 vault 零命中**（grep 实证；DeepWiki mem0 页亦无）：任何"mem0 过 LOCOMO"的说法在本库无据，引用需外部溯源。
6. **cognee eval_framework 是唯一可复现记忆基准 harness**：HotPotQA/Musique/TwoWikiMultiHop + DeepEval LLM-judge + EM/F1/ContextCoverage + bootstrap_ci(10000, 95%) + seed=42——EDU 建记忆评估直接抄此四步链。
7. **检索指标标准答案在 LlamaIndex metrics.py（行号实测）**：HitRate:29 / MRR:96 / NDCG:372-427，DEFAULT_METRIC_KEYS=["hit_rate","mrr"]（notebook_utils.py:9）；权威口径另接 BEIR（beir.py 出 NDCG@k/MAP/recall/precision）。
8. **faithfulness=逐句 yes/no 的 LLM-judge**（faithfulness.py:98，"Information/Context 是否支持"模板）：教学场景幻觉防线，抽样可跑。
9. **letta 的 Git 审计是记忆评估缺失时的替代维度**：不可回滚=不可信；EDU 记忆变更至少要有 append-only 审计表。
10. **上下文纪律五因子**（P-002）：own window/compact errors/small agents/stateless reducer/pre-fetch——每步先问"之后该剩什么"，错误压缩后进窗，状态外置可重建。

## 四专题结论

### 专题①记忆效果评估怎么做（用户点名）
- **卡内真相**：mem0/graphiti/letta 三卡 arch-evals 一致结论是 **OSS 版评估皆薄、无标准化基准**（mem0 evaluation/ 空壳——本次本地 find 实证；graphiti 只有 is_correct+reasoning 的 judge 提示词模板 + token_tracker；letta 只有集成测试+Git 审计维度）。三卡均带"是否有独立评估脚本"待补项。
- **LOCOMO**：全 vault grep 零命中，DeepWiki mem0 页亦无——库内不存在 LOCOMO 论述；"letta 的记忆基准"同样不存在（只有集成测试）。禁止在无外部溯源时引用"mem0 LOCOMO SOTA"类说法（厂商博客口径，库内标 UNVERIFIED）。
- **唯一实装**：cognee eval_framework（README 实证）——memory-quality benchmarking 四步链、HotPotQA/Musique/TwoWikiMultiHop、direct_llm/deepeval 双引擎、EM/F1/context_coverage/rubric/GEval-correctness/contextual_relevancy、bootstrap 置信区间、seed 复现；LongMemEval 有适配钩子（比 LOCOMO 更可落地的长程记忆基准）。**方法论**：LLM-judge 要带 reasoning（graphiti 模板）或用 DeepEval GEval 封装；评估要带置信区间与固定 seed；数据集从生产 trace 回灌（M-006 三平台共性）。

### 专题②向量库选型（用户点名）
- **库内无 Milvus/Qdrant/pgvector/Weaviate 的任何性能/功能对比结论**（grep+全卡精读确认）。存在的信息只有三类：①集成广度列举（mem0 28 个向量库含 qdrant/weaviate/milvus/pgvector；LlamaIndex 30+；均无选型依据）；②默认搭配信号（Dify docker-compose 默认捆绑 weaviate；cognee 主推嵌入式 LanceDB + 内置 Kuzu 图库；LangChain partners 列 chroma/qdrant）；③矩阵"提供商生态"行纯转述。
- **可执行结论**：本库不能回答"选哪家"；选型判据应外置——部署形态（嵌入式 LanceDB/复用现有 PG 则 pgvector/独立服务则 Milvus/Qdrant）、运维成本（EDU 已自运维 MySQL+Redis，pgvector 复用 PG 生态最省）、查询能力（metadata filtering 14 操作符是 mem0 的功能标杆）。EDU 已定 BGE-M3 向量路线（AGENTS.md：查询/入库必须同 embedding），向量库本身按"复用现有基础设施"原则裁决即可，勿引库内不存在的对比数据。

### 专题③检索评估指标（用户点名）
- **hit_rate**（LlamaIndex metrics.py:29）：召回集合是否包含相关文档/节点，支持 granular（细粒度到 chunk 级）；**mrr**（:96）：首个相关结果排名倒数的均值，granular 变体同在；两者是官方 DEFAULT_METRIC_KEYS。**ndcg**（:372-427）：dcg/idcg，考虑分级相关性与位置折损；权威口径走 BEIR 集成（NDCG@k/MAP/recall/precision）。**faithfulness**（faithfulness.py:98）：LLM-judge 逐句判断"信息是否被检索上下文支持"，为本地小模型（llama3:8b）有特化模板。
- **具体做法路径**（从代码反推的 EDU 落地）：标注集（query→gold node ids/reference answer）→RetrieverEvaluator.evaluate(retrieved_ids, expected_ids)→hit_rate/mrr/ndcg 出分→BatchEvalRunner 批量→结果入 test-reports 回归。生成侧另配 Correctness(1-5 分)/Relevancy/Faithfulness 三件套。cognee 侧对应端到端问答指标 EM/F1+GEval，两者层次不同：检索指标评"找得准不准"，EM/F1/faithfulness 评"答得对不对"。

### 专题④上下文纪律（P-002 深读）
- 纪律内核 = 12-Factor 五因子（own window/compact errors/small agents/stateless reducer/pre-fetch）+ Anthropic ground truth 原则（环境真实反馈，拒绝 agent 自我汇报进展）。
- 与记忆卡的暗线统一：mem0 "最近 10 条消息是工作上下文、不持久化；提取事实才是长期记忆"（F-C06-001 §arch-context）就是 own-your-window 的工业实现；letta RAM/disk 隐喻同源；LlamaIndex token_limit_fn 动态截断是工程兜底。
- 卡内缺口：真实框架 compaction 实测策略待补（claude-code/opencode 画像未蒸馏）；预取 vs 按需检索的张力未展开。EDU 落点：错误压缩回填 SSE、session 绑定单任务、状态全落库可重建——三条与现有 chat 架构零冲突，立即可执行。

## 附：本次精读的卡-码差异登记（供 vault 侧修订参考，未改动 vault）
1. F-C06-001 mem0 "evaluation/ 目录基本为空"：本地 find 实证为**完全空**（零文件），卡内 INFERRED 可升级 EXTRACTED，待补项可关闭。
2. F-C06-004 cognee 卡写评估支持"准确率/召回率/MRR/NDCG"：全仓 grep **无 MRR/NDCG 实现**，实际指标为 EM/F1/ContextCoverage/Rubric/GEval-correctness/contextual_relevancy——卡内该句超出代码证据，建议降级改写。
3. F-C06-003 letta 卡引用 integration-tests/memory-filesystem.sync.integration.test.ts：本地 pinned 克隆**无 integration-tests/ 目录**，记忆测试实际在 src/memory-confinement.test.ts、src/memory-constraints.test.ts——卡内文件路径在本克隆未复现（INFERRED 级偏差）。
4. GitHub 直链（pinned blob/tree）本次均网络拒绝（ECONNREFUSED），全部改用卡内标注的本地克隆等价核验；DeepWiki mem0 页 WebFetch 成功且与卡内"无评估内容"互证。
