# dev-plan: EduAgent 重构批次 reshape-r v1.0(TT 任务拆解总纲)

> 上游 PRD:formal-prd-edu-agent-refactoring.md。规划红线:批判 1:1 承接/KB 强对标/12-factor+ACI。前置复扫:2026-09-13 病灶行号零漂移实证。(历史 dev-plan.md 为 task101 时代文档,保留不覆盖。)

## 需求前提挑战
| # | Premise | Confirm |
|---|---------|---------|
| P1 | 三份冻结契约(a/a2/b)与 SSE 事件契约在重构期**禁改**;新契约只增不改旧 | agree(契约冻结纪律) |
| P2 | Phase1 七任务先于一切架构升级;"先接电流再堵漏再升级"顺序不可倒置 | agree |
| P3 | 死代码处置=删除而非注释保留(git 可回溯);未在本 PRD 接线者不留尸位 | agree(ponytail) |
| P4 | KB 对标为设计输入而非照搬:三因子/权限门等以 opt-in 或最小实现落地,实验性功能默认关 | agree |
| P5 | 全程禁 DB 直写;**一切 SQL 参数绑定禁拼接/f-string**;迁移必 dry-run 先行 | agree(Mimosa 硬约束) |
| P6 | 评估基线(hit_rate/mrr/faithfulness)一旦建立即为回归门,后续改检索参数须过门 | agree |

4 问结论:Q1 为什么现在 三处 P0 使 Agent 内核名存实亡,任何上层优化都建在断电管线上 / Q2 现状 已批判实证(49 条审计问题,病灶行号今日复扫零漂移) / Q3 窄楔子 Phase1 七抢修+Phase2 六对齐+Phase3 五基建=18 任务;不做容器化/公网/前端大改/R0 / Q4 未来适配 图/checkpoint/评估门/trace 均为长期能力资产,零废弃

## 任务分解(18 任务)

### Phase 1 核心抢修(波次 1,R01-R04/R06/R07 六任务并行——文件所有权互斥)
**R01 记忆 worker 通电**(T2 后端)
- 描述:main.py lifespan 启动段调 start_memory_worker()/关闭段 stop;启动失败仅 WARN 不阻断(与存储初始化同语义);消费循环异常自愈;召回注入前记忆 ID→序号映射(mem0 防幻觉);LLM 处理失败落 degraded 队列项不静默空列表。
- 依赖:无。契约:无新冻结(队列 key `edu:mem_queue` 既有)。
- GWT:Given Redis 在跑且服务启动;When 发起 1 轮真实 chat;Then 60s 内 user_memory 出现该轮抽取行(只读验证,参数绑定);Given 注入 worker 启动失败;Then /health 200 且日志含 WARN;Given 记忆 LLM 处理抛错;Then 队列项标 degraded 而非丢弃。
**R02 流式进图**(T3)
- 描述:/api/chat/stream 改走 graph.astream(stream_mode 适配),输出映射为既有 SSE 事件(start/retrieval/token/done/error,j.delta);guard.acquire/release 覆盖流式;灰度开关 STREAM_VIA_GRAPH(默认开,一键回旧路径);流式响应回填检索来源。文件所有权:chat service/router+graph 适配层。
- 依赖:无。契约:**C-R-SSE=沿用 reshape-a.json 冻结禁改**(前端零改动)。
- GWT:Given 流式请求;Then ①task104 SSE 契约回归全绿 ②Redis 出现该 thread 的 checkpoint key(实证 grep)③响应含 docs 来源 ④开关关闭时回退旧路径行为等同。
**R03 chunk_id 唯一化+迁移**(T3+T1)
- 描述:parser.py:62/125/160 三处改 `{tenant}:{sha256(content)[:16]}:{seq}`;Milvus collection schema v2(增 scalar:tenant_id/created_at);迁移脚本 dry-run/execute(**参数绑定 SQL**,向量原地保留仅改 PK 与 scalar);读侧新旧共存窗口。依赖:无。契约:**C-R-CHUNK 新冻结**(格式+scalar+兼容语义)→ R03 开工前。
- GWT:Given 双租户上传同名同内容文件;Then chunk 数=2×N 且 PK 零冲突;Given dry-run;Then 输出影响清单零写入;Given execute 后;Then eval_set32 抽样 top5 检索结果与迁移前一致(手动对照记录)。
**R04 MCP 调用契约修复+真测试**(T3)
- 描述:flows 内 call_tool(arguments=→args=;pydantic 返回 model_dump;registry get_tool_by_ref 补按名解析使 TOOL_FALLBACK 可达;契约测试删 monkeypatch 假 call_tool→打真实 stdio-echodemo;外部内容(知识块/工具结果)注入 prompt 前加来源隔离标记。
- 依赖:无。契约:C-R-ACI 草案(R15 冻结)。
- GWT:Given chat 触发 add 工具;Then mcp_tool_call_log 新增 SUCCESS 行(DB 只读验证);Given grep 全仓;Then 零 "call_tool(arguments";Given 重写的契约测试;Then 通过且不含 monkeypatch call_tool。
**R06 rule_rerank md5 修复**(T3)
- 描述:retriever.py:366 对齐 graph_expand 已修方案。依赖:无。
- GWT:构造含稀疏 term 的 fixture;修复后 _rule_rerank 命中数>0;单测过。
**R07 伪向量拒入库+IDOR**(T2/T3)
- 描述:嵌入失败 chunk 跳过+任务 degraded 计数;GET /api/knowledge/status/{task_id} 属主校验(参数绑定)。
- 依赖:无。GWT:Given 断嵌入后端上传;Then Milvus 无新 chunk 且任务 degraded>0;Given 用户 A token 查 B 任务;Then 403/40400;Given 本人查询;Then 200。
**R05 死代码清除**(T2/T3,波次 2)
- 描述:删 task95 四模块+flows/langgraph_agent.py+execute_tool_plan(未接线者)。依赖:R02/R04(定边界)。
- GWT:After grep 三者零引用;全量 pytest 零新增失败;diff 仅删除行。

### Phase 2 架构对齐(波次 2-3)
**R10 状态通道+引用回填**(T3) 依赖:R02。GWT:状态 TypedDict 字段带 Annotated reducer(Binop 合并);并发两轮检索 docs 无覆盖(单测);非流式响应 docs 非空(修复 graph.py:825 硬编码空)。
**R11 HITL interrupt**(T3+T4) 依赖:R02。契约:**C-R-HITL 冻结**(pending_confirm SSE 事件+resume 端点+thread_id 语义)→R11 开工前。GWT:危险工具触发→SSE pending_confirm→resume 确认→call_log 含人工确认标记;拒绝→不执行有日志;超时不执行。
**R11-F HITL 前端确认卡**(T4) 依赖:R11 契约。GWT:确认卡渲染+确认/拒绝两分支落 call_log;HTML gate=增量 diff 审查。
**R12 LLM 工具决策接管**(T3) 依赖:R04。GWT:RULE_ROUTING_ENABLED 默认 False;工具类 query 经 decide_agent_plan 产出 tool_plan 真执行;开关 True 回退旧行为(回归)。
**R13 停止条件**(T3) 依赖:R10。GWT:max_iter=3 的循环工具场景第 3 轮后图终止且输出终止原因;完成判据信号单测。
**R14 search_knowledge 统一**(T3) 依赖:R04。GWT:executor 内置 search_knowledge 返回真实检索(非空壳);ai/graph.py:425 重复包装删除后图路径回归绿;MCP 工具列表含 search_knowledge 且可被 call_tool 真调。
**R15 权限门+ACI 错误信封**(T3) 依赖:R04。契约:**C-R-ACI 冻结**(信封 {code,message,action_hint}+文案模板三例)。GWT:student 调写类工具→allowlist 拒且错误含可行动 action_hint;admin 放行;信封 schema 测试过。

### Phase 3 评估观测(波次 3-4)
**R20 hit_rate/mrr 评估器**(T3) 依赖:R03(数据稳定)。契约:**C-R-EVAL 冻结**(报告 JSON schema+阈值)。GWT:脚本跑 eval_set32 输出两指标;阈值入配置;低于阈值 exit 1。
**R21 faithfulness judge**(T3) 依赖:R20。GWT:已知幻觉 fixture 判 false、忠实 fixture 判 true;并入报告。
**R22 评估进 CI**(T5) 依赖:R20/21。GWT:pytest -m rag_eval 触发;改 nprobe 的门禁演示一次(阈值拦截实证)。
**R23 三因子重排+真 HyDE opt-in**(T3) 依赖:R20(对照)。前置:核实 Milvus scalar 时间戳现状(schema 探查)。GWT:开关开→recency 衰减参与排序(公式单测);关→零行为变化;真 HyDE 产出假设文档(非同义词表)。
**R24 trace JSONL**(T5) 依赖:R02。GWT:一轮 chat 后 trace 文件含 trace_id/节点耗时/工具调用/检索计数/降级原因;按日轮转;trace 失败不影响主流程(WARN)。

## 契约冻结顺序
C-R-SSE(已有复用)→ C-R-CHUNK(R03 前)→ C-R-ACI(R15 前,R04 凭草案开工)→ C-R-HITL(R11 前)→ C-R-EVAL(R20 前)。冻结后禁改,变更走变更单+重验收。

## 规划自审
### CEO 范围自审
- finding1:18 任务+三新契约体量偏大,存在烂尾风险。处置:三波独立交付(Phase1 自身即可验收收口),每波 review-gate+独立复验,Phase 顺序即止损线;用户可随时砍波。
- finding2:R23 实验性可能无收益。处置:opt-in 默认关+R20 基线对照,无收益登记不默认启用。
### Eng 架构自审
- finding1:R02 动用户唯一聊天入口,风险最高。处置:SSE 契约冻结+task104 回归+STREAM_VIA_GRAPH 一键回退+checkpoint 键与旧 thread 共存;灰度验证后再拆旧路径(R05 之后才删)。
- finding2:R03 迁移 2631 行存量,嵌入成本与误删风险。处置:向量原地保留仅重建 PK/scalar,dry-run 输出耗时预估与影响清单;回滚=旧 ID 数据未删(共存窗口)。confidence: medium-high(病灶行号今日复扫零漂移;Milvus scalar 现状与 R02 graph 适配细节为剩余未知,均已设前置探查步)。
### Design 体验自审
- finding1:HITL 确认卡打断高频操作会烦。处置:仅写类/外发类触发;会话级"不再确认"记忆。
- finding2:action_hint 文案不得是错误码堆砌。处置:C-R-ACI 冻结时定三例中文可行动模板并用户过目。
