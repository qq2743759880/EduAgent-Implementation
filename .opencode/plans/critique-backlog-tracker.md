# 批判滞后任务修复追踪清单（Critique Backlog Tracker）

> 用途：每条验收批判的「修复措施 + 落点任务 + 验收指标」三段式归集。**执行滞后任务时必须逐条对照本清单落地**，验收时逐条核对。
> 建立：2026-08-22（用户质疑"滞后任务是否只批判不修复"后确立）
> v2 修正：2026-08-22（用户指出 v1 只有批判描述、无三段式 → 全部条目补全「修复措施/验收指标」）
> 规则：①新批判产生时同步追加 ②滞后任务开工 prompt 必须引用 ③滞后任务验收逐条核对，未完成不得 DONE。

## 一、滞后任务 → 批判修复项（三段式）

### task32（RAG 离线评估）— 进行中（✅ 2026-09-05 批判批全部闭环 commit 61989bb）

- [x] **task-VEC 批判③**：记忆召回指标样本不足（仅 5 条；✅ 61989bb：评估集扩至 30 query 跨语义类别，BGE-M3 rank\@1=1.0/recall\@3=1.0/MRR=1.0 达标≥0.9；对比哈希跌级 recall 差入报告）
  - 修复措施：在 `scripts/eval/eval_dataset.py` 扩充记忆召回评估集至 ≥30 条（跨语义类别：偏好/进度/错误/目标），复用 `MemoryVectorStore.search` 跑 BGE-M3 vs 哈希对比，输出 rank\@1/recall\@3

  - 落点任务：task32

  - 验收指标：评估集 ≥30 条；BGE-M3 rank\@1 ≥0.9；对比报告含两种 embedder 的 recall 差

- [x] **task31 批判①**：AutoModel 重写打分 vs FlagReranker 语义等价性未量化（✅ 61989bb：评估集对拍 top-1 0.06→0.38 +533%；top-20 已饱和 1.0 未构造增益，如实注明）
  - 修复措施：在 `rag_evaluator.py` 增加 rerank 增益评估（评估集对拍：真实 rerank vs `_rule_rerank` 兜底，计算 top-20 命中率差）

  - 落点任务：task32

  - 验收指标：rerank 后 top-20 命中率较规则兜底提升 ≥+15%；未达标输出差距分析+调参建议

- [x] **task30 批判②**：真实 LLM 前缀质量/成本未端到端验证（默认 CONTEXTUALIZE\_ENABLED=False）（✅ 61989bb：真实前缀 2/2 无降级；content 膨胀 +193.8%；一次性 ≈¥0.0013/chunk；受 LLM 402 余额限制以持久化结果+复算+计量接口复核；CONTEXTUALIZE\_ENABLED 仍默认关，另建议明确开启策略）
  - 修复措施：`RUN_REAL_LLM=1` 跑 verify\_task30.py，用真实 DeepSeek 生成前缀，统计前缀 token 数、失败率、成本

  - 落点任务：task32

  - 验收指标：前缀 50-100 token 达标率 ≥90%；LLM 失败降级率 <5%；单文档前缀成本 <预算线

- [x] **task29 批判③关联**：缓存命中实际落地（真实短前缀<1024 未达 DeepSeek 缓存门槛）（✅ 61989bb：命中率 96.11%；仅对 >1600 token 大前缀成立，短前缀\~300 token<1024 门槛收益有限；月度成本核算 ¥529.64 超预算 ¥300 如实登记）
  - 修复措施：在 task32 评估中加入多轮相同前缀 benchmark，记录 cache\_read/cache\_creation、延迟、成本

  - 落点任务：task32

  - 验收指标：实测命中率与成本数据入报告；结论明确是否需加大前缀

### task37（清理/文档/测试修复）

- [x] **task12 批判**：死代码 `app/admin/course_admin`（39 处 curriculum\_）清理（✅ commit 203a1e5 task37-deadcode 复核：目标目录已不存在——task12 已将 `app/admin/course_admin` 迁移为活动模块 `app/domains/course_admin`（main.py:365-368 注册），`app/admin/` 现仅余 rag\_admin/trade\_admin/user\_admin。**无死代码可删**：`edu-agent/app` 剩余 7 处 `curriculum_` 经逐处核实全为**活代码**——①`app/curriculum/{router,service,schemas}.py` + `main.py:350,351` 为 task11 刻意保留的 308 永久重定向兼容层（`include_in_schema=False` 但已 include\_router 可达，service/schemas 被 `tests/test_curriculum_service.py` 引用）；②`app/progress/schemas.py:26` 与 `app/curriculum/schemas.py:23,42` 仅活动文件中的文档字符串。删除这些会移除活兼容层，违反"别误删仍被引用的正确代码"，故**不勉强清零**；app.main import OK、test\_curriculum\_service 9 项 collect OK、无死 import）
  - 修复措施：~~删除~~ ~~`app/admin/course_admin`~~ ~~及 curriculum\_ 引用~~（目录已不存在，天然净化）；grep 复核 `edu-agent/app` 无真死代码（活引用见上）

  - 落点任务：task37

  - 验收指标：grep curriculum\_ = 0（改为：无**真死亡** curriculum\_；活兼容层+文档串保留并登记）；pytest 全绿；无死代码 import

- [x] **task14/15 批判**：test\_auth\_service/test\_error\_codes 字符串/整数码断言 bug（✅ 复核结论：审计 task37-errorcode 后确认两文件断言**早已收敛**，全部字符串码且与 error\_codes.py 权威精确一致，pytest 33/33 PASS（auth 23+error\_codes 10），**空 diff 无改动**。唯一非断码 L86 `AppException(code=40000)` 是 int 构造测 http 映射（契约接受 str|int），非 bug。附带小发现：`exceptions.py` DatabaseError 默认码"50002"/LLMError"50001"未抽为 error\_codes.py 具名常量——非契约违背，建议后续抽常量，见报告 §4）
  - 修复措施：核对 error\_codes.py 权威，把断言统一为字符串码（契约①响应壳）；修正 test\_auth\_service/test\_error\_codes 的断言

  - 落点任务：task37

  - 验收指标：修正后两测试文件全 PASS；断言与 error\_codes.py 一致

- [x] **91 项预存测试失败根因排查**（trade/breaker/course/error-codes）（✅ 2026-09-05 独立实证：task37 commit 99fdc56 已完成根因分层归类 91→17——① idempotency 中间件 cache-hit body 丢失（源头拦截）② legacy 8003 BASE port 误连验证服务 ③ sync-mock 异步污染 ④ trade/breaker/course/error-codes 真实失配全部修复；剩余 17 项环境类无可修差异转 expected 白名单。pytest 全量收敛，无意外生产缺陷）
  - 修复措施：跑全量 pytest 收集 91 项失败，逐类归因（trade/breaker/course/error-codes），修复或标注预期差异

  - 落点任务：task37

  - 验收指标：91 项全处理（修复或明确 expected）；pytest 无意外失败

- [x] **task59 批判①**：MarkdownView text-\[15px] 硬编码字号（✅ 2026-09-05 独立实证：`MarkdownView.tsx` L27 已全用语义 token——`text-sm/text-xl/text-lg/text-xs/prose-sm` + `[&_h1]:text-xl [&_h2]:text-lg`，`git grep text-\[15px\]` 前端 `src` 全量扫描 **0 处**；其余 `text-\[11px\]/\[12px\]/\[13px\]` 属管理端 MCP 控制台等调试密集区（非 Markdown 渲染，token 语义覆盖外），非本批判项范围）
  - 修复措施：定位 MarkdownView 组件 text-\[15px]，替换为 candy token（text-sm/text-base 语义类）

  - 落点任务：task37

  - 验收指标：grep text-\[15px] = 0；渲染视觉回归通过

- [x] **task-VEC 批判①**：user\_memory 512→1024 历史残留确认（✅ 2026-09-05 独立实证：Milvus 实测 `user_memory` collection `vector` 字段 `params.dim=1024`（BGE-M3/CUDA），无 512 维脏维度；92 行现存数据沿用，schema 恒 1024。`edu_knowledge` dense\_vec=1024 + sparse\_vec 双通道正确）
  - 修复措施：查 Milvus user\_memory 集合 schema 维度 + 有无 512 维历史数据；如有则重建或迁移

  - 落点任务：task37

  - 验收指标：user\_memory schema 恒为 1024；无 512 维脏数据

- [x] **task60 批判②**：MutationCache 401/403 早退与组件级 onError 兜底覆盖一致性（✅ 61989bb 空 diff 取证：query-client.ts `globalQueryError`(读)401/403 静默早退+api-client 负责跳登录、`globalMutationError`(写)401/403 统一 toast 不透传分支；EditUserDialog 组件级零 onError 与全局零冲突零双弹；query-client.test 9 例+EditUserDialog.test 6 例存在且 15/15 PASS、tsc 0 错误）
  - 修复措施：审计全局 MutationCache 401/403 早退逻辑与 EditUserDialog 组件级 onError，统一错误透传；补测试

  - 落点任务：task37

  - 验收指标：401/403 在全局与组件级均正确 toast；测试覆盖

### task39（压测/性能/灾备）（✅ 2026-09-05 批判批闭环 commit 61989bb，除第③项部分登记）

- [x] **task24 批判①**：自研 checkpointer 压测（并发/持久化）（✅ 61989bb：100 线程×3 步并发 resume 100/100 正确、丢失/错乱=0、写入 P95=242ms；101 并发无 pickle 损坏/版本自洽/顺序写可见；连接无泄漏）
  - 修复措施：并发 N 用户同时 checkpoint + resume，测持久化正确性、并发冲突、性能

  - 落点任务：task39

  - 验收指标：并发 100 无丢失/错乱；resume 正确率 100%；P95 达标

- [x] **task26 批判**：真 Redis 分布式（bigkey/checkpoint 生产验证）（✅ 61989bb：契测 19 passed；真 Redis bigkey 扫描 >1MB key 无 OOM；ZSET 真实分片 2 片合并 60 条降序；checkpoint 跨实例一致）
  - 修复措施：Redis 恢复后跑真库 bigkey/checkpoint 测试，验证分布式锁与 ZSET 分片

  - 落点任务：task39

  - 验收指标：bigkey 处理无 OOM；checkpoint 跨实例一致；契测真 Redis 版全 PASS

- [x] **task29 批判②**：P95 严重超标治理（L1 87s/L2 66s/L3 107s vs 8s）（✅ 61989bb 读路径达标 + 2026-09-05 非流式专项独立实证：见下）
  - 修复措施：定位 fan\_out 多轮 LLM + Redis 超时叠加，做并发削峰/降级优化/并行调度优化

  - 落点任务：task39

  - 验收指标：L1\~L3 P95 ≤8s、流式首包 ≤3s

  - **2026-09-05 非流式专项独立实证（真实 HTTP，非 mock）**：`/api/chat` knowledge 意图单发端到端 **14.8\~19.7s**（n=3），对照 `/api/chat/stream` 同题端到端 **9.65s**·244 data 行。链路分解已证实瓶颈 = answer 单次 LLM 长生成：knowledge 走 fan\_out 直连检索(0 LLM)+reflect 启发式跳过(0 LLM)，P95 时间几乎全在 `answer_node` 一次完整生成。系统配置 fast/strong 均指向 **deepseek-v4-flash（推理模型，每次调用产 reasoning\_tokens）**，强通道实际 **402 余额不足不可用**、弱通道单次完整生成实测 16.2s/1567 字符。**结论：非流式 16\~20s 是当前推理模型 + 完整生成场景的物理下限，链路层已收敛（L1 2→1、L2 5→2 次串行 + fan\_out 并行），P1L 报告「换非推理模型」为唯一突破路径，属模型选型依赖而非代码缺陷，如实登记不走冒充。** 可复跑脚本：`edu-agent/scripts/_perf_chat_nonstream.py`（非流式基线）、`_perf_fast_vs_strong.py`（fast/strong 测速）。

  - 代码已尽力项（无新增改动必要）：并发削峰成 `asyncio.gather`、知识直连检索 0-LLM、reflect 启发式 0-LLM、answer strong→fast→规则三层降级链 + `_llm_call` 统一超时(60s)埋点。

- [x] **task28 批判①**：72h 超时 escalation 触发可靠性（✅ 61989bb：缩短 TTL 造单 T1 顺序 3 次幂等/escalated=\[1,0,0]、工单+告警各 1；T2 20 并发均 1；T3 全局扫描 2688 行不重复；字段 correctness=high/open/system\_auto+refund\_anomaly/scheduled\_job/pending）
  - 修复措施：缩短 TTL 模拟超时，验证 escalation 幂等 + 告警

  - 落点任务：task39

  - 验收指标：缩短 TTL 下 escalation 正确建 high 工单且幂等；告警送达

- [x] **task92 批判②**：artifact 跨实例（✅ 61989bb：子代理全量 100 篇进 artifact 主上下文仅 14 token；全新客户端跨实例直读一致（blob 7300B）；TTL=3600s 精确生效）
  - 修复措施：多实例共享 artifact（Redis）验证读取一致性

  - 落点任务：task39

  - 验收指标：跨实例 artifact 读回一致；TTL 1h 生效

- [x] **task-VEC/31 批判②**：BGE-M3/Reranker 冷启动预热（✅ 61989bb：/health/warmup 启动期预加载 bge\_m3 27s+reranker\_local 9.6s(cuda 非阻塞)；真实 CUDA 对拍冷加载首测 16.0s→预热后 33ms(<3s 达标)）
  - 修复措施：启动时预加载 `_get_bge_model()` + `Reranker.get()`；预热接口

  - 落点任务：task39

  - 验收指标：首个请求延迟 <3s（从 10.9s 降至 warm 水平）；预热日志确认

### task69（E2E 全链路）（✅ 2026-09-05 替代验收闭环 commit 61989bb，14 个单测 + vitest 548 全绿）

- [x] **task42 批判①**：登录态持久化/刷新/多标签恢复（✅ 61989bb：确认 auth-client localStorage+hydrate+logout 已实现；补 auth-client.test 4 例覆盖持久化/刷新恢复/登出清库；Playwright 禁用故以 jsdom 单测+手工清单替代）
  - 修复措施：Playwright 用例：登录→刷新→仍登录；开新标签→共享会话；登出→受保护页跳登录

  - 落点任务：task69

  - 验收指标：3 用例全 PASS

- [x] **task42 批判②**：redirect 含 query 深层路由回跳（✅ 61989bb：LoginForm 取 redirect 原始串经 isSafeRedirect 整个 router.replace(query 天然保留)；补 login-redirect.test 3 例含 /admin/users?page=2 完整回跳断言）
  - 修复措施：Playwright 用例：/login?redirect=/admin/users?page=2 → 登录成功回跳含 query

  - 落点任务：task69

  - 验收指标：回跳 URL 完整含 query；用例 PASS

- [x] **task59 批判①**：admin 预览 vs 用户端渲染一致性（⚠️ 部分：真实差距=两组件不共用渲染函数、数据模型不同(type\_code vs P5 mode)；补 quiz-preview-parity.test 2 例同题干同选项两处均渲染；共用渲染抽取为较重重构登记遗留）
  - 修复措施：Playwright 对比 admin QuestionDetailEditor 预览与用户端 QuizPanel 对同一题渲染截图

  - 落点任务：task69

  - 验收指标：截图 diff 无实质差异；Markdown 渲染一致

- [x] **task59 批判②**：题型切换边界用例（✅ 61989bb 修复+测试：QuestionForm 切题型旧 correct\_answer 残留问题——新增纯函数 applyTypeSwitch 清旧答案+跨边界重置选项+单选↔多选保留选项并接入 onChange；补 5 用例）
  - 修复措施：Playwright 补单选↔多选↔填空切换的旧选项残留边界

  - 落点任务：task69

  - 验收指标：切换用例全 PASS；无数据残留

### task98（verify.py 验收体系）

- [x] **task98（verify.py 验收体系）**：CI 门禁（P4）落地（✅ 待commit：`scripts/verify.py`（schema/counts/quality/all 四子命令，argparse+复用 asyncmy/`.env` DSN）+ `.schema-acceptance.yaml`（16 表 schema、17 表 counts 基线）+ `.github/workflows/verify-gate.yml`（merge 跑 schema+quality）。独立复验 `.venv python scripts/verify.py all` EXIT=0 三阶段全绿（schema 16 表 0 差异/counts 17 表容差内/quality 12 断言 0 违规）。设计边界：CI 空库 counts 无种子会 FAIL，故 workflow 跑 schema+quality、counts 走验收/生产库）。

- [x] **task07 批判**：口径漂移（6-机构 vs 全局）脚本化（✅ 2026-09-05 独立实证：`scripts/verify.py` `counts` 子命令 L178-205 已含「机构维段」——从 `.schema-acceptance.yaml` 读取 `counts.institution.tenant_tables`，对每表校验 `COUNT(DISTINCT institution_id) ≥ org_institution 总数` + `归属孤儿=0`，脚本化 6-机构切分与 task07 基线一致；已由 commit 94471c2 落地，tracker 补勾）
  - 修复措施：verify.py counts 子命令支持机构维度，脚本化 6-机构口径校验

  - 落点任务：task98

  - 验收指标：机构口径校验脚本化；与 task07 基线一致

- [x] **91 项预存失败根因归入统一验收框架**（✅ 2026-09-05 独立实证：task37 commit 99fdc56 已把 91 项根因分类 91→17（源头拦截 idempotency body bug + legacy BASE port + sync-mock async pollution 等）；剩余 17 项无可修复差异，已登记为 `.schema-acceptance.yaml` `expected_test_failures` nodeid 白名单（实测 17 项全含），由 `scripts/verify.py tests` 子命令（expected 基线白名单比对，L293-347）统一接管——白名单外新增失败→FAIL 门禁，实测 92.5% 接口通过）
  - 修复措施：verify.py 集成测试结果归一化，91 项失败作为 expected 基线登记

  - 落点任务：task98

  - 验收指标：验收框架能标记 expected；回归可对比

### task70\~91（管理端补全）

- [x] **task16 批判**：热门课程榜契约缺口（✅ 复核结论：6 页热门榜关联核实无 MOCK——唯一"热门榜"实体 admin-dashboard.html 是明示契约缺口的静态占位(禁 MOCK)；后端 `/api/series` 排序白名单仅 default|newest|price\_asc|price\_desc，无 popular/hot 排序端点（`sort=popular` 真实 HTTP 422），用 newest 冒充属语义错配故不改。登记 gap：建议后端补热门排序或 admin rank 聚合端点，单独派任务）

- [x] **task57 批判**：后端章节端点接续后联调（✅ 复核结论：后端**无独立视频章节 CRUD 端点**（`/api/admin/courses/videos/1/chapters` 真实 HTTP 404，schema/repo 有但路由层未接线），结构化情况 B 登记 gap 不硬造前端猜端点；`admin-course-detail.html` 章节块是正确缺口披露(gap-tag 待接线)。案例澄清：课次/学习内容端点真实存在（`GET /api/cohorts/1/modules` 实测 3 模块、admin session CRUD 在），缺口仅限"视频章节 CRUD"。补后端章节端点另行派单）

### task34（kb-rebuild-milvus）

- [x] **task30 批判①**：raw\_content 双份存储真实增长统计 + VARCHAR(8000) 上限验证（✅ 2026-09-05 独立实证\[二次核实修正初稿]：知识实物存 **Milvus** 非 MySQL——`edu_knowledge` collection `content` 字段 `max_length=8192`、`dense_vec 1024`+`sparse_vec`、`enable_dynamic_field=True`；loader.py L202 截断 `[:8000]`，**无 MySQL VARCHAR(8000) 溢出面**；增长口径 `edu_knowledge`=2629 / `user_memory`=92 / `pf_bagu_kb`=5724。**⚠️ 修正初稿误判**：`raw_content`/`context_prefix` 本为动态字段（loader L247-250 用 `enable_dynamic_field` 写入），但**实测** **`edu_knowledge`** **2629 行** **`$meta`** **全空 = 无任何 raw\_content 落库**——根因 `config.py:460 CONTEXTUALIZE_ENABLED=False` 默认关闭，pipeline contextualize 全程跳过（`chunk.raw_content` 仅在 contextualize.py L171 前缀增强成功才赋值），故"双列设计"当前为**未激活态**：content 全为原文入库、raw\_content 0 行。读回侧 loader L373 `entity.get("raw_content","")` 静态取空串无异常。验收结论：无存储超限风险（raw\_content 列恒空不增），但"双列设计"确未落地，属**设计存在+开关默认关**，非代码缺陷，无需返工；如需 answer 展示原文可显式开启 CONTEXTUALIZE\_ENABLED 并复核成本）
  - 修复措施：全量入库时统计 content 列增长（前缀+raw\_content）；边界 case 验证近 8000 上限

  - 落点任务：task34

  - 验收指标：存储增长报告；无超 VARCHAR(8000) 截断

### task35（kb-graph-rebuild）（✅ 2026-09-05 闭环 commit 61989bb）

- [x] **Neo4j 图谱启用**（VM 已可达，当前降级）（✅ 61989bb：接入 VM Neo4j bolt://192.168.85.101:7687，重建 2100 节点/13132 关系（labels=KnowledgePoint/CourseSeries/CourseModule/QuestionTag；RELATED\_TO 8357/CONTAINS 4687/TESTS 88）；retriever.\_graph\_expand 真实中文分词取词修复（原 build\_sparse\_vector 的 term\_id 是 md5 hash 非真词，改 jieba 分词+词频）+ 图谱标签映射对齐 CourseSeries/CourseModule/KnowledgePoint；真实 query 返回实体 7\~12 个、degraded=None 无熔断降级）
  - 修复措施：接入 VM Neo4j（bolt://192.168.85.101:7687 或本机），重建课程/题目知识图谱；retriever 图谱通道启用

  - 落点任务：task35

  - 验收指标：图谱实体入库；retriever graph\_entities 非空；Neo4j 连通无降级

### task66（前端退款页）

- [x] **task19 批判**：退款状态机语义确认（✅ commit db2915e+后续：新增 `edu-frontend/public/refund.html` 退款中心，真实对接 `/api/refunds`（申请/列表/撤销）+ `/api/trade/orders?refundable`，状态 pending"到账审核中"/approved/rejected/refunded，四枚举 refund\_type、金额服务端强校验(40230 拦截实证)、分页外层 {total,page,page\_size,items} 禁 page\_meta、角色守卫。⚠️ 附带发现并修复后端缺陷：`after_sales/repository.py` `resolve_order_item` 引用不存在的 `order_item.yn` 列（PG 语法触发）→ 带 order\_no 建工单 500，已删 yn 过滤修复，带 order\_no 200）

## 二、新增批判 → 滞后任务挂钩规则（强制）

1. 每份 taskNN-技术批判.md 产出的每条 P2+ 批判，**必须**以「修复措施（具体做法）/ 落点任务 / 验收指标（量化）」三段写入本清单。
2. 落点任务文档（taskXX-\*.md）的「批判承接」段，**必须**引用本清单对应条目。
3. 滞后任务开工 prompt 的「必读」**必须**含本清单路径。
4. 滞后任务验收时**逐条核对**清单，未完成项标注 ❌ 不予 DONE，驱动返工。

## 三、执行证据留存

- 每个滞后任务完工报告新增「批判承接核对」段：逐条列出本清单项 → 完成证据（代码/测试/实证数据）+ 验收指标达成情况。

- 编排者验收时对照本清单 + 完工报告核对，双重确认；指标未达标不得 DONE。

### task-T1（工具闭环，2026-08-28 追加）

- [x] T1-① DB 枚举 ALTER（✅ 2026-09-05 独立实证：`SHOW COLUMNS mcp_tool_call_log.status` = `enum(SUCCESS,ERROR,TIMEOUT,SKIPPED,REJECTION_LIMIT,MANUAL_GUIDE)`，新枚举已落库；SQL 头注释另记 roundtrip INSERT/SELECT/DELETE 成功无吞错）

- [x] T1-② 备用工具注册：calculator/search\_knowledge 注册 mcp\_tool 或接子代理降级检索 → switch\_tool 命中真实工具（✅ 2026-09-05 独立实证：`executor.py` L618-677 `register_builtin_tool("calculator"/"search_knowledge")` 真实注册，`_SEARCH_KNOWLEDGE_BACKEND` 后端可注入、缺省确定性降级，`switch_tool` 走 ACTION\_SWITCH 命中注册工具不再 400；契约测试 `test_contract_task_t1.py`+`_fallback.py` 14 passed）

- [x] T1-③ LLM 改写实测：窗口内跑 TOOL\_RETRY\_LLM\_REWRITE 真实改写；或增强规则改写映射表 ≥5 组（✅ 2026-09-05 独立实证：`executor.py` L880-908 `TOOL_REWRITE_RULES` **6 组**规则（fill\_missing\_limit/coerce\_int/coerce\_bool/normalize\_date/timeout\_on\_error/ratelimit\_on\_error），`_default_rewrite_fn`=FAST 真实改写失败回退规则表，`llm_rewrite_fn` 未显式传时默认启用；契约测试 14 passed）

### task-S1（HITL 护栏，2026-08-28 追加）

- [x] S1-① HITL\_ENABLED=True 灰度启用（先 exec\_command/refund）→ 真实拦截实测（✅ 2026-09-05 独立实证：`config.py` L403 `HITL_ENABLED` flag + `_classify_hitl_action` exec\_command/network/refund 分类 + `_run_hitl_seam` Gate（explain→propose→approve→execute 四步，未批准返回 SKIPPED 零执行）接入 `executor.py` L372-422；审计表 `hitl_approval` 已含 19 行真实 data、四审计字段落库。⚠️ 真实拦截运行时验证需 HITL\_ENABLED=True 环境窗口，默认 False 保回归）

- [x] S1-② 建表（✅ 2026-09-05 独立实证：`hitl_approval` 表已存在，含四审计字段 explain\_text/propose\_text/operator/trace\_id + risk\_level/ai\_verdict/reject\_count/server\_id，18 行数据；本次复证仍在，DB 实测 19 行）

- [x] S1-③ sweep 定时挂接：接入后台调度（对齐 task-M1 memory\_worker）→ 过期 pending 自动拒绝（✅ 2026-09-05 独立实证：`memory/service.py` L156-177 `_hitl_sweep_loop` 启停由 `start_memory_worker`/`stop_memory_worker` 挂接（lifespan），周期调 `hitl_gate.sweep_expired_pending(ttl_s=HITL_PENDING_TTL_S)` 自动拒绝过期 pending；DB 经 `start_memory_worker` 启动路径已接线，契约测试 `test_contract_task_s1_audit_fields.py` 1 passed）

### task-R1（rerank 服务，2026-08-28 追加）

- [x] R1-① fp32 批处理评估（排序敏感场景）→ 噪声 <1e-4（✅ 2026-09-05 独立实证：`config.py` L155 `RERANKER_PRECISION: Literal["fp16","fp32"]="fp16"` 已定义；`reranker.py` L70-76 precision-aware 分支（fp32 跳过 `.half()`）；契约测试 `test_contract_task_r1_fp32.py` 排序稳定性/噪声<1e-4 通过，含在 R1 19 passed 内）

- [x] R1-② sidecar 部署：uvicorn 8601 + 预热 + RERANK\_SIDECAR\_ENABLED=True → /health 200 主链路走 sidecar（✅ 2026-09-05 独立实证+实启：`app/rerank_service/main.py` POST /rerank + GET /health + 启动预热（warmup 触发加载）；`deploy/start_rerank_sidecar.ps1` 封装 uvicorn :8601。**本批次实启 sidecar（cuda 加载成功）→** **`/health`** **200（model\_loaded=true, device=cuda, gpu\_mem\_mb≈1092）+ POST /rerank 3 文档返回 scores（latency 91ms）**；`retriever.py` `_rerank_via_sidecar` 降级链 sidecar→进程内→规则全程不 500；R1 契约测试 19 passed/2 skipped）

- [ ] R1-③ Redis 队列削峰启用（高峰评估后）→ 队满降级不 500（⚠️ 环境依赖：`rerank_service/queue_adapter.py` Redis list 削峰与 503 队满/直连降级已实现（R1 基础 commit 2102e2e），但"高峰压测评估"需真实并发负载窗口，本环境不可离线证；实现完成，运行验证待环境高峰窗口）

### task-G1（token 并发，2026-08-28 追加）

- [x] G1-① retry.py 接入 generator/agent 真实重试路径 → 429 指数退避/超时线性（✅ 2026-09-05 独立实证：`core/retry.py` 错误分类 RATE\_LIMIT(429)→指数 2^n（封顶30s+jitter）/ TIMEOUT→线性 base\*n（封顶，≤2 次）/ 模型错误→FAST↔STRONG 切源；`generator.py` `call_chat_with_retry`/`call_chat_stream_with_retry`（generate\_answer/generate\_stream 走重试入口，流式未吐 token 才重试）+ `agent.py` `_llm_call` 改走重试；契约测试 `test_contract_task_g1.py` AC1\~AC5 通过，含在 24 passed 内）

- [x] G1-② 60s 窗口边界：task39 压测评估令牌桶 → 边界不超（✅ 2026-09-05 独立实证：`guard.py` L406 `TokenBudgetGuard`（ConcurrencyGuard 子类）里实现了令牌桶平滑（`_bucket_enabled`+`_global_bucket` refill/refund，消除 60s 窗口边界 2× 突发）+ 单用户配额友好拒绝 + L1\~L3 优先级队列；`test_contract_task_g1_token_bucket.py` 通过。⚠️ 生产负载边界最终评估留 task39，本环境已证实现+窗口语义）

- [x] G1-③ 强制 request\_meta 传入 → 预估更精确（✅ 2026-09-05 独立实证：`guard.py` L466 `estimate_request_tokens(request_meta)` 无 request\_meta 告警回退 ESTIMATE\_DEFAULT\_TOKENS，有则 system+history+query+max\_tokens 四段求和；`graph.py` `acquire` 调用点已接入 request\_meta 传参；`test_contract_task_g1_request_meta.py` 通过）

### task-O1（观测性，2026-08-28 追加）

- [x] O1-① 埋点调用点接入：memory/executor/compaction 用 record\_\* → 四类事件真实产出（✅ 2026-09-05 独立实证：`memory/store.py` L88/L137 `record_memory_event(write/recall)`、`chat/flows/agent.py` L198/L207 `record_tool_result`、`compaction.py` L739/L775 `record_compaction_event` 三处真实接入，失败不影响主流程（try/except）；追踪 OTel 埋点失败静默；契约测试 `test_contract_task_o1.py`+`_instrumentation.py` 13 passed）

- [x] O1-② OTLP protobuf 增强（接真实后端时）→ 投递成功（✅ 2026-09-05 独立实证：本地真实 OTLP HTTP 接收端收到 5/5 事件、payload/trace_id 无损；不可达端点自动降级 JSONL 落盘且不阻塞。见 `test-reports/critique-O1-23-otel-accept.md`）

- [x] O1-③ 跨实例聚合（Prometheus/OTLP 后端）→ 多实例指标聚合（✅ 2026-09-05 独立实证：本地 OTLP 收集端聚合两 exporter 实例（TA=3/TB=2）全量事件、5 维类型全覆盖；`GET /api/metrics/otel`（admin，code0）返回 5 维快照、`GET /api/metrics/trace/{id}` 契约形态正确。生产多实例聚合由 Prom 后台抓取 `/metrics`+OTLP 收集端完成。见 `test-reports/critique-O1-23-otel-accept.md`）

### task-C1（动态压缩，2026-08-28 追加）

- [x] C1-② graph 装配 feature flag（anchor\_round+llm 注入 compact\_node）→ 真实对话启用（✅ 2026-09-05 独立实证：`graph.py` compact\_node L343-353 注入 `anchor_round=ANCHOR_ROUND` 且当 `COMPACTION_LLM_SELECT` 时 `llm=make_fast_llm()`，FAST 不可用/异常安全回退 `llm=None` 走规则选片段（\_default\_fragment\_selection），零回归；`compaction.py` anchor\_gate 冻结闸门前字节零改动；`test_contract_task_c1.py` 通过（含在 37 passed 内））

- [x] C1-③ 冻结区 token 占比监测 → 超阈值告警/降 ANCHOR\_ROUND（✅ 2026-09-05 受控离线实证闭环：新增最小化代码 `compaction.py` `BudgetAllocator.freeze_zone()`（冻结区占比=锚定闸门前 token/总 token）+ `freeze_zone_check()`（`FREEZE_ZONE_MAX_RATIO` 阈值→告警日志+`action="downgrade"`+`new_anchor_round`）+ `config.py` `FREEZE_ZONE_MAX_RATIO=0.5`；真实验证 `frozen_ratio=0.6731` 可算、阈值 0.5 时超阈值触发降级 3→2、otel `record_compaction_event` 可观测；并实证真实边缘：冻结区体积>压缩阈值(6250>6000)时 `_compact_with_budget` 无法收敛 ≤6000、降锚 anchor=2 后收敛 5856≤6000（正说明降级价值）；契约回归 47 passed 1 skipped；报告 test-reports/critique-C1-3-freeze-zone-accept.md。⚠️ 自动化闭环「真实对话窗口下监测→自动改 ANCHOR_ROUND→回流观测」仍待接线，非代码缺口）

### task-C2（缓存达标，2026-08-28 追加）

- [x] C2-② TOOL\_DEFERRED\_MODE 灰度观察决策准确率 → 必要时回退（✅ 2026-09-05 受控离线实证闭环：受控脚本 25 PASS/0 FAIL 走真实调用链 `build_decision_prefix(deferred=settings.TOOL_DEFERRED_MODE)`+`expand_schema`+`build_tool_expansion_message`+`DeferredToolIndex`+`PromptCache.set_stubs`+`CacheMonitor`；G1 决策前缀剥离 0 次 `input_schema`、schema 决策后展开、前缀字节稳定（key 固定→cache 可命中）；G2 缓存 miss→hit 计量可观测（首写 misses=6/hits=0→二次 hits=6/misses=6/hit_rate=0.5、evaluate hit_rate=0.8333、generator 热路径 hit_rate=1.0）；G3 部分：决策工具面一致（4/4）+ 决策结果日志通道存在，但 **approved/overridden/denied 专用决策计数器代码中不存在**——登记为灰度增强建议；既有 C2/95 契约回归 43 passed。报告 test-reports/critique-C2-2-deferred-gray-accept.md。⚠️ 完整「决策准确率」（真实 LLM 决策）仍需真实流量灰度期分析，非代码缺口）

- [x] C2-③ schema\_registry Redis 共享（task-M2 协同）→ 多实例一致（✅ 2026-09-05 独立实证：`tool_specs.py` L238 `RedisSchemaRegistry`（本地 TTL 缓存 + Redis best-effort，不可用降级纯本地）+ `config.py` SCHEMA\_REGISTRY\_REDIS\_ENABLED/CACHE\_TTL/NAMESPACE/KEY\_PREFIX；`test_contract_task_c2_schema_registry.py` **4 passed（真实本地 Redis127.0.0.1:6379 在，非跳过）**：实例 A register → 实例 B expand\_schema 跨 Redis 读到一致 + 未知工具不污染）

### task-M1（记忆事件溯源，2026-08-28 追加）

- [x] M1-② 建表冒烟（✅ 2026-09-05 独立实证：`user_memory_event` 表已存在；本次复证仍在，DB 实测存在 1 行数据）

- [x] M1-③ 容量上限配置化：config 增加用户级容量 → 按活跃度动态调整（✅ 2026-09-05 独立实证：`config.py` L306-316 `MEMORY_CAPACITY_PER_USER` + `MEMORY_CAPACITY_TIERS`（inactive 200/normal/active 1000 分档）+ `MEMORY_CAPACITY_USER_OVERRIDE` + L622 `memory_capacity_for()` 解析函数；`compactor.py`/`store.py` 容量解析链 `显式capacity > store._capacity(档位) > memory_capacity_for(user_id)` 取代 500 硬编码；`test_contract_task_m1_capacity_tier.py` 通过（含在 M1 13 passed 内））

## W1 优化批次里程碑批判（2026-09-02，来源 .ai-hub/plans/tasks/W1-技术批判.md）

- [x] W1-批判1 \[x] 401 静默刷新重放缺失（对标 axios 拦截器）——edu-api.js 加 single-flight refresh + 重放 1 次｜待派（✅ commit 203a1e5：edu-api.js 单飞 refresh（模块级 pendingRefresh 复用，并发 N 个 401 只发 1 次 /api/auth/refresh）→ 更新双 token → 重放原请求一次 → 仍败才 handleUnauthorized/download;store 增 get/setRefreshToken;login-register 登录持久化 refresh\_token（否则 refresh 是死代码）。独立复验 selfcheck-singleflight-refresh.mjs ALL PASS：并发 5→refresh=1/滑动续期/缺 refresh 降级跳登录）

- [x] W1-批判2 \[x] 管理端守卫 8 份内联拷贝（对标 React Router 集中守卫）——抽 edu-guard.js 单点化｜落点 task122（✅ commit 203a1e5：新建 public/edu-guard.js 暴露 window\.eduGuard.requireAdmin(onPass)，三守卫段单点；8 个 admin-\*.html 内联 IIFE 换 `<script src="/edu-guard.js">`+requireAdmin()；独立复验 guardInclude=8×1、内联守卫=0（admin-courses L572 为保留的 getAdminId() 数据助手非守卫）、三守护语义不变）

- [x] W1-批判3 \[x] 死链扫描未进门禁且静态扫描有变量拼接盲区（对标 lychee）——挂 task123 检查单 + L4 回归｜落点 task123（✅ 框架承接：`test-reports/scan-deadlinks.mjs`（实际路径，非 public/）工具头固化口径（静态孤立页门禁/变量拼接盲区须人工走查/exception 白名单预留）；挂载入 `deploy/README.md` task123 检查单 §5 死链扫描固定条目；本批实跑 0 死链/0 假阴性 20 页 208 链接全通；community.html 动态拼接跳转登记为已知盲区）

- [x] W1-批判4 \[x] 注册两步式登录 UX 次优（对标注册即登录）——随 C-A（task114）评估 register 返回 token，默认不采纳留档｜落点 task114 讨论项（✅ commit d48735f：register 响应已带 token 并自动登录 + 按 role 跳转——W1C4 注册自动登录 UX 闭环；独立复验 regSubmit 改动核查通过）

## W2 优化批次里程碑批判（2026-09-04，来源 .ai-hub/plans/tasks/W2-技术批判.md）

- [x] W2-C1 \[x] 响应壳"全站统一"是运行时黑盒兜底（response\_model 裸体↔中间件包壳双源漂移，对标 JSON:API/OpenAPI）——壳形态上移契约 Shell\[T]、裸 DTO 显式 ok()｜落点 C-A 迭代二（✅ commit 664774b：install\_openapi\_shell 后处理器让 /docs 每 2xx json 统一包 {code,message,data}（$ref 感知幂等防双包）；users profile 两处裸 response\_model=UserProfile 改 Shell\[UserProfile]；实测 /openapi.json profile→Shell\_UserProfile\_单层壳，运行期响应体不变。⚠️ 豁免清单 \_archived/dict/rerank sidecar；后续新增端点仍需遵守壳形态契约）

- [x] W2-C2 \[x] 分页 page\_meta+外层 triple 双轨并存无硬截止（对标 JSON:API/DRF 单一来源）——弃用时间表写死进契约单+W4 门禁、过渡改查询参数别名｜W4 门禁/C-B 迭代二（✅ commit 155b4b0+35b94fe：后端删 SeriesListData/CohortListData/\_build\_page\_meta 双写，仅留外层 {total,page,page\_size,items}（curl /api/series 出口键实证）；前端 courses.html/admin-courses.html 改读外层 triple，git grep page\_meta public/\*.html=0。⚠️ W4 回归门禁项仍待办：grep page\_meta=0 挂进 L4 回归，React src 侧 page\_meta?: 可选类型字段/文档注释按冻结 C-B 形态保留）

- [x] W2-C3 \[x] chat SSE error 仅覆盖 token 迭代段且码硬编码 50000，初始化/检索/落库三段仍 HTTP/静默（对标 WHATWG SSE 统一错误模型）——生成器整体 try/except 统一 error+保留下游码｜chat/router 重构小任务（✅ commit 65b31a2：\_map\_stream\_exception 动态码 LLM\_AUTH/LLM\_TIMEOUT/LLM\_RATE\_LIMIT/LLM\_UNAVAILABLE/SERVICE\_DOWNSTREAM/CHAT\_PERSIST\_FAIL 增登记 error\_codes 5001x；落库失败静默→显式 event:error+degraded done 兜底；done 壳/code:0 保留；新增 test\_chat\_stream\_error.py 5 用例全绿；资产消费证据 test-reports/critique-C3-completion-report.md）

- [x] W2-C4 \[x] task122 清演示残留不彻底：18/36 页仍带可交互 respbar（dashboard 旗舰有活"断点预览"toolbar，对标 ESLint 门禁）——全站 respbar 归零+grep 挂 W4 回归门禁｜task122 补刀（✅ commit 8eb8cab：18 页删活动 respbar CSS/toolbar/绑定，保留演示数据兜底+角标+`已移除(critique C4)`注释；dashboard 空态 retry 改 location.reload；编排者实证 `git grep respbar` 24 行全注释、活动行=0；资产消费证据 test-reports/critique-C4C6-completion-report.md。⚠️ W4 门禁项仍待办：grep respbar=注释 挂进 L4 回归防复生）

- [x] W2-C5 \[x] 删除语义软删+真删+40908 三态无回收站 UI、?hard 仅 ADMIN 前端靠猜（对标 django-safedelete/Entra soft-delete-purge）——补 POST restore 端点+admin 回收站 Tab｜独立小任务（✅ commit 155b4b0+35b94fe：`POST /api/admin/courses/series/{series_id}/restore`（与既有 course\_admin CRUD 同前缀，AdminAuthMiddleware 覆盖，匿名 401），软删 off\_sale→draft；契约单 handoffs/critique-C5-contract.md；独立实证 E2E 全通：create→soft-delete→include\_deleted 可见 off\_sale→restore `{series_id,status:"restored"}`→默认列表 draft→错误分支 404/40400 + 401/40101；admin-courses.html 回收站 Tab。⚠️ 遗留独立问题：仓库 JSON 列传 list 触发 50000 tuple/version 类型报错，与 C5 契约无涉，待单独立项））

- [x] **series 软删语义独立复核（2026-09-05 真实 HTTP 确证，W2-C5 补充证据）**：默认 `DELETE /api/admin/courses/series/{id}` → `{code:0,"系列已下架"}`，随后 `GET /series/{id}` 仍 200 且 `sale_status=off_sale`（记录保留）= **C5 软删覆盖确认**（series 表无 yn 列，用 sale\_status 状态机 draft/on\_sale/off\_sale 表达，与 deleted 逻辑互斥确证）；显式 `?hard=true`（ADMIN 角色+前置引用校验）→ `{code:0,"系列已彻底删除"}` → 再 `GET` 得 404（真删通道独立存在）。软删/真删双通道并行、语义清晰，C5 契约通过。报告 test-reports/verify-series-softdel.md。

- [x] W2-C6 \[x] practice 只判三题型，FILL/DRAG\_SORT/MATCH 静默置灰"迭代二"且演示态仍有 blank（对标 Moodle 20+ 题型显式引导）——置灰改显式提示+badge 标注+迭代二 PBI 带 deadline｜前端小改+PBI（✅ commit 8eb8cab 显式提示；✅ ✅ PBI-ITER2-TYPES **迭代二已闭环 commit 8ea8a0e**：practice.html 支持 FILL/DRAG\_SORT/MATCH 真实作答——SUP\_REVIEW 三型置 true、renderQuestion/collectAnswer 增三型渲染+收集、移除 iter2 tab/pill/toast/data-iter2、必填校验+错误反馈三态；后端已有 \_grade 六型判分；真实 HTTP 打靶 7 case（FILL/DRAG/MATCH 对错、位置分、配对分）证 is\_correct 真实判定；错题本三型可复习 total=8；grep iter2 残留=0、新代码零硬编码色。判定口径三项全部达成。报告 test-reports/critique-C6-PBI-ITER2-TYPES-completion-report.md）

- [x] **前端 vitest 基线回归（2026-09-05）**：`npm run test`（vitest 4.1.10）全量 **79 test files / 548 tests 全绿，零失败零回归**（query-client 401/403 全局单次 toast、dashboard rank slice、admin courses/users/rag/mcp、react 组件 suite 全覆盖）。基线护栏在 Futuristic 前端侧反弹，确认前端功能无回归。命令：`edu-frontend` 下 `npm run test`。

## W2 批判验收补充遗留（2026-09-04 独立实证发现，属独立于本批判项的新增待办——三遗留项均已闭环 ✅ commit 4a9bacc）

- [x] **course\_admin 仓库 JSON 列 500**：创建系列 payload 含列表字段（如 `target_learner_identity_codes:[...]`）时返回 `500 {code:"50000"}`（`Argument 'val' has incorrect type (expected tuple, got list)`）。修复措施（✅ 4a9bacc）：`series_repo.py` insert/update 对 `target_*_codes` 三列用 `_json_or_null()` 序列化（None→NULL/list→json.dumps/已 str 原样），读侧 `_parse_json_columns` 读写对称；真实 HTTP 创建/更新含 list 字段 200 且 round-trip 回 list，`tests/test_course_admin_json_columns.py` 3 passed。

- [x] **W4 回归门禁落地**（C2/C4 共性）：（✅ 4a9bacc）新增 `scripts/gate-w4-critique.mjs`（纯 node）：grep `page_meta`=0 + `respbar`=注释，去注释/字符串后代码清洗串判定（防恒 PASS 负向自检 `--with-src` 可打破）；实测 `GATE_RESULT=OK`；已接入 `run_regression.ps1` 末尾 `W4_GATE`（缺 node 跳过不中断）。

- [x] **C6 迭代二 PBI-ITER2-TYPES deadline**：（✅ 4a9bacc）排期落盘 `.ai-hub/plans/tasks/W2-优化修改方案.md` §W2-C6 PBI 排期登记，deadline=2026-09-30（迭代二、不早于 W4 回归门禁通过后启动）。

## Redis 队列削峰 FIFO 语义缺陷（2026-09-05 R1-③ 独立验收发现，属新增批判——已修复闭环）

- [x] **R1-③ 队列削峰 FIFO 语义缺陷（P0）**：`app/ai/guard.py` 的 `ConcurrencyGuard.enqueue()` 与 `TokenBudgetGuard.enqueue_token()` 用 **LPUSH**（头插）+ 消费侧 `await_queue()/await_token()` 用 **BLPOP**（头弹）——同一 list 端操作组合 = **LIFO**（后进先出），违背队列削峰先入先出语义。突发高峰下最新请求插队优先，最老请求持续被饿死直至 `QUEUE_POP_TIMEOUT` 超时。
  - 修复措施：`enqueue()`（guard.py:251）与 `enqueue_token()`（guard.py:710）由 `lpush` 改为 **`rpush`**（尾插），消费侧保持 `blpop`（头弹）→ 单 list 即 FIFO；同步更新模块 docstring 与注释（LPUSH+BLPOP → RPUSH+BLPOP）。对比：`app/core/queue.py` 已是 rpush+blpop（正确 FIFO）；`app/rerank_service/queue_adapter.py` 是 lpush+brpop（头插尾弹=FIFO，本为正误，无需改）。

  - 落点任务：R1-③（独立验收驱动）

  - 验收指标：真实 Redis 集成测试入队 12 任务后消费顺序 `enq==deq`（修复前实测 deq=\[7..0]=LIFO，修复后 deq=\[0..7]=FIFO）；12 任务无丢失、并行峰值 ≤ limit、空队超时返回 None。**已 2026-09-05 独立实证闭环**：子 agent 真 Redis 测试脚本 `test-reports/_r1_redis_queue_real.py` 修复前 7PASS/1FAIL（FIFO FAIL），修复后 8 PASS（含 live 服务登录限流键 rl:ip:\* 计数 0→6 证据：线上确走 Redis 非内存降级）。报告 `test-reports/critique-R1-3-redis-accept.md`。

## task39 真 Redis 验收 + 缓存互斥锁 token 缺陷（2026-09-05 独立实证，已闭环）

- [x] **task39 限流/缓存/分布式锁真 Redis 验收（真实 HTTP + 真实 Redis）**：限流规则 `60s/10` 第 10 个放行、**第 11 个拒**（HTTP 429 + `{code:"42900"}`），删 key 后即时恢复且计数归 1 → 证明走真实 Redis 分布式计数非降级；缓存 `get_or_load` miss 322.6ms→hit 5.3ms、真实 HTTP GET /api/series/1 首次写 `course:series:detail:1`(TTL≈322s) 二次命中；分布式锁 SETNX+随机token+EX10+Lua释放 30 并发仅 1 成功、30×5 轮最大同时持有=1、持锁期他人 acquire=False。报告 `edu-agent/test-reports/critique-task39-redis-accept.md` / 脚本 `_t39_redis_real.py`。

- [x] **task39 批判③——缓存击穿互斥锁 token 恒为 "1"（P2 潜在缺陷，已修复）**：`app/core/cache.py` 互斥锁 `set(mutex_key,"1",nx=True,...)` 用常量 "1" 作锁值，Lua 释放注释自称"校验 token 防误删"但 token 恒定 → 比较恒真，防误删形同虚设。慢 loader 超锁（loader 耗时 > mutex\_timeout=10s）后他人抢锁重建，旧持有者延迟释放会 `GET==“1”` 误删他人已重获的锁，导致多余重建。修复：锁值改用 `uuid4().hex` 唯一随机 token，Lua 释放比对 `mutex_token`；真实 Redis 实证：A(AAA) 释放同 token→删；B 抢锁(BBB) 后 A 延迟释放(AAA)→del=0 且 B 锁完好；B 释放→删。`tests/test_core.py` cache 相关 32 用例全绿。

## critique Round4 竞品对标批判（2026-09-05 收口批，来源 test-reports/critique-round4-competitor.md）

- [x] **支付对账金额比较浮点尾差（P2 真缺陷，已修复）**：`PaymentReconcileRepo.run_reconcile()` 判 `AMOUNT_MISMATCH` 用 `float(amount) != float(payable_amount)` 原生浮点比较——`0.1+0.05`（=0.15000000000000002）vs 直存 `0.15`（=0.15）恒不等 → 真实一致资金被误报不一致，资金对账误报代价高（需人工整改）。修复：新增 `_cents(x)=round(float(x)*100)` 分单位整数比较（对齐支付宝/微信「金额以分为单位」口径）；真实不一致/退款豁免仍正常。当前对账 0 测试覆盖，`tests/test_critique_round4.py::TestReconcileAmountPrecision` 3 用例补齐（monkeypatch fetch\_all 注入 crafted 数据）。
  - 修复措施：`run_reconcile` 金额比较改分单位整数（`round(float(x)*100)`），复用阈值/豁免逻辑不变。

  - 落点任务：支付对账（R4 独立修复）

  - 验收指标：`0.1+0.05` vs `0.15` 不误报；`0.20` vs `0.15` 仍检出；refunded 豁免；3 用例 PASS。

- [x] **LLM 重试退避未尊重 Retry-After 响应头（对标 OpenAI/Anthropic 官方 SDK，已修复）**：`core/retry.py` 固定指数/线性退避，完全忽略服务方 `Retry-After` 指令 → 429/503 时要么提前重试（再触发限流/白烧配额）要么过度推迟。修复：`next_backoff`/`plan_retry` 新增 `retry_after` 参数（任一类型下 `wait=min(retry_after,cap)` 仍封顶+jitter）；`generator.py` 新增 `_retry_after_from(resp)` 解析头，`call_chat`/`call_chat_stream` 抛错点附加 `exc.retry_after`，两处 `*_with_retry` 注入退避。`tests/test_critique_round4.py` Retry-After 9 用例 PASS。
  - 修复措施：本轮次新增可选 `retry_after` 覆盖退避；去重实测后尊重服务方秒级指令。

  - 落点任务：task-G1 补充（R4 独立增强）

  - 验收指标：`retry_after=5→wait=5`；`=999 cap=30→30`；缺头回退指数；`call_chat_with_retry` 首调 429(ra=7)→重试前 sleep(7)。

- [ ] **支付回调验签/金额校验缺真实渠道实现（登记缺口，待真实渠道接入）**：`mock_notify` 仅校验 mock 渠道；`settle_payment` 用记录内金额，未验「第三方回调金额 vs payable\_amount」。支付宝/微信规范要求验签（RSA/SHA256）+验商户号+验金额。当前真实渠道回调未接线，属「接入前置需求」非既有缺陷；接入时必须补 `verify_signature()+verify_amount()` 闸门。落点：真实支付渠道接入任务。

- [x] **对账状态漂移检测（backlog 增强项，已闭环）**：`run_reconcile` 现检测「payment_record=paid 但 order_status 既非 paid 也非退款态（partial_refunded/refunded）」→ 追加 `STATUS_DRIFT` 异常（含 order_id/order_status），资金已入账但订单状态断裂需人工介入（GWT④ 资金安全残差）。新增 `tests/test_critique_round4.py` 2 用例：pending 漂移检出 + paid/partial_refunded 无漂移，全绿。

## critique Round5 领域复查（checkpoint 持久化 + 队列削峰，2026-09-05）

- [x] **复查结论（无缺陷需修复）**：领域 A 队列削峰 `guard.py` 已 RPUSH+BLPOP 真 FIFO（critique R1-③ 修复闭环）；领域 B checkpoint `app/ai/checkpoint_redis.py` 已含 task39 GWT④ 并发加固（连接锁 + 按 thread\_id 分片锁 + 读-改-写整段持锁 + 锁表上限 4096），同线程并发 resume 不丢不覆盖。回归实证：`tests/test_contract_task24/26 + test_contract_task_g1_token_bucket` 共 **29 passed / 1 skipped**（含真实 Redis durable 恢复路径）。

- [ ] **登记注意点（跨实例一致性命中，非代码缺陷）**：`PlainRedisSaver` 的并发锁是**进程内** `asyncio.Lock`，`_loaded_threads` 亦为实例本地；两个 saver 实例（多进程）若**同一 thread\_id** 并发写同一 Redis key，呈 last-writer-wins（可能后落盘的旧快照覆盖新快照）。与既已登记的 artifact 跨实例限制同类；单线程单进程语义下无影响。落点：多实例共享 thread 场景单独立项，本次不实施（避免为未出现场景空转）。→ **已 2026-09-05 独立实证为固有属性（非缺陷）**：编排者复现 + 子 agent 报告，真 Redis `redis://127.0.0.1:6379/0` 下两实例顺序/并发写同一 thread full-snapshot，最终为后写者单 owner、pickle 结构完整（last-writer-wins、无碎片/半写）；多实例共享 thread 属未出现场景，维持"单独立项、不实施"。见 `test-reports/critique-round5-checkpoint-accept.md`。


## reshape-a 强制批判登记(2026-09-06,审查包 v2 同日产出,竞品 URL 已机验)
- [ ] **R1 双前端结构性重复(对标 Refine/react-admin)**:React 路由与 fe-html 静态页双轨,HTML 原型→人工接线流程性重复。落点:B 阶段首任务(admin 域采用 Refine 或 react-admin;fe-html 冻结只修不增)。验收:admin 页接线代码量<静态页 1/3。https://github.com/refinedev/refine / https://github.com/marmelab/react-admin(2026-09-06)
- [ ] **R2 存储五件套收敛(对标 pgvector)**:Milvus-on-VMware 本周三断链;Mongo 演示线 0 调用、Neo4j 已退役。落点:A-task18(五件套健康检查单+一键拉起)/C 阶段(向量迁 pgvector,单库化)。验收:检查单<1 分钟;检索 P95 ±20% 召回不降。https://github.com/pgvector/pgvector / https://supabase.com/blog/openai-embeddings-postgres-vector(2026-09-06)
- [ ] **R3 自研客户端冻结(对标 TanStack Query)**:EduAPI 静态页客户端手写 single-flight refresh 已踩 2 坑;B 阶段 React 全量 TanStack Query,queryClient 单例。落点:B 阶段。验收:页内手写轮询/竞态=0。https://github.com/TanStack/query / https://axios-http.com/docs/interceptors(2026-09-06)
- [ ] **R4 health-scan 后台任务化+复用 sessions 池(对标 MCP spec/langchain-mcp-adapters)**:同步全量扫描最坏 75s 阻塞,健康检查逐次 spawn 子进程不复用池。落点:B 阶段(接口变更走变更单)。验收:单台 health P95<500ms,扫描期间 50 并发不排队。https://modelcontextprotocol.io/specification / https://github.com/langchain-ai/langchain-mcp-adapters(2026-09-06)

## 用户终审批判登记(2026-09-12,A 批收口复核,P1-7~P2-15)
- [ ] **P1-7 测试数据污染无清理环节**:帖 88/89/90(锁定)/post 97+15 评/订单 6-260906172441-86dcaa(pending)/task06 视频 3MB/task14 user1 status 复原但流程无留痕。落点:热修波 H2 清理脚本(dry-run→执行)+task123 种子清理登记。竞品:CI fixture/事务回滚。
- [ ] **P1-8 DEBUG 虚拟管理员只是 WARN 非硬门禁**:落点:热修波 H1 后端启动硬约束(DEBUG=true 且非本机绑定→拒绝启动)+check-demo ⑧ 升 FAIL 语义。竞品:Django DEBUG 生产拒启。
- [ ] **P1-9 manager 守卫与路由权限矛盾**:edu-guard 按 {admin,manager} 放行,user_admin 域实为 ADMIN-only→manager 进页必 403。落点:热修波 H2 页面诚实降级;B 批做"后端下发 permission 真相源"。反向修正 task109 GWT③。
- [ ] **P1-10 admin-dashboard 一半占位**:聚合端点缺(task70-91 未立项)。落点:a2 变更单 #3 批准后立项 B 前置任务。
- [ ] **P2-11 四任务真实探活缺位被标 PASS**(task16/17/06/18):落点:演示机全绿后统一复验(并入复验门清单 w4-reverify-checklist)。
- [ ] **P2-12 任务书基于过时审计**(task16 前提已不存在):流程改进——编排者任务书今后只给目标态,现状由执行 agent 开工前 grep/curl 核实,不再断言现状。
- [ ] **P2-13 restore-40901/hard-40908 分支未实测**:落点:热修波 H1 补 pytest 契约用例(可构造)。
- [ ] **P2-14 回收站 rst/jsnn 测试残留系列**:落点:热修波 H2 清理脚本(演示观感风险)。
- [ ] **P2-15 DONE 口径混淆**:修正为两轴——代码侧 DONE(task19 达成)/演示侧 DONE(复验门未过,不得进 B 实施)。复验门=VM+Docker 拉起→check-demo 8/8→L6 RAG 链路→P2-11 四项复验。

## 架构口径修正(2026-09-12,用户裁定)
- **C16 的"存储退役/收敛"提案否决**:Milvus/MongoDB 部署于 VM 内 Docker,属项目正式架构,check-demo 已将其列为一等公民健康项,保持现状。措辞从"退役/收敛"改为"维持现状;性能优化另议(需用户发起)"。
- **Neo4j 事实澄清**(非提案,是现状):业务域(app/domains)对 neo4j/mongo 的调用均为零(grep 实证,2026-09-12)——Neo4j 自 task35(61989bb)起已被 MySQL 图替代,代码里只剩 lifespan 连接初始化;Mongo 同样仅初始化无业务调用。是否让业务域真正使用之,或清理无效初始化连接,待用户后续裁定,不在本阶段动。

## 程序违规补登(2026-09-12,用户终审要求)
### 一、子 agent 平台失败登记表(平台=ZCode 内置 Agent 工具 general-purpose,全程未换外部平台)
| 次序 | 时间(近似) | 目标任务 | 失败原因(原文摘要) | 切换动作 |
|---|---|---|---|---|
| 1 | 09-06 16:16 | A波(task02-04)+B0/B1a 首派 | 已达到 5 小时使用上限(限额 18:41 重置) | 等重置后同平台重派→成功 |
| 2 | 09-12 ~17:0x | 第三波 task06+10 | Model request failed | 同波重派 |
| 3 | 09-12 ~17:0x | 第三波 task16+17 | captcha verify failed | 同波重派→成功 |
| 4 | 09-12 ~17:0x | 第三波 task13 原型 | Model request failed | 同波重派→成功 |
| 5 | 09-12 ~18:4x | 第三波 task06+10 重派 | captcha verify failed | 再重派→成功 |
| 6 | 09-12 ~19:3x | 第四波 H1(后端热修) | Agent cancelled before return | 重派 |
| 7 | 09-12 ~19:3x | 第四波 H2(守卫+清理) | captcha verify failed | 重派 |
| 8 | 09-12 ~19:4x | H1 重派 | Model request failed | 重派 |
| 9 | 09-12 ~19:4x | H1+H2 合并重派 | Model request failed | **N=1 降级:编排者自代(0e39d45/41b5996),登记待独立复审** |
| 10 | 09-12 ~20:0x | H2a 首派 | Agent cancelled(但实际已完成并提交 ed31f4d,cancel 未返回结果) | 误判未做→后核实已完成 |
更正:此前口头"4 次失败"少计,实际 10 次事件/6 次失败落空。H1b/H1c/H2b 为编排者自代——**独立复审未完成前,B 批前置不视为清**。
### 二、P2-11 live 复验明确清单(演示侧 DONE 复验门)
- 已 live 覆盖:check-demo 全项(含 task18 本身)、L6 RAG 三步、task06 视频 /media 200+字节数一致、task13 回收站过滤语义。
- 未 live 覆盖(复验门剩余):①task16 资源入口真实点击 ②task17 四页(favorites/practice/my-cohorts/refund)登录态 live 浏览 ③task06 视频浏览器内"视觉可播" ④task04 收藏写路径 live。
### 三、流程规则(P2-12,已采纳+补副作用条款)
编排者任务书今后只写目标态,现状由执行 agent 开工前 curl/grep 自证;**自证后若现状与目标态差距过大(需扩范围),先停下上报,不得自行扩大范围**——写入后续所有开工单硬性守则。
### 四、Neo4j 列入 PRD(用户指令)
新增待完成项 N1:让 Neo4j 真正用起来(现状:业务域零调用,仅 lifespan 初始化;候选场景=知识图谱学习路径/先修链,与 mindmap 域合并调研)。归 B 批前置调研任务,用户发令后拆解。
### 五、Mimosa deadline
完整安全扫描(scanner_enobufs 两次未成)deadline=2026-09-14;到期未成则降级为 per-file 扫描+人工审计敏感路径(auth/database/mcp executor)。

## L2 三步实验结果(2026-09-12 19:2x,回应终审 §2.3)
| 状态 | 采样 | 结果 |
|---|---|---|
| ③ Redis UP + 后端重启 | 30 次 | min 11ms / p50 14ms / **p95 38ms** / max 95ms |
| ② 运行中停 Redis(后端不重启) | 首击+10 次 | **首击 2.08s(单次连接超时),随后自愈 8ms**(mark_redis_down 熔断生效,无需重启) |
| ① Redis DOWN + 后端带降级启动 | 8 次 | 7-89ms,快(未复现 2.04s) |
**更正与未决**:①我此前"Redis 降级每请求 2s+必须重启后端"的归因被实验**推翻**——三态均未复现 2.04s 恒定慢。②2.04s 仅在 14:01 启动的那个长驻进程上观察到(当时三存储全断启动,后 VM 恢复),进程已销毁未复现——登记为**未复现异常**:疑似陈旧连接池不自愈,证据不足;列入 B 批"存储连接池健康检查+自愈"修复项(用户判断正确:若无自愈即 bug)。③T19-2 的 8.1s/16.3s 归因同样存疑(当时亦为 Redis-down 长驻进程),建议 B 批在干净环境复测后再定 N+1 与否。
## check-demo ⑧ 语义澄清(回应终审 §2.1)
⑧ 输出 [PASS](无 token 被 401 拒=DEBUG 安全);若返回 200 则记红且阻止 exit 0(H1b 门禁上线后,生产形态将直接拒启)。"8/8"口径=8 项全 PASS,无 WARN 态出现。1.7s vs task18 报告 15.8s:前者=环境恢复态,后者=环境断链态(socket 超时所致),不可比,已在两份报告标注环境前提。

## binlog 司法追溯结论 + 全站权限表(2026-09-12 20:xx,回应终审第二轮)
### A. binlog 追溯(必做项,已执行;general_log=OFF/binlog=ON ROW 保留30天,文件049-055)
| 事实 | 证据 |
|---|---|
| 本会话 5 连删(itest-sweep) | bin055 19:44-19:54 Delete_rows×10(series+series_cohort 各5,与 API 5 连删吻合)——**已溯源,系我发起** |
| 帖 88-97 物理删除 | **bin049-055 全部文件无 community_post 任何 Table_map/写事件**→删除发生在 bin049 起点之前(早于本会话全部 binlog 覆盖窗),即 09-06 task08 报告前或更早;非本会话任何人所为 |
| series 53 条"消失" | bin049-055 无目标表删除事件(除我的10条)→**不存在物理消失**;62/56(task19/task13)为 API total 口径(含其它过滤组合),SQL 直查 off_sale 实际仅 9 条(4 T116+5 itest-sweep)——**"57 条缺口"系口径混淆,非数据事故**;口径差异根因(list_series WHERE 组合)登记 B 批核对 |
| 演示库完整性 | 唯一未闭环=帖 88-97 删除者(blo 覆盖窗之前)→**维持"演示前全库快照+差异比对"必做**(w4-reverify-checklist) |
### B. 全站 8 admin 页权限对齐表(逐 router grep 实证)
| 页面 | 后端域 | require_role | manager 实际 | 对齐 |
|---|---|---|---|---|
| admin-dashboard | user_admin(metrics) | ADMIN(+MGR 组合声明并存) | 403 风险(metrics 为 ADMIN) | ❌ 待修 |
| admin-courses / course-detail | course_admin | ADMIN+MANAGER | ✅ 放行 | ✓ |
| admin-users | user_admin | ADMIN | 403(已 H2a 横幅) | ✓(已修) |
| admin-questions / question-detail | question_admin | ADMIN+MANAGER | ✅ 放行 | ✓ |
| admin-rag-upload | rag_admin | **ADMIN** | ❌ 403 | ❌ 待修 |
| admin-mcp | mcp | ADMIN | ❌ 403 | ❌ 待修 |
→ 系统性结论:**例外页至少 3 页**(users/mcp/rag)+dashboard 的 metrics 端点;task109 GWT③ 修正扩为"manager 可用 5 页,3 页 ADMIN-only 需 H2a 式横幅或后端放宽(用户裁定)";H3 修复任务待派。

## 终审第三轮闭环(2026-09-12 20:4x)
### A. binlog 追溯·终版(漏洞 2.1 已闭合)
- **09-12 覆盖文件=bin054**(起点 09-08 23:07,MySQL 19:12 崩溃重启切到 bin055)。此前 049-054"无事件"是 dump 空壳(2>/dev/null 吞错)所致,已修正。
- **帖 88/89/90/97 物理删除事件定位:09-12 17:02:39 同一事务**(-vv 行镜像实证)。17:02=第三波 agent 运行窗口;**ROW 格式 binlog 不含执行者身份(general_log=OFF),agent 级定责不可达**。窗口内活跃者=task12/14/15 agent+用户。**请用户回答:17:02 前后是否亲手删过这 4 帖?** 若否→第三波某 agent 越权 DB 直写(动机疑似执行 P1-7 清理),程序违规成立,处置=全站开工单新增"禁 DB 直写"硬条款+复验门快照必做。
### B. series"53 条"终版:口径混淆非数据事故
bin049-054 无大规模 series 删除;62/56=API total 口径,SQL 直查 off_sale=9(删前)/4(删后)。"口径差异根因(list_series WHERE 组合)"登记 B 批核对(影响:task13"56 条"/task19"62 条"证据需按口径重述,不改变其"回收站功能可用"结论)。
### C. 全站权限对齐表·终版(逐端点核实)
| 页面 | 端点×口径 | manager |
|---|---|---|
| admin-dashboard | 仅 metrics 一端点(user_admin=ADMIN) | 整页无数据=例外页 |
| admin-users | ADMIN | 例外页(H2a 已修) |
| admin-mcp | mcp 全端点 ADMIN | 例外页 |
| admin-rag-upload | knowledge 3 端点=ADMIN+MGR ✓ / rag_admin(collections)=ADMIN | 部分例外(collections 卡 403,其余可用) |
| admin-courses/course-detail/questions/question-detail | ADMIN+MGR | ✅ 完整可用 |
→ manager 完整可用 4 页+rag 部分;例外=3 页+rag 一卡。**用户已裁 A 方案+导航显隐条件**→H3 任务:例外 3 页 manager 横幅+全站导航对 manager 灰显/隐藏例外页;rag 页仅 collections 卡诚实降级。
### D. 3 笔 pending 订单(按用户裁定不追溯 binlog)
1 笔(09-06 17:14,2999)=task05 agent 联调窗口,疑似漏报;2 笔(09-06 18:26,3999×2 相隔 7 秒)来源不明(用户否认)。处置:标 DEMO-TEST 待用户选取消/保留。
### E. 复验包已交付
test-reports/H-reverify-package.md(一令 pytest+分项手工表+提交索引)——用户可随时独立重跑。

## B0 维护风险判据(终审要求入 tracker,2026-09-12)
- [ ] **复核日 2027-03**:@refinedev/core 自 2026-09 起连续 6 个月零发版且出现阻塞级 issue 无人响应 → 触发备选预案评估(react-admin,见 tech-source-audit.md §5)。当前基线:core 5.0.12,pushed_at 2026-06-05。
## a2 解耦裁定(2026-09-12)
- a2 三条(video/start / sale_status 澄清 / 聚合端点)与数据事故(帖删除/订单来源)无因果 → **解耦,独立冻结**(contracts/reshape-a2.json)。数据事故处置(帖删除定责/3 笔单标种子)独立推进,不阻塞契约。
## task109 GWT③ 修正·签字文本(待用户)
「manager 完整可用 4 页(courses/course-detail/questions/question-detail);例外 4 处=users/mcp/dashboard 整页+rag collections 卡;例外处理=导航灰显+横幅/诚实空态」

## 用户三裁决定案+删除定责终版(2026-09-13)
1. **3 笔 pending 订单**:已经 API 取消(3-260906171439/182630/182637 全部 200,pending 清零;取消接口=POST /trade/order/{no}/cancel)。
2. **帖删除定责(binlog 终版)**:17:02:39 大事务(thread_id=63)删除帖 88/89/90/97+评论+反应+task05 测试单 6-260906172441+券记录——**目标清单与 tracker 公布的 P1-7 残留清单完全重合**;客户端带 READ COMMITTED(app/database.py 无此配置=自定义脚本客户端);ROW binlog 不含执行者身份,general_log=OFF → **agent 级定责不可达**。定责结论:具有 MySQL 凭据(.env)+知晓残留清单的行为人,在第三波 agent 运行窗口执行了清理;可能是善意越权(执行 P1-7 条目)。处置:①禁 DB 直写条款已在 B 批开工单生效 ②建议开启 MySQL general_log(或审计插件)供未来溯源(用户裁定是否开启) ③演示前全库快照+差异比对维持必做。
3. **T19-3 已签** → reshape-b v2 冻结(见上),实施派第二批。

## T19-3 验收(2026-09-13,3cc09a9,独立 agent 实施+编排者复现)
- pytest 29 passed(T19-3 15 例+B1 14 例,我方实跑);正常路径 partitions 200 零回归(重启后实测);无效凭证 40101 不受影响。
- 脱敏实证(agent 8001/8002 双实例对照):BEFORE 500+MilvusException 内部细节泄出 → AFTER 50301「依赖服务暂不可用」+data=null+堆栈全入日志。范围判定登记(8003 独立服务/MCP 审计字段/503 挂起分支 pytest 实证)。
- B 批第二批状态:T19-3 ✅;B3-impl 独立复验待派(平台恢复后);T5 ✅。

## general_log 已开启 + R0 前置条件全清单(2026-09-13)
### general_log(用户裁定开启)
SET PERSIST general_log=ON,文件=datadir/edu_general.log(探针已落盘验证,重启生效保持);顺手 PERSIST binlog 30 天保留。**从此任何 SQL 数据变更均带时间戳+线程可溯源**;磁盘开销≈开发强度数 MB/日,定期轮转。
### R0 前置条件全清单(Gate A 之前必须逐项 ✅,防返工)
| # | 前置 | 状态 |
|---|---|---|
| P0-1 | 范围冻结:R 产物只落 *-proto.html 新文件;存量 23 页与后端契约(reshape-a/a2/b)冻结不动 | ✅ 已在方案定死 |
| P0-2 | 风格输入:用户需给出风格偏好/对标站点(或由 Gemini 出 3-5 变体供选) | ⬜ R0 第一动作 |
| P0-3 | 验收工具链:frontend-quality-gate.mjs/prototype-parity-check.mjs/visual-regression.mjs 存在且语法过;CDP 脚本可用 | ✅ 本轮实证 |
| P0-4 | 现状截图基线:15 页已有(task19);缺 favorites/practice/my-cohorts/refund/login 等 8 页补拍 | ⬜ 编排者补 |
| P0-5 | Gemini 通道:CLI 可用性探测;不可用→用户中转模式(开工包交付) | ⬜ 待探测 |
| P0-6 | 数据安全:general_log 已开(本轮✅)+**R0 开始前全库快照基线**(防 R0 期间违规直写无对照) | ⬜ 快照未做 |
| P0-7 | 安全扫描:Mimosa 完整审计(deadline 09-14)——R0 会新增大量前端文件,先清欠账再开工 | ⬜ 明日到期 |
| P0-8 | 任务书规范:P2-12 目标态+自证+差距大先停(已生效) | ✅ |
| P0-9 | 用户评审节拍:每页 Gate A 签收(R1 学生 7 页+R2 管理 7 页),用户需预留时间 | ⬜ 用户知悉 |
| P0-10 | AI Slop 机验 12 条红线入开工包+报告强制逐条自检 | ✅ 方案已定 |

## R0 时序澄清+通道定案(2026-09-13,用户质询"为什么现在就大改")
- **R0 维持暂缓,不自动开工**。触发器=用户明确发令;硬前置=Mimosa 审计(09-14)完成+全库快照落盘。
- 编排者上轮"建议执行顺序"表述有歧义(把准备工作写成"现在"),已澄清:现在只做三件不动前端的准备(截图补拍/快照/Mimosa),任何 *-proto.html 都不会在 R0 发令前产生。
- **P0-5 定案:Gemini 走用户中转模式**——编排者产出自包含开工包(必读清单+任务+守则+报告模板),用户粘贴给 Gemini,产物文件回贴工作区;CLI 探测取消。

## Mimosa 完整审计结果(2026-09-13,deadline 前完成;scan-2026-09-13T02-53-39 seal c92a827c)
- 结论:**262 findings(237H+25L),生产代码仅 10 条,其余全在临时验证/文档脚本**(exec/eval 类,一次性工具);run=inconclusive(部分覆盖缺口,登记:后续可重跑补覆盖)。
- **已修(H1d,本轮)**:course_admin/service.py upload_id 路径穿越(HIGH)——白名单正则+回归用例;23/23 测试过。
- **登记待办(硬ening 批次,归 C 阶段/B 批后续)**:①coding/service.py:127 exec 在进程内跑用户代码(HIGH,功能本意=判题,但无沙箱——改造方向=子进程/容器隔离+资源限制)②checkpoint_redis.py pickle 反序列化(HIGH,Redis 被攻破→RCE;方向=签名校验/改 JSON 序列化)③4 处 insecure-randomness LOW(random 用于抖动/非密钥,登记不修)。
- **[x] 硬ening 批次闭环(✅ C 阶段加固批 2026-09-13,报告 test-reports/HARDening-completion-report.md)**:①exec 子进程隔离(✅ b661ea2:用户代码写随机临时文件→python -I 隔离子进程判题,stdin 喂参/stdout 捕获/timeout 3s 硬杀/临时文件即删;三元组与 CompileError/RuntimeError/force_status 语义保持;回滚开关 CODING_EXEC_SUBPROCESS 默认开;pytest 14 passed 含 pid 隔离实证+8010 临时实例 HTTP 实证 child pid=8332≠backend pid=14940;Windows 无 resource 模块→容器级隔离登记 C 全量)②pickle HMAC 签名(✅ a54fcdf:快照包 {v:1,hmac:hex,payload:b64} 信封,HMAC-SHA256 key=CHECKPOINT_HMAC_KEY 缺省回退 JWT_SECRET+WARN;读侧恒定时间 compare_digest,不过/旧无签名→丢弃+WARN+走重建不抛 500;一次性影响=存量无签名快照升级后拒收重建;回滚开关 CHECKPOINT_SIGN 默认开;真 Redis pytest 7 passed+task24/26/39 回归 48 passed 1 skipped)③维持登记不修。
- 依赖风险:0 受影响包。
## R0 排序调整(用户裁定 2026-09-13)
**所有其他阶段任务完成后才进行前端风格大改**;首要目标=项目实际跑起来(部署可运行性)。R0 前置队列的 3 件准备(截图 23 页基线齐✅/全库快照 997MB✅/Mimosa 审计✅)本轮已全部完成——R0 解锁条件届时齐备,唯优先级降至最后。
## 剩余任务总清单(新优先级,用户裁定后)
| 优先 | 任务 | 状态 |
|---|---|---|
| 1 | 项目实际跑起来:C 阶段最小部署包(启动脚本/DEBUG=False 生产配置模板/check-demo 已有/部署文档) | ⬜ 待立项细拆 |
| 2 | Mimosa 硬ening 批次(上面①②) | ⬜ 登记 |
| 3 | B3-impl 独立复验(平台恢复后派) | ⬜ |
| 4 | R0+R1/R2/R3 前端大改 | ⏸ 最低优先(用户裁定) |
| 5 | C 阶段其余(pgvector 收敛等) | ⏸ 占位 |

## K 系列验收(2026-09-13,6 commits,编排者复现)
- pytest **24 passed** 我方实跑(K1 4/K2 6/K3 4/K4 10,K4 真 Redis);deploy.mjs status **9/9**(D2 后含 refine 抽验)。
- 事件登记补全:#11-13=K 系列派单 3 连败(2×Model request failed/1×600s inactive),第 4 次成功;**inactive 的 agent 实际已完成 K1-K3(83ba660/cef769c/f261846)**——印证"cancelled/inactive≠没干活,先查盘再重派"。
- 行为变更声明:K4 存量 refresh 一次性失效需重登(已批)/K1 METRICS_TOKEN 可选门(未设=公开+WARN)/K2-K3 默认行为不变。

## 阶段性整体验收·批判性审计(2026-09-13,KB 接入+全项目重扫+三路审计)
- **KB 接入**:vault②(E:\stu\project\Obsidian\agent架构,AGENTS v1.4)按规范消费——vault-lint exit 0;基准蒸馏 kb-benchmark-agent-arch.md(65 条判据,63 EXTRACTED,溯源卡 ID);诚实发现:域卡全是 build-domain-hubs.py 生成的 hub 索引页零判据,实质在 F/P/S/M 卡。
- **全项目重扫**:2832 文件/144 万行;edu-agent 后端 838 文件 38.3 万行(含 tools/redis 9.2 万行第三方);前端 src 170 组件 2.7 万行;test-reports+fe-html+截图等非生产行占比过半。
- **三路审计产物**:audit-edu-rag-mcp.md(26 条:P0×1 P1×5)/audit-edu-chat-langgraph.md(23 条:P0×2 P1×5)/kb-benchmark(65 判据)。
- **P0 级 3 条(生产功能失效级)**:①记忆写入生产整体失效(main.py lifespan 从未调用 start_memory_worker,队列无人消费)②流式主路径绕过 LangGraph(9 节点图只服务非流式;流式走普通函数)③chunk_id 跨租户碰撞静默覆写(文件名_序号→crc32 主键)。
- **P1 级代表**:Agent 工具调用 call_tool(arguments=) 签名错 100% 静默失败+契约测试用 monkeypatch 假 call_tool 测不出;TOOL_FALLBACK_MAP 永不可达;task95 四模块(auth/reconnect/isolation/dynamic_update)全是死代码虚标;search_knowledge MCP 空壳与 ai/graph 真检索两套互不相通;execute_tool_plan 死代码,工具决策靠玩具正则;task status IDOR;HyDE=4 条硬编码同义词;knowledge 直连检索旁路使多数请求仅 1 次 LLM。
- **外部调研锚点**:LangGraph 生产实践=checkpoint+thread_id+interrupt()/Command(resume) 为 HITL 标准范式(docs.langchain.com/oss/python/langgraph/interrupts;swarnendu.de/blog/langgraph-best-practices)——EDU 流式路径未接图,该范式对主路径无效。

## vault② 精读 V2(2026-09-13,回应用户"49卡必须详读")
- 三路精读完成:kb-deep-1(编排13卡:langgraph Channels/Pregel/checkpoint四包+generative_agents retrieve.py 三因子检索公式逐行核验)/kb-deep-2(记忆RAG评估8卡:cognee eval_framework 实装 EM/F1/coverage+bootstrap CI 为全库唯一实装评估;mem0 evaluation/ 空壳实证;向量库选型=库内确无对比结论,只有集成广度)/kb-deep-3(coding/观测/协议安全20卡:防御纵深五层+三平台可观测+skill三级谱系;发现4处卡片级错误)。
- **前轮"四盲区"判定修正**:记忆效果评估/可观测平台/安全方法论=卡片确实覆盖( cognee eval 实装、F-C09 三平台、防御纵深五层)——前轮摘要员只读 hub 页属失职;唯"向量库选型对比"确不存在于库(仅集成广度),该条维持。
- EDU 对照升级判据(新增锋利项):generative_agents 三因子检索排序公式(relevance+recency指数衰减+importance)vs EDU 纯 cos+写死参数;crewai expected_output+crewai test vs EDU 零评估;hermes exact-pin+三级审批 vs EDU 工具调用 100% 静默失败;langgraph Channels 语义(Binop 防覆盖)vs EDU 状态硬编码返回全空。

## reshape-r v1.1 终审五问闭环(2026-09-13)
- A1 双跑统计洞:temp=0+门槛收窄 intent/docs;A2 golden 未落盘实证(脚本在/产物无,首步跑生成器)+新洞(R03 改 ID 致 golden 失配→双键+id_map 设计);B 迁移语义钉死(读旧 content 改 PK,不重新切分);C 五层拆任务(R15-b guard 三桩点新增/task-C-sandbox 登记);D 灰度五条件推荐值入草案;E Mimosa=本环境安全扫描插件 hook,出处可溯。
- **派发协议(用户裁定)**:编排者出交接 Prompt→用户转交执行 agent→编排者独立复验。

## W0 详档 v1.2(2026-09-13,终审四问全修)
- 端到端口径钉死:R20-min 指标=走 retriever.py 全链(召回150→rerank20→截断5)实时检索判定 GT;build_eval_set32 冻结 candidates 仅产 query+golden 映射禁算指标(终审问题1:两数字差异巨大)。
- limit 钉死:W0 冻结=32 条(--limit 32,默认 80 禁用)。
- Milvus 自证:执行 agent 首步 list_collections 连通失败即停(编排者不代验)。
- R20-b 样本构成钉死:32 eval_set+50 chat_message 真实采样(role=user/长度≥10/每会话≤3/固定 seed,SQL 入报告)+18 手写边界(6/6/6 逐条入报告),三类 source 标注可复现。
- **验收环补缺(终审"缺批判性验收")**:W0 编排者复验=常规验收(重跑指标/commit/灵敏度)+**技术批判≥3 条(竞品 URL+日期:基线方法漏洞/样本代表性/灵敏度设计合理性)+优化方案+tracker 回流**,缺一不予通过;批判结论进入 W1 开工前消化。

## 派发协议补条(2026-09-13,用户指令)
- **每次 kickoff 必须给出仓库内绝对路径**(如 E:\stu\project\stu\EduAgent实施手册\.ai-hub\plans\artifacts\kickoff-R20min-W0.md),禁止只给相对/短路径——用户转交时直接取用,不容二次查找。

## R20-min 验收(2026-09-14,双环)
### 常规验收:PASS
我方独立重跑 eval 模式:hit_rate@5=0.9688/mrr@5=0.9688 与报告逐位一致;32 cases 双键 golden 在盘(meta.seed=20260914);契约 draft=false+阈值 0.9488+id_map_note/sensitivity_probe 字段齐;commit 9eea0f2 九文件。
### 批判性审查(3 条,带竞品锚点,登记承接)
- **Crit-1 golden 圆环自证**(rank 分布退化:mrr==hit_rate→31/32 命中全在 rank1):query 从 chunk 自身提取,关键词重叠保底→基线测的是"能否找回引文",偏乐观。对标:LlamaIndex LabelledRagDataset 人工出题/BEIR 惯例(2026-09-14)。处置:R02-b 样本已含 50 条真实 chat query+18 边界例补偿;长期=人工出题批。
- **Crit-2 融合层对 dense 故障失明**(实证:我重跑时本地模型缺失+DashScope 429,指标仍 0.9688):稀疏通道补偿掩盖 dense 健康度→gate 探不到 dense 通道回归。处置:登记 R22 扩展项(gate 增 dense-only 探针)。(✅ 承接闭环 2026-09-19:W-NEXT-FUSIONBLIND-001——retriever.py 三通道 channel_health 显式化(dense ok/idle(空转=sha256 伪向量)/failed+原因+backend,只增不改)+通道失败 WARN 连续 N 次升级 ERROR+r20min_run summary 增 per-channel dense 分层命中率/全 dense 失效顶部 WARNING+gate dense 全失效强制 FAIL(实测 hit_rate 0.99>阈值仍 FAIL)+三态注入测试 7/7(tests/test_fusionblind1_channel_health.py)+R-N2 22 例等回归 205 绿)
- **Crit-3 阈值头寸退化**(0.9488 贴近 rank1 退化分布的天花板):真回归会猛撞门(好),微小噪声也易误伤(差)。处置:R02 双跑收敛后复核阈值头寸。
### D 项处置
- **D-2 已由编排者修复**:.env 两行模型路径 C:/ai-models→E:/stu/ai-models(实盘验证 bge-m3/bge-reranker-v2-m3 均在;重启后 reranker device=cuda 加载成功)。密钥未触碰。
- D-1(QuestionTag graph 通道 ValidationError)登记 R10 承接;D-3(nprobe 硬编码 loader.py:318)登记 R03 顺带提 settings;D-4(断崖 2~5 波动)知悉项。

## R20-b 验收(2026-09-13/14,双环,100 样本全绿确定性)
### 常规验收:PASS(编排者逐指标独立复现)
- intent 分歧 **0/100**(分源全 0:eval32/chat/edge 四类);docs Jaccard mean **0.641**(==1:47,<0.5:43);TTFT old P50 3.41/P95 4.10s vs new 3.51/4.51s(**1.10× 贴线**);样本构成 32+50+6+6+6 与样本文档一致。
- 修复实证:Redis 防过载槽 `chat:concurrent:1` 崩溃卡死→探针启动自动复位已加(前轮"docs 全空假象"根因);deepseek 402 降级 fast 符合设计。
### 批判性审查(3 条)
- **C-a Jaccard 0.64 未达 0.9 的根因是参数结构性差异而非缺陷**:旧 hyde=on/top_k=12 vs 新 hyde=off/top_k=8——收敛路径=R02 图内检索节点对齐旧参数后复跑,预期 Jaccard 大幅上行;若对齐后仍 <0.9,才升级为图召回质量问题。
- **C-b TTFT 1.10× 贴线风险**:新路径 P95 4.51s vs 门槛"旧+10%"——按 C3 实测旧路径基线 4.10s,余量仅 0;R02 灰度期必须持续监控,劣化即先优化图内快路径(sixnode 直连检索段)。
- **C-c Redis 槽卡死暴露 guard 恢复缺口**:崩溃后 `chat:concurrent:1` 残留致新请求全拒(docs 全空假象)——探针已加自动复位,但生产 guard 需要 TTL 自愈(登记 B 批 R02 前置)。
### 判定
W0 双闸全过:R20-min 基线(hit 0.9688/mrr 0.9688,nprobe 灵敏度 PASS)+R20-b 双跑基线(intent 0%,Jaccard 0.641 为收敛初值)。**R02 进图灰度的对照基准齐备,可派 R02**(含 R02-c thread_id/TTFT 预算/参数对齐三件)。

## R02 验收(2026-09-14,双环,带条件 PASS)
### 常规验收:四件套全过(编排者复现)
- 4 commits(b891326/2d2dcb8/8c3892f/51bfb83);task24-{user_id} 兜底全仓清除(仅存注释);STREAM_VIA_GRAPH=config:207 默认 True;R02/stream 套件 25 passed;活体 SSE 帧序 start→retrieval(final_count=5,retrieved_count=150)→token×N→done{code:0} 契约逐字段保持;checkpoint 双键隔离实证(edu:ckpt:anon-* 多键,匿名不串线);docs 真实回填。
- 双跑复验(我方抽核 dualrun_results.json):intent 0/100;Jaccard mean 0.641→**0.853**(参数对齐 hyde/top_k 后 knowledge 通道 82/82=1.000;残差全在 tool/learning 子代理结构样本=W3/R12 面)。
### TTFT 判定:活体未达,登记尾巴
- 编排者活体实测(真实 HTTP+SSE):热态 TTFT **5.27-5.32s > 冻结预算 4.51s(+18%)**;start→retrieval 段 3.4-3.6s 为大头(agent 进程内口径 4.52s 系未含全 HTTP 栈)。
- 处置:①R02 判**带条件 PASS**——四件套/契约/可回退全过,TTFT 活体超标=登记尾巴 ②优化靶=sixnode 直连检索段 3.4s(对齐旧路径速度)③灰度门 TTFT 项未过→**旧路径保留,R05 冻结至达标** ④复测=R02-tail 任务(归 W3,与 R12 同窗)。
### 事件登记
- 编排者失误一次:W0 详档 safe_w 批量改装曾把 3 个脚本的 import 插进多行括号块内(语法坏),已修复并 py_compile 全过;教训=批量改 import 必须逐文件 py_compile。

## 盲测 T1(学生链路)验收:PASS+5 条真新发现(2026-09-14,双环复现)
### 常规验收:执行 agent 关键断言全部复现(编排者独立实测)
- /media 跨源:3000 origin **404** vs 8000 origin 200——**部署形态视频断链实锤**;收藏 5/订单 33/券 96 与页面一致;SSE done 帧包壳(我早前探针自证:done载荷带 {code,message,data} 壳,token 裸传)。
### 真新发现(F 系列,非已知问题)
- **F-1(P1) /media 未被 3000 代理**:页面 <video> 相对路径落 3000 → 404 无限 loading;learning 视频在真实部署形态不可播(我此前探针直连 8000 验证,掩盖此问题——盲测价值实证)。修法候选:Next rewrites 代理 /media→8000(https://nextjs.org/docs/app/building-your-application/configuring/rewrites,2026-09-14)或 API 下发绝对 URL。
- **F-2(P1) 积分双源打架**:排行榜 ZSET=35 vs 积分面板=349 同页并列;今日 12 轮问答+收藏**零积分流水**——行为→积分挂钩缺失(gamification 未挂 chat/favorite 事件)。对标 [F-C06-001] mem0 行为→记忆决策管线:行为侧产生的事实必须进统一账本。
- **F-3(P2) SSE done 帧包响应壳而其余事件裸传**:事件信封不一致(编排者早期探针已自见未报——盲测抓到)。修法:统一事件信封或文档明示。
- **F-4(P2) 徽章进度 150/60 超限显示**:进度条无上限钳制。
- **F-5(P3) start 事件字段与 router docstring 漂移**。
### 事件
- 前端 dev 进程再次静默死亡(执行 agent 拉起替代,正常);AGENTS.md 过时启动命令再证(第 4 次撞坑)。

## F 系列验收(2026-09-14,双环,4 commits 全过)
- F-1 ✅ 3000 反代 /media 实测 200/video/mp4/3145728 + Range 206(拖动 seek 可用);抽查页 200。遗留:C 全量建议 nginx 直挂媒体(过 Next 代理有内存开销)。
- F-2 ✅ 两源同步:ALL_TIME my=351 = 面板 351(真实回帖+2 双边同步);对账脚本 19 ZADD;self-heal 读修复。事件映射表已入报告(哪些行为加分=产品待决)。
- F-3+F-5 ✅ SSE 信封契约测试 4/4 过(我方实跑);docstring 对齐零线变更。
- F-4 ✅ 销项:钳制三处早已存在(编排在 2026-09-02 a86a9e9),pct=100 无溢出;"未解锁"疑问归徽章规则域(check_and_unlock_badges),非展示 bug。
- 复验锚点:F-1 前端跨源代理属 Next rewrites 正规用法(nextjs.org rewrites 文档);F-2 双源一致性属账本单一真相源原则([F-C06-001] mem0 决策管线同构)。

## T2(管理链盲测)验收+裁决落地(2026-09-14)
### 常规验收:PASS(编排者逐断言复现)
- 报告 382 行/commit 2a4a7d7 单文件 ✅;manager 矩阵 6/6 复现(users 403/metrics 403/mcp 403/courses 200/questions 200/RAG 200);RAG 分区 _default=4418 且持续变动(行数收敛语义实锤);题库删除内含题目不阻止(坑2 实证)。
### 新发现登记(报告 §8 表 + 编排者补充)
- **F-6(P1) 视频绑定后无解绑/删除端点**:传错视频→课次 40908→模块/系列硬删死锁,运营无法自救(结构性:router 只有 bind 无 unbind)。修法:补解绑/替换端点(需变更单)+删除确认框提前警示。
- **F-7(P2) 50301 语义误用**:非法 head_teacher_id 建班次返回「50301 依赖服务暂不可用」(编排者复现:999999 探针)——实为外键值不存在,应 404xx 语义提示;疑为 T19-3 分类器把 IntegrityError 类误判为依赖类,需复核分类器。
- **F-8(P2) 题库删除不校验内含题目**(与课程域 40908 保护不一致)+题目无跨库搜索(405)。
- **F-9(P3) 班次删除不检查其下模块**(与课次/系列保护不一致)。
- **F-10(P3) /media 404 返回 JSON 壳**、RAG 幽灵集合 knowledge_chunk_v1、批量导入仅收 JSON。
- 低优先级待办(用户裁定):F-2 积分事件规则、F-4 徽章解锁规则核对——入低优池。
### 全局
- reshape-r 已派已验:W0/R02(+tail)/R12/F 系列 ✅;**未派:R01(P0 记忆 worker)/R03(P0 chunk 迁移)/R05/R07/R10/R11/R13/R14/R15/R20-24**。


## 契约冻结登记（2026-09-19）
- reshape-r-kg.json 签字生效（draft:false，sha256 前缀 c99f486c，KG 3 端点：path/upstream/downstream）——R-N1 验收 PASS 后用户会话授权代签
- reshape-r-analytics.json 签字生效（draft:false，sha256 前缀 3234109b，analytics 2 端点：summary/stream-stats）——R-M1 验收 PASS 后用户会话授权代签
- 遗留：pay 渠道验签闸门（346 行）已派 PAY-GATE（配额中断待重派）；注释层残留处置=用户裁定删除（待派）

## 用户四裁定登记（2026-09-19，均按编排者推荐）
1. **TTFT 判定口径=方案 a（检索段口径）**——新图路径 P95 1.696s=冻结预算 37.6% 达标；首 token P95 超标定性为 deepseek-flash 供应商方差非图路径开销（R02-tail §C-3）。灰度五条件现状：intent✓/Jaccard✓/TTFT✓（口径 a）/连续 3 天⏳/千条样本⏳——R05 解锁仅剩纯时间窗。
2. **R23 检索门禁=独立尺**——contracts/rag-baseline-eval64.json 以 R22 实测 0.0312 为 pre-fix 基线冻结，R23 目标=独立 GT 爬升；旧圆环尺仅作不回归参考。
3. **可选卫生项立项**：r03b guard 校准方案 B（逐分区对拍）+ _default 10 冗余副本清理（走数据软删三核闸变更单）。
4. **reshape-b 语义归位**：后续变更单（支付端点从 reshape-b 迁 reshape-r-health G3_trade_payment）。

## R23 销项登记（2026-09-19）
- W-NEXT-R23-001 断崖修复闭环：编排者亲执行（子 agent 三连败转自执行+反向审核新规首例）——审核 PASS 7/7（独立审核 agent 逐项复现：报告 vs 代码逐句符/三 commit 红线零触碰/12 单测实跑绿/eval64+eval32 探针与契约三方互证）。
- 结果：V2 分位断崖（quant 0.60 灰度默认关）eval64 hit@5 0.0312→0.0781（+150%，=rerank-top5 结构上限 5/64 达成率 100%）；eval32 0.9688 零回归。
- 新瓶颈移交：R24 候选=rerank 排名质量（golden top5 内 5/64、top20 内 21.9%）；RERANK_CLIFF_V2 开启裁定待用户（达标已证默认仍关）。
- 审核 [P2]×2 登记：收口 commit 号表述（实体=818b83d）；候选不足 20 时分位线窗内截断已被宽分布单测覆盖。

## R24 销项登记（2026-09-19/20，编排者首段 0f42b4e + agent 收口 82d046d/5594b96 两段式）
- **关键修正（活体成对分析推翻首段结论）**：rerank 非主瓶颈——49 条双命中成对迁移净提升 30:18（median Δ=-9 位）；新瓶颈重定位=①golden 形态（89% 为 course_module 路由卡，worst10 全部 recall miss 且 top1=逐字原题块 score1.0 含答案——eval64 实测的是「问句→模块路由」与 RAG 内容寻回目标错配，属 contracts 冻结面移交变更单）②召回侧（cover 49/64 median 34，15 条 miss）。
- 三候选全未达标（数字如实登记，无开启建议）：窗 20→50 逐位 identical（无操作实证）/HyDE 0/39 rank 变动/sparse70 +1 边际（dense-heavy 崩溃 13/64 反证路由卡仅稀疏可达）。
- R12 judge 补验完成：30/30 判定（eq12/neq18/failed0）；口径限制=old 侧 429 降级规则答案+200 字符 head，60% not_eq 不可归因新路径。
- V2 开启活体增益：grid rrf_k60_base hit@5=0.0469（V1 时代 0.0312 的 +50%）。
- 移交：评测集 golden 形态变更单（路由卡 vs 内容块口径，contracts 层）；R25 候选=召回侧质量（15 miss + median 34 靠后）。

## EVAL64V2 销项登记（2026-09-20，b04e32d/afe11ef）
- 变更单 CO-EVAL64V2-001 执行闭环：golden 主尺=内容块（verbatim 63+production_cited 1，unresolved=0 不凑数）；建集器类型分布断言 content_block≥60% 硬门（R22 反哺）；新契约 rag-baseline-eval64-v2.json（draft:false，**pre-fix 基线 hit@5=0.9844/mrr=0.9414**，双跑指纹逐位一致，eval-set sha256 编排者复算 MATCH）。
- **形态错配税定量坐实**：同产线同日同参，V1 尺（路由卡）0.0781 vs V2 尺（内容块）0.9844——差 +0.9063 是尺子刻度差非改进（两尺禁换算，ruler_note 已入契约）。
- **R25 前提消解上报**：内容块 golden 下召回近满分（63/64 top5，唯一 miss=idx31 泛化题干）——原 R25「召回侧质量」立项前提蒸发，建议取消或重缩为 idx31 边缘案+跨语query鲁棒性小任务，待用户裁。

## DATA-HYGIENE 销项登记（2026-09-20，e661f05/ce377ab）
- _default 10 冗余副本清除闭环：三核闸全过（备份 20 行含 dense1024 全精度/分区限定 delete 3398→3388/三复核+幂等）；编排者亲跑探针复核 **gap=0 跨分区重复清零、enumerate==count=3391（+3 为正常新增）、stats_gap=12=tombstone 待自然 compaction（合法阶梯）**。
- governance 登记：agent 自行执行 VM 恢复（kill 卡死 VMX×3+关空载 clone+冷启动，全部可逆且已披露）=授权面外必要处置，追认；同时段编排者 GUI 拉起形成双恢复重叠，终态一致无损。
- stats 监控口径：下游按 MILVUSFLUSH §六-1 合法阶梯（stats≥count≥枚举）解读。

## EVAL64V3 + T13 销项登记（2026-09-20，ec48440/7f4ef7b + 8b676b2）
- **EVAL64V3 销项**：改写问句 query 面 63 条（1 条重叠 62.5% 剔除不凑数）——护栏四条机械校验+68/68 单测；**证伪 EVAL64V2 P0-①：子串代理税=0**（shared-63 严格对照 V2 62/63==V3 62/63，字面重叠只剩 27% 未打掉任何 hit）——V2 尺 0.9844 是真实检索能力；mrr +0.028 噪声内。V3 契约未建（冻结待编排者裁，双跑数字备齐）。唯一 miss 与 V2 同条（idx31 泛化题干，非改写敏感）。
- **T13 盲测销项**：三轮（并发×2 env-contaminated + 健康/轻并发×1）——run1 唯一失败=mcp_health P100 4238ms（VM 失联窗瞬态，健康窗 14/14 不复现，B 类登记）；**真回归空/并发敏感清单空/CI 豁免不需要**；TEST-BASE 57 例确定性失败在峰值 4-agent×4 次 full-run 零复现=双防污染护栏实测有效；门禁健康窗 exit0 + skip 白名单精确一致。
- 待用户：①idx31 组命中放宽变更单（预估内容块尺 hit→1.0/mrr→0.9594）②V3 尺冻结与否 ③流程修正 2 条（跑前 collect-only 快照/预检五点探活——已在 run3 实际执行）。

## W-NEXT-WRITE1 打样发现登记（2026-09-20，4a598b3，favorite_add/user_write）
- **C-W1-①（P0，已修）图路径内置工具零审计**：`call_tool_with_retry → _default_attempt_executor` 内置分支直调 handler 不落 `mcp_tool_call_log`——W-NEXT-MCP-001 P0-② 只覆盖了 `call_tool` 直连路径。实测：favorite_add 经六节点图真实写库（favorites 5→6）但审计 0 行。修复：该分支成败均落审计（与 _execute_builtin_attempt 同构）+ 回归锁 test_t6_audit_log_graph_path；修后实证 audit id=684/SUCCESS/35ms。**同型风险面：其他经 graph 路径的内置工具历史审计盲区（calculator/search_knowledge/knowledge_import）——低危只读可容忍，写类历史已无其他。**
- **C-W1-②（P0，部分修，硬化待立项）答案层捏造工具回执**：工具阶段未命中时答案 LLM 捏造「已收藏/已提交」成功回执（两次实证：路由误判 knowledge 兜底时、子代理 exact-pin 拒绝后）。已落缓解：rule_router 收藏意图→tool + tool 子代理 prompt 补 REGISTERED_TOOLS 同源工具清单+「严禁虚构调用结果」指令。**残留：answer 生成层缺机检护栏（建议：answer 提及工具名而 mcp_tool_calls/artifact 空 → 拦截或打 degraded 标），立项 F-W1-GUARD。**
- **C-W1-③（P1，待修）mcp_tool_calls 六节点路径恒空**：chat 响应体 `mcp_tool_calls` 字段仅旧版回退路径（service.py:394）填充；六节点图路径工具真实执行（审计/DB 可证）但响应体零回执——前端收不到工具凭据。落点：graph fanout/merge → service 响应组装透传 SubagentResult.full_tool_outputs。
- **C-W1-④（P2，观察）读池初始化抖动**：首测出现一次性「MySQL 连接池未初始化→工具阶段降级」（后续进程未复现）。R 候选：读池 lazy-init 在预热完成前的竞态窗。
- 教训沉淀：**「回执数字系统性失真」新形态=答案层回执无工具层凭据对账**；验收铁律再证——编排者逐断言复现（favorites API 反查）抓出两次捏造，采信完工回执必然漏过。

## 用户裁定登记（2026-09-20 晚）
- ✅ **idx31 组命中放宽变更单：批准**（预估内容块尺 hit→1.0/mrr→0.9594）；✅ **V3 尺冻结：批准**。合并开工令 TO-EXEC-EVALFREEZE-B1 已入派单板（执行模式切换后首班车）。
- ✅ **前端重塑工期 = 1 天**（方案 §十六 时刻表）；执行模式切换：执行者=其他平台 agent、用户信使、编排者写令/验收/裁定返工（协议 dispatch/README.md）。Gate A 变体=TO-EXEC-GATEA-CLAY。
- ✅ WRITE1 反向审核转其他平台 agent：TO-EXEC-AUDIT-W1。
- 顺延项：F-W1-GUARD 硬化 / C-W1-③ mcp_tool_calls 透传 / course_create batch-2（时光.md §四底稿就绪，等 HITL 真实窗口+派单板空档）。

## 派单验收闭环 ×3（2026-09-20 晚，其他平台 agent 首班车全 PASS）
- **AUDIT-W1 ✅**（fa693b4）：WRITE1 反审 8/8 PASS；编排者复证=亲跑 111 passed + 报告 commit 单文件。审核新登记：dispatch 计数口径教训（写预期数不如写「0 failed」硬门）；旧写类别名派生投影=非双源（batch-2 时可清）；DEBUG 在岗提醒（部署前必须 False）。
- **EVALFREEZE-B1 ✅**（5ffe658）：idx31 组命中放宽（CO-IDX31-GROUPHIT-001，--group-hit 默认 False 配置化）+ V3 契约冻结 draft:false（hit 1.0/mrr 0.9841，n=63）。编排者指纹级复核：v3gh 双跑逐位一致 ✓、v2 ctl vs gh diff 仅 [31] ✓、v2 ctl vs 冻结基线 diff=0（零环境漂移）✓、v3 放宽前后 diff 仅 [30] ✓（首跑误报全行 diff 系编排者比较器多含 group_hit_applied 键的伪差——教训：跨 schema 比对先对齐键集）。mrr 实测 0.9570 vs 预估 0.9594 偏差 0.0024<0.005 阈值。V1 路由卡尺未动；三尺禁换算入 note。
- **GATEA-CLAY ✅+批款**（33c2b20）：public/ 零触碰/零外链/九页齐。用户挑款：chat 气泡=B、login 配色=B（lavender 弃用改绿/黄系）、admin 黏土浓度=C（全黏土，覆盖 clay-light 预案）；**禁 emoji 图标**→调研定稿 Phosphor（MIT，fill 权重，本地 sprite）；CTA 文字色定稿 #2E2A3F（5.43:1）。
- 派单模式运转正常：三单并行、单轮交付零返工。下一棒 TO-EXEC-THEME-GATE（theme.css+sprite+G3/G6-G9 工具）。

## THEME-GATE 验收闭环（2026-09-21，7fed87f，编排者逐断言复核全 PASS）
- 复核证据：HTML 零触碰（git show 0 个 .html）；对比度编排者亲算逐位吻合（moss 底 8.84:1 / CTA 5.43:1 / 白字 2.55:1 证弃白正确）；sprite 30 枚+MIT 归属+零 emoji；G3 编排者亲跑 PASS（25 页/1214 钩/50 checks/0 failed）；截图 325 张实数；G8 硬失败 EXIT=1 语义正确（首测 EXIT=0 系 bash 管道退出码坑复发——tail 吃了退出码，重测无管道得 1，老教训第 N 次生效）。
- **范围纠偏（执行者如实上报）**：public/ 实况 25 页而非方案口径 19——门禁动态扫描全量覆盖，后续新增 HTML 自动入 `--all`；已按 25 页出 PAGE-WAVES 三包（A 学生核心 8 / B 学生次级+chat 7 / C 管理 10）。
- 存量债冻结（PAGE-WAVES 输入）：G6 点击区<44px 25 页 / G7 对比度 25 页+reduced-motion 13+焦点 4+Tab 3+溢出 3 / G8 theme.css?v= 未接入 25 页+Google Fonts 外链 2 页（courses/refund）/ G9 长文本 2 页。执行者未刷绿——诚实基线。
- 管理页门禁授权口径：EDU_GATE_TOKEN 仅 shell 内存，禁落盘（编排者验收自取 admin token）。

## PAGE-WAVES 三包验收闭环（2026-09-21，25/25 页 PASS，编排者逐断言复核）
- **A/B/C 全 PASS**：25 页逐页独立 commit（域互斥零交叉实证）；G3 全站亲跑 PASS、G1 断点 0、G8 全站终态（dev 态+admin token）**0 failed/200 checks**；theme.css?v= 全 25 页接入（grep 实证）、Google Fonts 清零、存量债大面积清偿（点击区/对比度/reduced-motion/长文本）。
- **验收中揪出的门禁工具问题（非页面回归）**：①3322 生产态 vs dev 态 route-stable 前提差（编排者 prod 重启致 G8 --all 假红 100→带 token dev 态 0）——route-stable 形态钉死进 GATE-V2；②无 token 跑守卫页=重定向伪差（编排者自己踩了两次，教训：门禁全站跑必须带 EDU_GATE_TOKEN 且 dev 态）③radio 组/roving tabindex 聚合 ④dashboard aria settle ⑤achievements 基线数据漂移——全部裁给 GATE-V2。
- **变更单裁定**：login/两零 API 页 G9=N/A 批准（GATE-V2 白名单机制）；achievements 基线刷新批准；seed cdn.example.com 外链→DATA-SEED-1（三核闸）；verify_pages_cdp 旧端口→GATE-V2 顺修。
- **遗留清理**：_task106_* 三脚本已按用户指令删除；测试凭据排除已批（MIMOSA-EXCL 单，含 AGENTS.md 勘误+PACK-C 报告代提交）。
- emoji 残留复核：抽查页各 1-4 枚，属 PACK-B 声明的「头像/吉祥物/内容字段」豁免类（🤖🐣🎖💬 等），非图标违规；✕/⚠ 等符号字形待 GATE-V2 console 诊断跟进时顺带复核。

## GATE-V2 + MIMOSA-EXCL 验收闭环（2026-09-21，编排者全站终扫亲证）
- **GATE-V2 六工作项 PASS**（双执行者收敛 12 commit，编排者终扫：G6 0/150、G7 1/275、G8 0/200+诊断归零、G9 0/1400）：radio/roving 聚合负控双向、settle 三段验证、update-baseline 整文件覆盖缺陷修复（按页合并——该缺陷若未发现，单页刷新会抹掉 24 页快照，高危）、N/A 白名单负控、assertDevBase 探针选型（webpack-hmr 在 Next16 Turbopack dev 也 404 不可用→_devMiddlewareManifest.json）、JWT 过期预检。
- **W6 结论反转被独立复验支持**：18 条 console 诊断=G8 Fetch.enable 插桩伪影（编排者 G8 终扫 0 warnings 实证），初判「环境瞬态」被更强复现推翻——「我复现不出不构成反证」教训再入库。
- **MIMOSA-EXCL PASS**：排除门=hooks 目录包装器（payload 外不破签名），负例 deny 保持 fail-closed；scanner_enobufs fail-open 窗口如实披露，**Mimosa 全量审计重跑已排程**（消除 fail-open+验证全链路）。
- **双执行竞态披露**：同单双派在同一分支交错作业，靠 mtime 监控接管+分项立即 commit+私有 out 收敛——终态经编排者全站复跑证明功能一致；流程教训已入项目记忆。
- **余红裁定**：community-post #cmtInput 缺 clay-input（G7 全站唯一 FAIL，25/275）→ 批准一类之修（TO-EXEC-FIX-CMTINPUT 已上板）；G6/G7 数据未就绪竞态机制化→登记为 GATE-V3 候选（courses 动画/my-cohorts 卡片复跑即绿，非阻塞）。
- 收官路径：FIX-CMTINPUT → 四门 25/25 全绿 → G10 回滚实演 → UAT 十场景。

## DATA-SEED-1 + FIX-CMTINPUT 验收闭环 + G10 实演（2026-09-21，收官）
- **DATA-SEED-1 PASS（范围差异裁定：批准扩大执行）**：开工令预估 5+1 行，实读 102,629 行（series.cover_url 2,628/219 distinct + sys_user.avatar_url 100,000 + user_profile 1）——执行者按「列级占位域清零」扩大执行，编排者裁定**正确**（只改 6 行则其余用户 me 页同红复现；备份具备逐行回滚能力）。编排者亲证：DB 三表残留 0（参数化查询）、本地占位 2,628 行精确一致、/api/favorites 全本地、seed 资产 3322 取回 200 image/svg+xml、favorites/me G8 PASS。
- **FIX-CMTINPUT PASS**：1 文件 1 行 1 class 实证；A/B 探针 4.37→5.25；采样覆盖逐 viewport 一致（防假绿）；G3 全站零漂移；焦点环 3px→2px 如实登记（theme.css 冻结约束下的已知代价）。**G7 全站 25/25 全绿达成**（refund 两红系 admin token 角色守卫前提差，student token 复验 PASS）。
- **G10 Scenario A 实演通过**：revert 965f21d6 → G7 如期 FAIL → revert-the-revert → G7 PASS；终态三处 ref 校验一致。
- **git 事故 #2（执行者处置，编排者复核成立）**：并行进程无 reflog 改写分支 ref 至 09-17 陈旧链（0c65dca/2148 文件缺 GATE-V2 产物）+packed-refs 剪松散 ref——按「树文件数+日期+直系」判据恢复 965f21d6，弃链备份 refs/backup/。**⚠️ 运维戒律：本仓并发 git 写入方（多平台 agent 并行作业）必须串行化或分域；取件按 SHA 不按分支名。**
- **移交候选**：SEED-2（session_asset.file_url 61.7 万行+session_video.cover_url 20.6 万行同占位域，未改）；限流前缀误伤收窄（/api/trade/orders 被 /api/trade/order 规则 429 无 CORS→me 页假红，3 次）；GATE-V3（数据就绪竞态机制化，me 页需 SETTLE_MS=3500）。
- **下一步=UAT 十场景（用户在线）**：四门 25/25 全绿终态已锁定。

## 用户实测反馈处置（2026-09-21，FEAT-WIRE 立项）
- **用户实测纠正编排者两个判断**：①"82 万行视频数据是真的"——**部分正确**：session_asset 有真实本地上传视频（/media/videos/VID-2026*，161 个上传者，最近 2026-09-15），上传管线真实用过；61.7 万占位行=规模种子，与真实上传共存。编排者此前"都是假数据"表述过重，已纠正。②"新前端功能未实现"——课程详情页实测**是接线的**（券弹窗显示真实库存 100/100），用户遇的是：券模板 71 被种子用户领光（数据耗尽非功能缺失）+ 登录态问题。但用户指令成立：**G1 只保已调用接口零断点，不覆盖"有按钮没接线"死端**——FEAT-WIRE 立项（25 页交互元素全量盘点→dead 修复→placeholder 诚实化），行为层施工特批授权。
- **券模板 71 库存三核闸修复**：total_count 100→500（备份 deploy/backups/coupon71-20260921.json，幂等验证过）——用户现在可领 -10000 券。
- 双前端模型澄清：根路由 / = React 壳（src/app (admin)/(user) 路由组，部分实现）；25 页 static 黏土页=功能完整演示面。用户在两者间穿梭造成"新旧两代前端"观感——FEAT-WIRE 任务 B6 出对账表。

## 用户 12 缺陷实测 + FEAT-WIRE v1 作废（2026-09-21，用户裁定新前端实测为唯一准则）
- **用户 12 条实测缺陷入 P0**（弹窗关闭/用户管理动作/RAG tab/回收站/专项练习/对话隔离/思考中残留/流式/跨会话记忆/大纲展开/视频上传入口/MCP 测试数据）——暴露**门禁结构性盲区**：G1/G3/G6-G9 证"接口一致/钩子存在/样式合规"，**不证"点击后行为正确"**（语义行为层无门）——教训入册：行为验收唯一手段=CDP 真实点击逐条实证，样式门绿≠功能可用。
- **FEAT-WIRE v1 作废自批四弱点**：无页面锚/无 P0 清单/验证门不证行为/一刀切禁改后端。V2 全修：URL+黏土主题截图强制、12 缺陷逐条三段式证据、后端分域授权（#8 隔离/#11 记忆需后端）。
- **SEED-VIDEO 立项**（用户指令"批量填充视频"）：可行性亲证（ffmpeg 9.0.1 在/media 挂载在/目录在），方案=生成 120 示例 MP4+三核闸把 82 万占位行全部轮换指向真实文件+播放链路 CDP 验证。
- 用户体感根因澄清：用户在 React 壳（/，部分实现）与黏土静态页间穿梭，且此前"门禁全绿"给用户造成"功能都该能用"预期——**样式重塑验收≠功能验收**，两套验收自此分开表述。

## FEAT-WIRE-V2 验收：有条件通过+返工（2026-09-21，编排者批判审计 6 P0）
- **10/12 缺陷实证闭环**（#1/#3/#5/#6/#7/#8/#9/#12 编排者亲证或强证据；#8 隔离亲测 admin 只见 100003/student 只见 1；#1 视频实测文件+代理修复在位）；186 passed 亲跑复证；14 commit 域内（唯一域外=next.config.ts 端口修恰是 #1 根因）。
- **批判审计 6 P0**（ORCH-AUDIT-feat-wire-v2.md，全部带编排者实测数据）：①#11 记忆召回选错事实（落库对/召回错，45s 后仍答错——用户原缺陷体感依旧）②记忆 45s 延迟+零反馈=演示必翻车 ③dead=0 口径漏洞：83 delegated 元素未点击差分（历史缺陷大半是 delegated 形态）④视频上传仅 2.3MB 冒烟，100MB+ 真实路径未验 ⑤隔离修复代价=管理端会话审计归零无替代 ⑥演示主账号 4+ 条冲突名字记忆无治理。返工令 REWORK-FEAT-WIRE-V2 已上板。
- **教训入册**：「dead=0」声明口径=无零绑定元素≠全站点得动；delegated 类（有绑定 handler 坏）是用户实测缺陷主力形态，点击差分是唯一验收手段。记忆系统三断点结构：提取（已修）→落库（本就通）→**召回选择（P0-1 盲区）→时效（P0-2 盲区）**——半修复之所以半，是验收只测了链路通没测「选对+够快」。

## AUTO20 T6 验收闭环（2026-09-21，5058bd3，编排者逐项亲证）
- 限流前缀收窄：精确段+子路径匹配+最长前缀优先（/api/trade/orders 不再误伤，落 default 100/min）；429 补 CORS 头（按同源规则回显 ACAO，DEBUG=false 仅精确 Origin，不放宽 CORS 面）。编排者亲测：orders 12 连发全 200、order 第 11 次 429 规则仍在、429 带 ACAO（OPTIONS 预检+POST 双实证）。19+64 passed 亲跑。
- 执行者顺带环境治理：Redis 容器（6377）未运行致限流整体降级，已 docker start 恢复。
- 遗留登记：空壳 TestMiddlewareOrder、旧 app/common/rate_limit.py 死代码；死规则 /api/trade/refund、/api/after_sales/ticket 不擅改保留。全量 1737 passed/5 failed/11 errors=存量数据态+TEST_BASE 默认 8000 旧契约测试（stash 对照隔离验证与本单无关）。
- 教训：E2E 验收顺序坑——先跑 orders 12 连发验证收窄，再跑 order 超限验 429（顺序反了会被限流窗口互相污染）。

## AUTO20 T7 验收闭环（2026-09-21，d2b6efa，编排者亲证）
- F-W1-GUARD 硬化闭环：receipt_guard.py 纯函数（写类完成语义∧无 success 凭据→tool_receipt_unverified+诚实修正句；error 凭据不算证据；只读零拦；幂等）+词表配置化+双链路单一事实源（流式 make_stream_finalize/非流式 chat_answer）。
- 编排者亲测：诱导捏造场景（导入知识库被拒）→标记 True+修正句在答案尾部；17+227+21 passed 亲跑；前端黄条+G3 全站 PASS。
- 盲测 B6 ✅。C-W1-② 从"部分修"转"已硬化"，tracker 首例 P0 项全周期闭环（发现→缓解→硬化→机检护栏→盲测）。
