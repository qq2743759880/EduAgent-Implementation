# EduAgent RAG 与 MCP 域源码审计（只读实况）

- 审计日期：2026-09-13；审计人：源码审计子代理（RAG/MCP 域）
- 仓库根：`E:\stu\project\stu\EduAgent实施手册`；下文所有 `app/...` 路径均相对 `edu-agent/`
- 方法：只读源码 + grep 交叉验证调用链，未运行任何服务。每条论断附 file:line。
- 结论速览：问题 26 条（P0×1、P1×5、P2×12、P3×8）；亮点 5 条。

---

## 一、RAG 实况架构图（文字版）

### 1.1 导入链路（写入侧）

```
POST /api/knowledge/upload            用户私有上传（任何登录用户，≤20 文件×200MB）
POST /api/knowledge/admin/upload      管理员公共上传（require_role admin/manager）
  │  app/knowledge/routers/upload.py:242-322 / 328-403
  ├─ 后缀白名单 .md/.txt/.markdown/.pdf/.docx（upload.py:51）
  ├─ 落盘临时文件（upload.py:92-122）→ MinIO edu-upload 留存 30 天 best-effort（upload.py:57-68,125-147）
  ├─ 建任务双写：MySQL knowledge_import_task（真相源）+ Redis edu:knowledge:task:{id} TTL 24h
  │    app/knowledge/task_store.py:31-55,111-120
  └─ BackgroundTasks → _process_import（upload.py:150-227）→ anyio 线程跑管道
       run_import_pipeline（app/knowledge/importer/pipeline.py:137-143）
       LangGraph 线性串：parse → chunk → contextualize → embed → load → graph_build
         （pipeline.py:79-97；langgraph 缺失时降级 LinearImportPipeline pipeline.py:103-131）
       ├─ parse    parser.parse_node：course_intro/questions/generic 三种正则解析
       │            （app/knowledge/importer/parser.py:177-209；readers.py:89-128 两级文件类型检测）
       ├─ chunk    chunker.chunk_node：≤800 字符直接保留；超限按评分制选 4 策略之一
       │            （app/knowledge/importer/chunker.py:497-550）
       │            MAX=800 / TARGET=512 / OVERLAP=128 字符（chunker.py:31-35，字符非 token）
       │            策略：HEADING_BASED 两级标题 / PARAGRAPH / SEMANTIC_WINDOW 句子滑窗 / WORD_WINDOW
       │            （chunker.py:55-111,162-186,189-250,253-278；评分矩阵 chunker.py:312-413）
       ├─ contextualize  task30 上下文前缀（Anthropic Contextual Retrieval），LLM 生成 50-100 token
       │            前缀写 content、原文存 raw_content；失败逐条降级（contextualize.py:132-191）
       │            ⚠ 总开关 CONTEXTUALIZE_ENABLED 默认 False（app/config.py:483）→ 默认空转
       ├─ embed    embedder.embed_node：dense 1024 + sparse
       │            （app/knowledge/importer/embedder.py:406-446）
       │            dense 三级：EMBED_BACKEND=cloud 默认云端 API（OpenAI 兼容 /embeddings，
       │              trust_env=False 直连，embedder.py:160-208）→ 本地 BGE-M3 CUDA
       │              （embedder.py:133-157）→ sha256 伪向量兜底（embedder.py:272-306，自注"检索质量极差"）
       │            sparse：jieba 分词+停用词+BM25 风格 TF 权重，term_id=md5 hash 映射
       │              （embedder.py:312-400，_term_to_id embedder.py:348-361）
       ├─ load     loader.load_chunks：Milvus upsert 到 tenant 分区，batch=200
       │            （app/knowledge/importer/loader.py:165-271；PK=zlib.crc32(chunk_id) loader.py:200）
       └─ graph_build  graph_builder：从 chunk 元数据抽 CourseSeries/Module/KnowledgePoint/QuestionTag
                    关系 → Neo4j apoc.merge（失败仅 warning，不阻断；loader 侧无对应失败上报）
                    （app/knowledge/importer/graph_builder.py:54-151,194-294,321-349）
```

### 1.2 Milvus 索引与检索结构

- Collection：`settings.MILVUS_COLLECTION`（默认 `edu_knowledge`，config.py:97；loader.py:30）
- Schema（loader.py:70-102）：`id INT64 PK`、`chunk_id/content/content_type/source_file VARCHAR`、
  `dense_vec FLOAT_VECTOR dim=1024`（IVF_FLAT + COSINE，nlist=128，loader.py:86-91）、
  `sparse_vec SPARSE_FLOAT_VECTOR`（SPARSE_INVERTED_INDEX + IP，loader.py:92-96）、
  `tenant_id/visibility` 标量列 + enable_dynamic_field 动态列（tags/keywords/series_*/question_* 等）
- 分区：`_default`（公共）/ `course_public`（task31 保留分区 loader.py:139-140）/ `user_{user_id}`（loader.py:143-162）
- 混合检索 `hybrid_search`（loader.py:274-379）：dense AnnSearchRequest(nprobe=10) + sparse AnnSearchRequest
  → `RRFRanker(k=60)`（硬编码，loader.py:335）→ output_fields 带 raw_content/context_prefix 等（loader.py:339-347）

### 1.3 查询链路（读取侧，chat）

```
POST /api/chat（非流式）/ POST /api/chat/stream（SSE）
  app/chat/service.py:331-514 / 517-701
  ├─ Agent 循环优先（USE_AGENT_LOOP=True，service.py:350-377,539-575）
  │    chat/flows/agent.py decide_plan（LLM fast 决策 need_search/query_rewrite/tool_plan）
  │    chat/flows/langgraph_agent.py：agent_node→retrieve_node→tool_node→generate_node 循环
  ├─ 回退「检索先行」：retrieve_three_channel（service.py:313-328,576-584）
  │    app/chat/retriever.py:488-571
  ├─ ① 查询改写 "_rewrite_query_by_hyde_if_enabled"（retriever.py:161-189）
  │    ⚠ 无 LLM 假设文档：仅 4 条硬编码同义词表（雅思听力/线性代数/Python 装饰器/考研数学）
  ├─ ② Milvus 双通道（retriever.py:195-261）：recall_k=max(top_k, RETRIEVER_RECALL_TOPK=150)
  │    （config.py:555）；filter_expr 排除 RETRIEVER_EXCLUDE_CONTENT_TYPES（config.py:559）
  │    asyncio.to_thread + MILVUS_SEARCH_TIMEOUT=8s 硬超时（retriever.py:508-522）
  │    租户范围：admin=None 全分区；其他=["_default","course_public","user_{id}"]（retriever.py:140-155）
  ├─ ③ Neo4j 图谱扩展（retriever.py:267-355）：jieba 真实分词取 top5 关键词→1 跳扩展≤12 实体；
  │    neo4j_run 熔断快速失败（retriever.py:346-351）
  ├─ ④ 重排 _rerank_docs（retriever.py:427-462）：
  │    sidecar http://127.0.0.1:8601/rerank（RERANK_HTTP_TIMEOUT=10s，config.py:447）
  │      → 进程内 Reranker 单例（app/knowledge/reranker.py:31-136，bge-reranker-v2-m3，
  │        transformers AutoModelForSequenceClassification，fp16，batch=16，max_len=512）
  │      → _rule_rerank 规则兜底（retriever.py:361-378）；保留 RETRIEVER_RERANK_TOPK=20（config.py:556）
  ├─ ⑤ 断崖截断 _cliff_cutoff（retriever.py:468-482）：相邻分数跌幅>cutoff_drop_ratio(默认0.40,
  │    schemas.py:108-113) 即停，final_max_k=5 上限
  └─ ⑥ 生成 generator.generate_answer/generate_stream（app/chat/generator.py:499-543,546-618）
       docs 编号 doc[1..N] 拼 prompt（generator.py:36-57，单 doc 截 1200 字符）
       RAG_SYSTEM_PROMPT strict_rag（generator.py:476-492）；LLM 失败→_local_rule_answer 规则兜底
       （generator.py:98-125）；流式 60s 无增量超时降级（generator.py:593-598）
```

### 1.4 引用溯源（citation）

- 检索 docs 全量 JSON 存 `chat_message.rag_docs_json`（service.py:466,655），响应体带
  `docs[]`（doc_id/score/content/source_file 等，chat/schemas.py:69-89）与 SSE `retrieval` 事件
  （schemas.py:178「给前端提前渲染引用区」）。
- 答案正文不做引用标注：prompt 未要求模型输出 doc[n] 角标（chat/prompts 拼装 generator.py:476-496 无
  citation 指令）；仅规则兜底答案有「引用：doc[1]…」拼串（generator.py:114-116）。前端可点引用是靠
  rag_docs_json，不是答案内锚点。

### 1.5 评估

- 离线评估器 `app/chat/rag_evaluator.py`：HitRate/MRR/NDCG/P@k/R@k（:61-120）+ task32
  「同冻结候选集 BGE-rerank vs 规则 top-20 A/B + data_hash 可复现」（:194-443）。
- ⚠ 仅被 `scripts/eval/verify_task32.py` 与 `tests/test_contract_task32.py` 引用；无路由、无定时任务、
  无 CI 门禁、无线上抽样回流（grep 全仓 `rag_evaluator` 在 app/ 内无调用方）。无 ragas 类答案忠实度评估。

---

## 二、MCP 实况架构图

```
挂载：app/main.py:526-528 include_router(mcp_router)，整路由 dependencies=[require_role([ADMIN])]
  app/mcp/router.py:40-44，prefix=/api/mcp

管理面（全 admin-only）：
  POST/GET/PATCH/DELETE /servers          CRUD（registry.py:26-168，软删 yn=0）
  POST /servers/import-url                一键导入：data://test-stdio 打靶副本 或 https→SSE
                                          （router.py:128-203；SSE 导入默认 enabled=0 router.py:183）
  POST /servers/{id}/health               initialize+ping / SSE GET（executor.py:1237-1313）
  POST /servers/{id}/discover             initialize+tools/list → upsert mcp_tool（executor.py:1316+，
                                          registry.py:246-281）
  POST /description-review                工具描述体检：规则打分 0-100，<70 分 FAST 重写 + 审计日志
                                          （router.py:238-266；registry.py:287-373；description_reviewer.py）
  POST /tools/test                        测试调用 → executor.call_tool（router.py:272-287）
  GET  /call-log, /call-log/{id}          调用审计日志分页/详情（router.py:293-375）
  GET  /servers/{id}/discover-live、POST raw-rpc、health-scan(-async)、/sessions CRUD、/console UI
                                          （router.py:381-535；会话池 stdio 长连接 checkpoint）

传输层（executor.py）：
  stdio：asyncio.create_subprocess_exec + Content-Length 帧协议（executor.py:138-193,212-328）
  sse/http：httpx 优先 aiohttp 备选，POST JSON-RPC tools/call（executor.py:331-364,1202-1223）
  ⚠ 无 streamable-http/SSE 长连接语义——sse/http 实际都是一次性 POST JSON-RPC；
    stdio 每次 tools/call 全新 spawn+initialize（executor.py:1166-1183），会话池仅用于
    健康检查（MCP_HC_USE_POOL executor.py:1250-1252）与 admin 调试 /sessions

调用入口（chat 集成）：
  路径A 启发式：chat/tool_calling.py run_chat_tool_calls（service.py:391,544 并行触发）
    list_enabled_tool_metas：mcp_tool JOIN mcp_server 全量 yn=1+enabled=1（tool_calling.py:45-68）
    正则/关键词匹配 add/ping/echo/list_alphabet（tool_calling.py:97-189）
    → executor.call_tool(tool_id=..., args=...)（tool_calling.py:265-271，签名正确）
    结果注入 system prompt（inject_mcp_into_system_prompt tool_calling.py:349-353）
  路径B LLM 决策：chat/flows/agent.py execute_tool_plan（:151-216）
    → executor.call_tool(tool_name=..., arguments=...)（agent.py:184-187）
  路径C langgraph tool_node：chat/flows/langgraph_agent.py:280-283 同样 arguments= 调法
  路径D 子代理服务：ai/graph.py:447-456 call_tool → call_tool_with_retry(tool_name=..., args=...)

可靠性/治理（已落地）：
  per-server 熔断：连续 5 失败→30s OPEN 快败（executor.py:40-41,78-88；core/breaker）
  只读工具 60s 同参缓存：get_or_load + 写语义前缀跳过（executor.py:43-45,91-103,539-555）
  审计：每次调用 upsert mcp_tool_call_log（含 ERROR/TIMEOUT，executor.py:1396-1430）
  重试闭环 call_tool_with_retry：换参(LLM 改写)→换工具(TOOL_FALLBACK_MAP)→熔断→人工指南
    （executor.py:1002-1154；状态机 retry_loop.py；拒绝计数 Redis/Mem executor.py:740-792）
  HITL 护栏 seam：高风险工具名分类→run_hitl_gate（executor.py:48-73,374-464,489-501）

声称已落地但生产零接线（死代码，grep 全仓仅定义文件自身引用）：
  ✗ app/mcp/auth.py        OAuth2/API-key 注入（build_auth_headers/OAuthClient）——executor 无 import
  ✗ app/mcp/reconnect.py   自动重连 with_reconnect——无任何调用
  ✗ app/mcp/isolation.py   子代理 mcpServers 隔离 + truncate_tool_result——无任何调用
  ✗ app/mcp/dynamic_update.py DynamicToolRegistry 工具变更监听——仅 __init__.py 提及
  （deferred.py 延迟加载是唯一被真实使用的：description_reviewer.py 引用其 build_summary_listing）

安全现状：
  工具 allowlist：无（只有 server.enabled 开关 + 前端决策 prompt 层 admin_only 过滤 ai/tool_specs.py:221-222）
  用户权限：chat 链路调 call_tool 只带 operator_user_id 做审计，无角色/用户级工具授权
  HITL：默认 False（config.py:426）→ 高风险工具执行前无强制人工门
```

### 交叉：RAG 与 MCP 的重叠/断裂

- **`search_knowledge` 存在两套同名实现且互不相通**：
  1. MCP 内置工具 `executor.py:662-677`：`_SEARCH_KNOWLEDGE_BACKEND` 注入点 `set_search_knowledge_backend`
     （executor.py:636-638）**全仓无任何调用**（grep 仅定义+提示文本）→ 永远返回
     `{"results":[], "degraded":true, "note":"知识检索后端未接入"}`（executor.py:669-673）。
  2. LangGraph 子代理服务 `ai/graph.py:425-454`：真接 `retrieve_three_channel` 三通道检索。
  - 即：知识库检索**没有**作为可用 MCP 工具暴露；MCP 侧是个空壳占位。
- `TOOL_FALLBACK_MAP`（config.py:404-408）把 `search_knowledge/calculator` 当兜底工具，但按名解析在
  registry 不被支持（见问题 3），该兜底链对 DB 注册工具与内置工具均走不通。

---

## 三、自曝问题清单（26 条）

严重度定义：P0=数据损坏/越权写；P1=功能性断裂/越权读/契约虚标；P2=质量/性能/安全隐患；P3=死代码/卫生。

| # | 严重度 | 问题 | 证据 |
|---|--------|------|------|
| 1 | **P0** | **chunk_id 非全局唯一 → Milvus PK（crc32）跨文件/跨租户碰撞，upsert 静默覆写他人数据**。generic 解析 chunk_id=`{source_file}_{idx}`（source_file 只是文件名），course 解析 chunk_id=`course_{idx:03d}` 连文件名都不含；两个用户上传同名文件、或任何两个课程格式文件，PK 必然相同。models.py:71 声称"chunk_id 全局唯一"，该不变量被解析器自己违反 | parser.py:160,62,200-204；loader.py:200（PK=crc32(chunk_id)）,258-264（upsert）；models.py:71 |
| 2 | **P1** | **Agent/LangGraph 工具调用 100% 静默失败**：`call_tool(tool_name=..., arguments=...)` 用了不存在的关键字 `arguments`（实参名是 `args`），且把返回的 pydantic `MCPToolTestResp` 当 dict `.get()`。TypeError 被裸 except 吞成一条 warning → 路径 B/C 的 MCP 工具执行在生产必失败。契约测试是用 monkeypatch 假 call_tool 造的，测不出 | agent.py:184-193（`arguments=args`）,209-215（吞异常）；langgraph_agent.py:280-289；executor.py:465-478（真实签名 `args`）；tests/test_contract_task_o1_instrumentation.py:105-107（fake 签名与生产一致地错） |
| 3 | **P1** | **工具按名解析不存在**：`get_tool_by_ref` 只接受 tool_id 或 server_id+tool_name；`call_tool_with_retry` 入口即按名解析失败直接返回 ERROR。导致 TOOL_FALLBACK_MAP 兜底链（calculator/search_knowledge）与内置工具注册（executor.py:676-677）在重试闭环主路径永远到不了 `_default_attempt_executor`——"内置工具优先命中"的设计被入口解析短路 | registry.py:211-232；executor.py:1029-1037；executor.py:684-710（设计注释自认解决 400，实际入口更早拦截）；config.py:404-408 |
| 4 | **P1** | **任务状态查询 IDOR（代码自曝）**：`GET /api/knowledge/status/{task_id}` 任何登录用户可查任意任务（含 tenant_id、源文件名、错误详情），docstring 自认"先放宽可查，生产加字段"，未加 | upload.py:432-445 |
| 5 | **P1** | **MCP task95 四模块死代码，能力虚标**：auth.py（OAuth/API-key）、reconnect.py（自动重连）、isolation.py（子代理隔离+结果截断）、dynamic_update.py（动态工具更新）在生产链路零调用（grep 全仓仅定义文件自身）。executor 实际不注入 OAuth 头、不重连、不隔离；HTTP 传输只是透传 http_headers_json | auth.py 全文；reconnect.py 全文；isolation.py 全文；dynamic_update.py 全文；executor.py import 区 13-33 无这些模块；grep `with_reconnect/resolve_subagent_tools/truncate_tool_result/OAuthClient` 仅命中定义文件 |
| 6 | **P1** | **MCP 侧 `search_knowledge` 空壳**（详见交叉节）：backend 注入点无调用方，MCP 工具调用知识检索永远返回空降级结果，与 ai/graph.py 的真实现断裂 | executor.py:632-638,662-673,676-677；ai/graph.py:425-454；grep `set_search_knowledge_backend` 全仓 0 调用 |
| 7 | P2 | **查询改写名不副实**：所谓 HyDE 是 4 条硬编码同义词字符串拼接（雅思听力/线性代数/Python 装饰器/考研数学），无 LLM 假设文档、无多查询（multi-query）改写；注释自认"简化实现…可在这里调用 FAST 模型" | retriever.py:161-189（词表 :176-181） |
| 8 | P2 | **规则重排用稀疏 term_id（md5 整数串）当词匹配正文，命中数恒≈0**：`build_sparse_vector(query).keys()` 是 hash id 不是中文词；graph_expand 通道已修过同类 bug（:285-288 注释自认），`_rule_rerank` 未修 → 兜底重排退化为长度偏置打分，"质量不劣于现状"的降级承诺不成立 | retriever.py:366,371-377；对照修复注释 retriever.py:285-288 |
| 9 | P2 | **RAG 评估孤岛**：evaluator 无路由/定时/CI 接线（app 内零调用方），无 ragas 类忠实度/答案质量评估；线上检索质量变化只能靠人肉跑脚本 | rag_evaluator.py 全文；grep `evaluate_retrieval/compare_rerank_vs_rule` 仅 scripts/eval/verify_task32.py + tests |
| 10 | P2 | **嵌入三级兜底静默污染索引**：最终兜底 sha256 伪向量照常入库（自注"检索质量极差"），维度不符静默截断/补零；伪向量行无任何 Milvus 侧标记 → 查询端/文档端可能不同模型不同维度仍"成功"，破坏"两端同模型"约束且不可发现 | embedder.py:272-273（伪向量）,199-205,276-282（pad/trim）；对照 AGENTS.md 教训 7 |
| 11 | P2 | **Contextual Retrieval 默认关闭**：CONTEXTUALIZE_ENABLED=False，task30 声称的召回失败率 -35% 在默认配置下完全不生效；开启还需运维确认模型预算（config.py:481 注释自认） | config.py:481-485；contextualize.py:133-135（enabled=False 直接 return） |
| 12 | P2 | **检索超参硬编码/相对归一化无质量底线**：RRF k=60 写死（loader.py:335）、nprobe=10 写死（loader.py:318）；rerank 分数 min-max 归一化是每查询相对值（retriever.py:386-393）+断崖只看相邻跌幅（retriever.py:468-482）→ 全差结果集照样放行 top1，无绝对分阈值 | loader.py:318,335；retriever.py:386-393,468-482 |
| 13 | P2 | **chat 工具触发无用户级授权/allowlist**：`list_enabled_tool_metas` 拉全部启用工具（SQL 无 admin_only 列/过滤），启发式命中关键词即以当前用户身份调任意"无 required 参数"工具；admin_only 只在决策 prompt 层过滤；HITL 默认 False，高风险名前缀门不生效 | tool_calling.py:45-68,171-189；ai/tool_specs.py:221-222（仅 prompt 层）；config.py:426；executor.py:489-501 |
| 14 | P2 | **HITL 分类靠工具名子串**："url" 子串即判 network_access（会误伤含 url 的只读工具），写语义仅认 7 个前缀——非前缀写工具（如 submit_xxx）既不缓存豁免也不过 HITL | executor.py:45,51-55,58-73,91-96 |
| 15 | P2 | **60s 同参缓存对非前缀写工具生效**：缓存豁免只看 `_WRITE_TOOL_PREFIXES` 前缀，名字不含 write/create/delete/update/send/broadcast/upload 的副作用工具结果会被缓存 60s，二次调用副作用丢失 | executor.py:43-45,91-103,539-555 |
| 16 | P2 | **stdio 工具调用每请求 spawn 子进程+全握手**：会话池只服务健康检查与 admin 调试，chat 路径的 call_tool 每次 spawn+initialize+tools/call，高并发下延迟与句柄开销大 | executor.py:1166-1183（每次 _stdio_exchange_async）；pool 仅 executor.py:1250-1252,1531-1647 与 router /sessions |
| 17 | P2 | **SSE/HTTP 健康检查把 4xx 当健康**：`ok = (200 <= status < 500)`，401/403/404 的 server 被标记健康 | executor.py:1287,1297 |
| 18 | P2 | **知识库无文档级删除/更新**：只有整分区 drop（upload.py:478-497），无按 source_file 删 chunks；重新上传改名/改结构的文件后旧 chunk 成孤儿向量，永远参与检索 | upload.py 路由清单（仅 upload/tasks/status/partitions）；loader.py 无 delete-by-source |
| 19 | P2 | **上传无用户配额**：普通用户单次 20 文件×200MB、管理员 50×200MB，无频率限制/总配额；并发上传可打满 DATA_DIR 磁盘与任务表 | upload.py:49-50,256-257,341-342 |
| 20 | P3 | **任务 total_chunks 魔法数**：`len(files)*20` 粗估写库，跑完才回写真实值 | upload.py:299,381 |
| 21 | P3 | **双检索实现并存**：knowledge/retriever/retriever.py 的 KnowledgeRetriever 生产未用（chat/retriever.py:501 自注"留作后用"），且 admin=搜索全部分区（含所有用户私有）、_filter_private_data 是取回后过滤而非检索期过滤 | retriever/retriever.py:62-83,86-116；chat/retriever.py:498-501 |
| 22 | P3 | **影子采样注释称"确定性"实则进程内随机**：`hash(query)` 依赖 PYTHONHASHSEED，跨重启不可复现 | retriever.py:58-64 |
| 23 | P3 | **MCP 敏感配置明文落库且详情原样返回**：env_json/http_headers_json（可含密钥）明文存 MySQL，GET /servers/{id} 自述"含敏感字段"无脱敏 | registry.py:29-30,114-116,144-145；router.py:73-79 |
| 24 | P3 | **调用审计 args/result 全量落库无脱敏**：mcp_tool_call_log.args_json/result_json 存完整出入参（与 P3-23 同为 admin 可见，但敏感数据无最小化） | executor.py:1401-1415,1417-1428 |
| 25 | P3 | **会话池 GC 无定时器**：仅 admin 打开 /sessions 列表或新建会话时触发；被遗忘的 stdio 子进程可持续存活 | router.py:461-464；executor.py:1548-1549 |
| 26 | P3 | **死代码/小问题**：`_estimate_tokens` 定义后从未使用（分块全程按字符数非 token）；图构建 APOC 缺失时降级为粗粒度 GRAPH_LINK，与 apoc 路径图谱语义不一致且任务状态不体现 | chunker.py:38-42；graph_builder.py:285-315,344-348 |

---

## 四、亮点清单（5 条，同样带证据）

1. **检索级联完整且超参可配**：150 召回（RETRIEVER_RECALL_TOPK config.py:555）→ BGE 重排 top20
   （config.py:556）→ 断崖截断 → final_max_k=5；Milvus 真·混合检索 dense IVF_FLAT/COSINE + sparse
   SPARSE_INVERTED_INDEX/IP + RRFRanker（loader.py:84-96,313-348），filter_expr 同时作用于两路
   （loader.py:289-291,315-329）。
2. **全链路降级纪律执行到位**：Milvus/Neo4j/reranker/LLM 每级失败都产出 degraded_reason 并汇聚到响应体、
   指标（record_degraded retriever.py:544-560）与 RAG 审计日志（service.py:477-492,666-681 →
   admin/rag_admin/service.py:451+），LLM 宕机也有规则兜底答案不 500（generator.py:98-125,536-543）。
3. **MCP 治理面（管理侧）完备**：每次调用幂等 upsert 审计（含 ERROR/TIMEOUT，executor.py:1396-1430）、
   per-server 熔断 5 次/30s（executor.py:40-41,78-88）、工具描述体检打分+<70 分 FAST 重写+专属审计表
   （router.py:238-266；registry.py:287-373）、健康检查异步化带弃用头（router.py:398-442）。
4. **rerank sidecar 连续批处理**：GPU 独立进程 8601（rerank_service/main.py:5-9）、跨请求攒批
   （batcher + RERANK_BATCH_WINDOW_MS/MAX_BATCH_PAIRS，config.py:443-447）、sidecar→进程内→规则三级降级
   且降级原因如实标注（retriever.py:427-462）。
5. **导入任务可靠性设计**：MySQL 真相源 + Redis 24h 热缓存双写、Redis 故障吞掉降级不阻断
   （task_store.py:4-17,111-120）；MinIO 30 天生命周期 best-effort（upload.py:53-68）；LangGraph 管道节点
   失败不互相阻断、langgraph 缺失自动退化线性执行器（pipeline.py:37-61,103-131）。

---

## 五、TOP5 严重问题（审计人裁定）

1. **#1 P0 chunk_id/PK 碰撞跨租户覆写**（parser.py:160,62 + loader.py:200）——多租户"物理隔离"承诺被
   主键设计直接击穿，属数据损坏级。
2. **#2 P1 Agent 工具调用签名错误 100% 静默失败**（agent.py:184 / langgraph_agent.py:280）——LLM 决策
   路径的工具能力实为不可用，测试 monkeypatch 掩盖了它。
3. **#3 P1 工具按名解析缺失**（registry.py:211-232 + executor.py:1029-1037）——重试闭环/兜底链/内置工具
   三套设计被入口短路，闭环退化为人工指南。
4. **#4 P1 任务状态 IDOR**（upload.py:432-445）——代码注释自曝的越权读，一行属主校验缺失。
5. **#5+#6 P1 MCP 能力虚标与 RAG-MCP 断裂**（auth/reconnect/isolation/dynamic_update 死代码 +
   MCP search_knowledge 空壳）——"对标 Claude Code"的五大能力中四个未接线，知识库检索未作为
   MCP 工具暴露，两域只在启发式 add/ping/echo 层面相连。
