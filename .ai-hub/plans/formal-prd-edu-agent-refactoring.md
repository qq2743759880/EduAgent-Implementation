# PRD: EduAgent 系统级重构(批判承接版 v1.0)

> 依据:六份审计/精读报告(audit-edu-rag-mcp 26 条、audit-edu-chat-langgraph 23 条、kb-benchmark 65 判据、kb-deep 1-3)+ 2026-09-13 定向复扫(病灶行号零漂移)。规划红线=用户三条守则(批判 1:1 承接/强对标 KB/12-factor+ACI)。

## 1. 需求总览:崩溃点 → 目标全景

**当前崩溃面**(源码实证):Agent 内核三处断电——记忆管线生产不通电(main.py lifespan 无 start_memory_worker 调用,队列 LPUSH 后无人消费)、流式主路径绕过 9 节点 LangGraph 图(chat/stream → 普通函数直连)、chunk_id 三形态碰撞(course_{idx} 连文件名都不含 → crc32 PK 跨租户覆写);工具层系统性虚标——call_tool 关键字签名错用致 100% 静默失败且被 monkeypatch 假测试掩盖、TOOL_FALLBACK 链因按名解析缺陷永不可达、search_knowledge MCP 空壳与真实检索两套互不相通;质量层无护栏——RAG 评估离线孤岛、无 hit_rate/mrr/faithfulness 基线、伪向量静默入库。

**修复后全景**:用户走的每一条 chat 请求都流经 LangGraph 图(checkpoint 落 Redis、可 interrupt 人审、状态通道语义显式);记忆每轮真实写入/召回(user_memory 落库、失败可见不静默);知识块全局唯一(租户+内容哈希);工具调用真执行(call_log 可审计、权限门可拦、错误即行动指南);检索质量有回归护栏(改参数必跑指标基线);每 turn 有结构化 trace。

## 2. Phase 1:核心链路抢修(P0/P1,先接电流再堵漏)

| ID | 模块/函数设计 | 承接批判 |
|---|---|---|
| R01 记忆 worker 通电 | main.py lifespan 启动段调 start_memory_worker()、关闭段 stop;启动失败仅 WARN 不阻断主服务(与存储初始化同语义);worker 消费循环异常自愈。含 mem0 两要点落地:召回注入前 ID→序号映射防幻觉;LLM 处理失败显式落 degraded 队列项而非静默空列表 | P0-记忆失效 |
| R02 流式进图 | /api/chat/stream 改走 graph.astream(stream_mode 兼容适配),产出映射为既有 SSE 事件序列;**SSE 契约(reshape-a.json 冻结)前端零改动**;graph 内 guard.acquire/release 恢复护主路径;流式检索引用真实回填 | P0-绕图+P1-guard 不护流式 |
| R03 chunk_id 唯一化 | 新格式 `{tenant}:{sha256(content)[:16]}:{seq}`(parser.py:62/125/160 三处);Milvus collection schema v2 增 scalar 字段;迁移脚本 dry-run/execute 双模式(**SQL 一律参数绑定,禁 f-string 拼接**);读侧新旧 ID 共存兼容窗口 | P0-碰撞 |
| R04 MCP 调用契约修复 | call_tool(arguments=→args=,pydantic 返回显式 model_dump;契约测试重写:删 monkeypatch 假 call_tool,改打真实 stdio-echodemo server 断言 call_log SUCCESS;按名解析补 registry 支持(get_tool_by_ref 名称路径)使 TOOL_FALLBACK 链可达 | P1-假调用+假测试+链不可达 |
| R05 死代码清除 | task95 四模块(auth/reconnect/isolation/dynamic_update)、flows/langgraph_agent.py 500 行(含 user_id=1 越权写法)、execute_tool_plan:本 PRD 未接线者一律删除(git 可回溯),禁"留着以后接" | P1-虚标+越权残留 |
| R06 _rule_rerank md5 bug | term_id md5 当词匹配正文(retriever.py:366)→对齐 graph_expand 已修方案 | P1 |
| R07 数据完整性小修 | 嵌入失败 sha256 伪向量→拒绝入库+degraded 标记;GET /api/knowledge/status/{task_id} 补属主校验(参数绑定) | P1-伪向量+IDOR |

## 3. Phase 2:Agent 架构对齐(KB 最佳实践)

| ID | 设计 | KB 对标 |
|---|---|---|
| R10 状态通道语义重构 | 状态 TypedDict+每字段 Annotated 通道语义(检索结果 Binop 合并防覆盖);run_agent 硬编码空 docs/graph_entities 修复为真实回填 | [F-C01-002] Channels+非流式引用丢失 |
| R11 HITL interrupt | 危险工具(写类/外发类)interrupt() 暂停,SSE 增 pending_confirm 事件;Command(resume) 恢复,thread_id 绑定 | [F-C01-002] interrupt 三件套标配 |
| R12 LLM 工具决策接管 | RULE_ROUTING_ENABLED 默认 False;decide_agent_plan 产出 tool_plan → 真实 executor(依赖 R04);规则路由降级为回退开关 | [P-001] 停止"为省 token 而裸奔" |
| R13 停止条件四件套 | max_iterations 上限+完成判据+文本信号+外部信号,图级统一 | [F-C02-001] autogen 终止条件 |
| R14 search_knowledge 统一 | set_search_knowledge_backend 真调用注册真实检索 → 知识库作为 MCP 工具可被 agent/外部消费;删除 ai/graph.py 内重复包装 | [P-003][F-C03-001] 资产单一真相源 |
| R15 工具权限门+ACI | per-user/role 工具 allowlist(默认 deny 写类);错误信封 {code,message,action_hint}——错误本身是可行动 prompt(Poka-yoke);HITL 门与 R11 共用声明 | [F-C03-001] CanUseToolFn+[P-003] ACI |

## 4. Phase 3:评估与观测基建

| ID | 设计 | KB 对标 |
|---|---|---|
| R20 检索指标评估器 | hit_rate/mrr(对齐 LlamaIndex metrics.py 口径)+ eval_set32 基线集;输出 JSON 报告 | [F-C07-001] RetrieverEvaluator |
| R21 faithfulness 判官 | 逐句 yes/no LLM-judge 幻觉检测,纳入同一报告 | [F-C07-001] |
| R22 评估进 CI | pytest 标记 @rag_eval;改检索参数(RRF k/nprobe/rerank)必触发;基线阈值失败即 exit 1 | [F-C06-004] cognee eval_framework 复现纪律 |
| R23 三因子重排 opt-in | 核实/补充 Milvus scalar 时间戳 → recency 指数衰减+importance 加权与 RRF 融合(开关默认关,实验对比);真 HyDE(假设文档生成)opt-in 替换同义词表 | [F-C02-005] retrieve.py 三因子公式 |
| R24 trace JSONL | 每 turn 落 trace_id/节点耗时/工具调用/检索计数/降级原因,logs/trace/*.jsonl+轮转;OTLP 导出保持既有登记 | [S-002] Factor 11+12 |

## 5. 安全与合规设计(横切)

- **权限门禁**:R15 allowlist(角色×工具矩阵,默认最小权限)+R11 HITL(危险操作人审)。
- **沙箱隔离**:coding 判题已子进程隔离(H-1 完成);后续容器级归 C 全量(登记)。
- **防幻觉**:R01 记忆 ID 序号映射;R21 faithfulness 专测;引用回填(R10)使答案可溯源。
- **数据红线**:全程禁 DB 直写(既有纪律);**所有 SQL 参数绑定,禁拼接/format/f-string**(Mimosa 硬约束);迁移先 dry-run。
- **注入防御基线**:外部知识块注入 prompt 前加隔离标记(来源+边界),工具结果同样(随 R04 落)。

## 6. 批判 1:1 承接总表(守则 1 闭环证明)

P0×3:记忆失效→R01|流式绕图→R02|chunk 碰撞→R03。P1×10:假调用→R04|假测试→R04|FALLBACK 不可达→R04|task95 死码→R05|langgraph_agent 死码→R05|execute_tool_plan→R05|IDOR→R07|HyDE 虚标→R23|md5 重排→R06|规则路由旁路→R12。架构盲区:评估闭环→R20/21/22|纵深防御→R15/R11|可观测→R24|引用丢失→R10|ACI→R15|停止条件→R13。**49 条审计问题中 P0/P1 全量承接,P2/P2 择要 9 条承接,其余登记 tracker 后续批次。**

## 7. 验收基线(项目级)

①check-demo 9/9 维持;②chat 流式请求产生 graph checkpoint(Redis key 实证)+SSE 契约回归全绿;③记忆写入 roundtrip(提问→user_memory 新行);④同名文件双租户上传零覆写;⑤工具触发→call_log SUCCESS;⑥评估基线 JSON 产出且阈值化;⑦全量 pytest 零新增失败。
