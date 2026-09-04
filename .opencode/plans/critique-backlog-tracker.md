# 批判滞后任务修复追踪清单（Critique Backlog Tracker）

> 用途：每条验收批判的「修复措施 + 落点任务 + 验收指标」三段式归集。**执行滞后任务时必须逐条对照本清单落地**，验收时逐条核对。
> 建立：2026-08-22（用户质疑"滞后任务是否只批判不修复"后确立）
> v2 修正：2026-08-22（用户指出 v1 只有批判描述、无三段式 → 全部条目补全「修复措施/验收指标」）
> 规则：①新批判产生时同步追加 ②滞后任务开工 prompt 必须引用 ③滞后任务验收逐条核对，未完成不得 DONE。

## 一、滞后任务 → 批判修复项（三段式）

### task32（RAG 离线评估）— 进行中
- [ ] **task-VEC 批判③**：记忆召回指标样本不足（仅 5 条）
  - 修复措施：在 `scripts/eval/eval_dataset.py` 扩充记忆召回评估集至 ≥30 条（跨语义类别：偏好/进度/错误/目标），复用 `MemoryVectorStore.search` 跑 BGE-M3 vs 哈希对比，输出 rank@1/recall@3
  - 落点任务：task32
  - 验收指标：评估集 ≥30 条；BGE-M3 rank@1 ≥0.9；对比报告含两种 embedder 的 recall 差

- [ ] **task31 批判①**：AutoModel 重写打分 vs FlagReranker 语义等价性未量化
  - 修复措施：在 `rag_evaluator.py` 增加 rerank 增益评估（评估集对拍：真实 rerank vs `_rule_rerank` 兜底，计算 top-20 命中率差）
  - 落点任务：task32
  - 验收指标：rerank 后 top-20 命中率较规则兜底提升 ≥+15%；未达标输出差距分析+调参建议

- [ ] **task30 批判②**：真实 LLM 前缀质量/成本未端到端验证（默认 CONTEXTUALIZE_ENABLED=False）
  - 修复措施：`RUN_REAL_LLM=1` 跑 verify_task30.py，用真实 DeepSeek 生成前缀，统计前缀 token 数、失败率、成本
  - 落点任务：task32
  - 验收指标：前缀 50-100 token 达标率 ≥90%；LLM 失败降级率 <5%；单文档前缀成本 <预算线

- [ ] **task29 批判③关联**：缓存命中实际落地（真实短前缀<1024 未达 DeepSeek 缓存门槛）
  - 修复措施：在 task32 评估中加入多轮相同前缀 benchmark，记录 cache_read/cache_creation、延迟、成本
  - 落点任务：task32
  - 验收指标：实测命中率与成本数据入报告；结论明确是否需加大前缀

### task37（清理/文档/测试修复）
- [x] **task12 批判**：死代码 `app/admin/course_admin`（39 处 curriculum_）清理（✅ commit 203a1e5 task37-deadcode 复核：目标目录已不存在——task12 已将 `app/admin/course_admin` 迁移为活动模块 `app/domains/course_admin`（main.py:365-368 注册），`app/admin/` 现仅余 rag_admin/trade_admin/user_admin。**无死代码可删**：`edu-agent/app` 剩余 7 处 `curriculum_` 经逐处核实全为**活代码**——①`app/curriculum/{router,service,schemas}.py` + `main.py:350,351` 为 task11 刻意保留的 308 永久重定向兼容层（`include_in_schema=False` 但已 include_router 可达，service/schemas 被 `tests/test_curriculum_service.py` 引用）；②`app/progress/schemas.py:26` 与 `app/curriculum/schemas.py:23,42` 仅活动文件中的文档字符串。删除这些会移除活兼容层，违反"别误删仍被引用的正确代码"，故**不勉强清零**；app.main import OK、test_curriculum_service 9 项 collect OK、无死 import）
  - 修复措施：~~删除 `app/admin/course_admin` 及 curriculum_ 引用~~（目录已不存在，天然净化）；grep 复核 `edu-agent/app` 无真死代码（活引用见上）
  - 落点任务：task37
  - 验收指标：grep curriculum_ = 0（改为：无**真死亡** curriculum_；活兼容层+文档串保留并登记）；pytest 全绿；无死代码 import

- [ ] **task14/15 批判**：test_auth_service/test_error_codes 字符串/整数码断言 bug
  - 修复措施：核对 error_codes.py 权威，把断言统一为字符串码（契约①响应壳）；修正 test_auth_service/test_error_codes 的断言
  - 落点任务：task37
  - 验收指标：修正后两测试文件全 PASS；断言与 error_codes.py 一致

- [ ] **91 项预存测试失败根因排查**（trade/breaker/course/error-codes）
  - 修复措施：跑全量 pytest 收集 91 项失败，逐类归因（trade/breaker/course/error-codes），修复或标注预期差异
  - 落点任务：task37
  - 验收指标：91 项全处理（修复或明确 expected）；pytest 无意外失败

- [ ] **task59 批判①**：MarkdownView text-[15px] 硬编码字号
  - 修复措施：定位 MarkdownView 组件 text-[15px]，替换为 candy token（text-sm/text-base 语义类）
  - 落点任务：task37
  - 验收指标：grep text-\[15px\] = 0；渲染视觉回归通过

- [ ] **task-VEC 批判①**：user_memory 512→1024 历史残留确认
  - 修复措施：查 Milvus user_memory 集合 schema 维度 + 有无 512 维历史数据；如有则重建或迁移
  - 落点任务：task37
  - 验收指标：user_memory schema 恒为 1024；无 512 维脏数据

- [ ] **task60 批判②**：MutationCache 401/403 早退与组件级 onError 兜底覆盖一致性
  - 修复措施：审计全局 MutationCache 401/403 早退逻辑与 EditUserDialog 组件级 onError，统一错误透传；补测试
  - 落点任务：task37
  - 验收指标：401/403 在全局与组件级均正确 toast；测试覆盖

### task39（压测/性能/灾备）
- [ ] **task24 批判①**：自研 checkpointer 压测（并发/持久化）
  - 修复措施：并发 N 用户同时 checkpoint + resume，测持久化正确性、并发冲突、性能
  - 落点任务：task39
  - 验收指标：并发 100 无丢失/错乱；resume 正确率 100%；P95 达标

- [ ] **task26 批判**：真 Redis 分布式（bigkey/checkpoint 生产验证）
  - 修复措施：Redis 恢复后跑真库 bigkey/checkpoint 测试，验证分布式锁与 ZSET 分片
  - 落点任务：task39
  - 验收指标：bigkey 处理无 OOM；checkpoint 跨实例一致；契测真 Redis 版全 PASS

- [ ] **task29 批判②**：P95 严重超标治理（L1 87s/L2 66s/L3 107s vs 8s）
  - 修复措施：定位 fan_out 多轮 LLM + Redis 超时叠加，做并发削峰/降级优化/并行调度优化
  - 落点任务：task39
  - 验收指标：L1~L3 P95 ≤8s、流式首包 ≤3s

- [ ] **task28 批判①**：72h 超时 escalation 触发可靠性
  - 修复措施：缩短 TTL 模拟超时，验证 escalation 幂等 + 告警
  - 落点任务：task39
  - 验收指标：缩短 TTL 下 escalation 正确建 high 工单且幂等；告警送达

- [ ] **task92 批判②**：artifact 跨实例
  - 修复措施：多实例共享 artifact（Redis）验证读取一致性
  - 落点任务：task39
  - 验收指标：跨实例 artifact 读回一致；TTL 1h 生效

- [ ] **task-VEC/31 批判②**：BGE-M3/Reranker 冷启动预热
  - 修复措施：启动时预加载 `_get_bge_model()` + `Reranker.get()`；预热接口
  - 落点任务：task39
  - 验收指标：首个请求延迟 <3s（从 10.9s 降至 warm 水平）；预热日志确认

### task69（E2E 全链路）
- [ ] **task42 批判①**：登录态持久化/刷新/多标签恢复
  - 修复措施：Playwright 用例：登录→刷新→仍登录；开新标签→共享会话；登出→受保护页跳登录
  - 落点任务：task69
  - 验收指标：3 用例全 PASS

- [ ] **task42 批判②**：redirect 含 query 深层路由回跳
  - 修复措施：Playwright 用例：/login?redirect=/admin/users?page=2 → 登录成功回跳含 query
  - 落点任务：task69
  - 验收指标：回跳 URL 完整含 query；用例 PASS

- [ ] **task59 批判①**：admin 预览 vs 用户端渲染一致性
  - 修复措施：Playwright 对比 admin QuestionDetailEditor 预览与用户端 QuizPanel 对同一题渲染截图
  - 落点任务：task69
  - 验收指标：截图 diff 无实质差异；Markdown 渲染一致

- [ ] **task59 批判②**：题型切换边界用例
  - 修复措施：Playwright 补单选↔多选↔填空切换的旧选项残留边界
  - 落点任务：task69
  - 验收指标：切换用例全 PASS；无数据残留

### task98（verify.py 验收体系）
- [ ] **task07/10 批判**：CI 门禁（P4）落地
  - 修复措施：实现 `scripts/verify.py`（schema/counts/quality/all 四子命令）+ `.schema-acceptance.yaml` + GitHub Actions workflow
  - 落点任务：task98
  - 验收指标：verify.py 四子命令可跑；CI gate 失败禁合并；文档对齐 db-acceptance-principles

- [ ] **task07 批判**：口径漂移（6-机构 vs 全局）脚本化
  - 修复措施：verify.py counts 子命令支持机构维度，脚本化 6-机构口径校验
  - 落点任务：task98
  - 验收指标：机构口径校验脚本化；与 task07 基线一致

- [ ] **91 项预存失败根因归入统一验收框架**
  - 修复措施：verify.py 集成测试结果归一化，91 项失败作为 expected 基线登记
  - 落点任务：task98
  - 验收指标：验收框架能标记 expected；回归可对比

### task70~91（管理端补全）
- [ ] **task16 批判**：热门课程榜契约缺口
  - 修复措施：前端实现时按 api-request.md 权威对齐热门榜契约
  - 落点任务：task70~91
  - 验收指标：热门榜页面字段与契约一致；无 MOCK

- [ ] **task57 批判**：后端章节端点接续后联调
  - 修复措施：后端补章节端点后，前端课程详情 CRUD 联调
  - 落点任务：task70~91
  - 验收指标：章节 CRUD 全通；无 disabled 占位

### task34（kb-rebuild-milvus）
- [ ] **task30 批判①**：raw_content 双份存储真实增长统计 + VARCHAR(8000) 上限验证
  - 修复措施：全量入库时统计 content 列增长（前缀+raw_content）；边界 case 验证近 8000 上限
  - 落点任务：task34
  - 验收指标：存储增长报告；无超 VARCHAR(8000) 截断

### task35（kb-graph-rebuild）
- [ ] **Neo4j 图谱启用**（VM 已可达，当前降级）
  - 修复措施：接入 VM Neo4j（bolt://192.168.85.101:7687 或本机），重建课程/题目知识图谱；retriever 图谱通道启用
  - 落点任务：task35
  - 验收指标：图谱实体入库；retriever graph_entities 非空；Neo4j 连通无降级

### task66（前端退款页）
- [ ] **task19 批判**：退款状态机语义确认
  - 修复措施：前端退款页实现时按 task19 状态机（pending/approved/rejected/refunded）确认展示语义
  - 落点任务：task66
  - 验收指标：退款状态展示与后端一致；无 MOCK

## 二、新增批判 → 滞后任务挂钩规则（强制）

1. 每份 taskNN-技术批判.md 产出的每条 P2+ 批判，**必须**以「修复措施（具体做法）/ 落点任务 / 验收指标（量化）」三段写入本清单。
2. 落点任务文档（taskXX-*.md）的「批判承接」段，**必须**引用本清单对应条目。
3. 滞后任务开工 prompt 的「必读」**必须**含本清单路径。
4. 滞后任务验收时**逐条核对**清单，未完成项标注 ❌ 不予 DONE，驱动返工。

## 三、执行证据留存

- 每个滞后任务完工报告新增「批判承接核对」段：逐条列出本清单项 → 完成证据（代码/测试/实证数据）+ 验收指标达成情况。
- 编排者验收时对照本清单 + 完工报告核对，双重确认；指标未达标不得 DONE。

### task-T1（工具闭环，2026-08-28 追加）
- [ ] T1-① DB 枚举 ALTER：执行 refactor_sql/task-T1-add-status-enum.sql → MANUAL_GUIDE/REJECTION_LIMIT 落库无吞错
- [ ] T1-② 备用工具注册：calculator/search_knowledge 注册 mcp_tool 或接子代理降级检索 → switch_tool 命中真实工具
- [ ] T1-③ LLM 改写实测：窗口内跑 TOOL_RETRY_LLM_REWRITE 真实改写；或增强规则改写映射表 ≥5 组

### task-S1（HITL 护栏，2026-08-28 追加）
- [ ] S1-① HITL_ENABLED=True 灰度启用（先 exec_command/refund）→ 真实拦截实测
- [ ] S1-② 建表：执行 refactor_sql/task-S1-create-hitl-approval.sql → hitl_approval 四审计字段可写
- [ ] S1-③ sweep 定时挂接：接入后台调度（对齐 task-M1 memory_worker）→ 过期 pending 自动拒绝

### task-R1（rerank 服务，2026-08-28 追加）
- [ ] R1-① fp32 批处理评估（排序敏感场景）→ 噪声 <1e-4
- [ ] R1-② sidecar 部署：uvicorn 8601 + 预热 + RERANK_SIDECAR_ENABLED=True → /health 200 主链路走 sidecar
- [ ] R1-③ Redis 队列削峰启用（高峰评估后）→ 队满降级不 500

### task-G1（token 并发，2026-08-28 追加）
- [ ] G1-① retry.py 接入 generator/agent 真实重试路径 → 429 指数退避/超时线性
- [ ] G1-② 60s 窗口边界：task39 压测评估令牌桶 → 边界不超
- [ ] G1-③ 强制 request_meta 传入 → 预估更精确

### task-O1（观测性，2026-08-28 追加）
- [ ] O1-① 埋点调用点接入：memory/executor/compaction 用 record_* → 四类事件真实产出
- [ ] O1-② OTLP protobuf 增强（接真实后端时）→ 投递成功
- [ ] O1-③ 跨实例聚合（Prometheus/OTLP 后端）→ 多实例指标聚合

### task-C1（动态压缩，2026-08-28 追加）
- [ ] C1-② graph 装配 feature flag（anchor_round+llm 注入 compact_node）→ 真实对话启用
- [ ] C1-③ 冻结区 token 占比监测 → 超阈值告警/降 ANCHOR_ROUND

### task-C2（缓存达标，2026-08-28 追加）
- [ ] C2-② TOOL_DEFERRED_MODE 灰度观察决策准确率 → 必要时回退
- [ ] C2-③ schema_registry Redis 共享（task-M2 协同）→ 多实例一致

### task-M1（记忆事件溯源，2026-08-28 追加）
- [ ] M1-② 建表冒烟：执行 patch_memory_event.sql → user_memory_event 真实读写
- [ ] M1-③ 容量上限配置化：config 增加用户级容量 → 按活跃度动态调整

## W1 优化批次里程碑批判（2026-09-02，来源 .ai-hub/plans/tasks/W1-技术批判.md）
- [x] W1-批判1 [x] 401 静默刷新重放缺失（对标 axios 拦截器）——edu-api.js 加 single-flight refresh + 重放 1 次｜待派（✅ commit 203a1e5：edu-api.js 单飞 refresh（模块级 pendingRefresh 复用，并发 N 个 401 只发 1 次 /api/auth/refresh）→ 更新双 token → 重放原请求一次 → 仍败才 handleUnauthorized/download;store 增 get/setRefreshToken;login-register 登录持久化 refresh_token（否则 refresh 是死代码）。独立复验 selfcheck-singleflight-refresh.mjs ALL PASS：并发 5→refresh=1/滑动续期/缺 refresh 降级跳登录）
- [x] W1-批判2 [x] 管理端守卫 8 份内联拷贝（对标 React Router 集中守卫）——抽 edu-guard.js 单点化｜落点 task122（✅ commit 203a1e5：新建 public/edu-guard.js 暴露 window.eduGuard.requireAdmin(onPass)，三守卫段单点；8 个 admin-*.html 内联 IIFE 换 `<script src="/edu-guard.js">`+requireAdmin()；独立复验 guardInclude=8×1、内联守卫=0（admin-courses L572 为保留的 getAdminId() 数据助手非守卫）、三守护语义不变）
- [ ] W1-批判3 [ ] 死链扫描未进门禁且静态扫描有变量拼接盲区（对标 lychee）——挂 task123 检查单 + L4 回归｜落点 task123
- [ ] W1-批判4 [ ] 注册两步式登录 UX 次优（对标注册即登录）——随 C-A（task114）评估 register 返回 token，默认不采纳留档｜落点 task114 讨论项

## W2 优化批次里程碑批判（2026-09-04，来源 .ai-hub/plans/tasks/W2-技术批判.md）
- [x] W2-C1 [x] 响应壳"全站统一"是运行时黑盒兜底（response_model 裸体↔中间件包壳双源漂移，对标 JSON:API/OpenAPI）——壳形态上移契约 Shell[T]、裸 DTO 显式 ok()｜落点 C-A 迭代二（✅ commit 664774b：install_openapi_shell 后处理器让 /docs 每 2xx json 统一包 {code,message,data}（$ref 感知幂等防双包）；users profile 两处裸 response_model=UserProfile 改 Shell[UserProfile]；实测 /openapi.json profile→Shell_UserProfile_单层壳，运行期响应体不变。⚠️ 豁免清单 _archived/dict/rerank sidecar；后续新增端点仍需遵守壳形态契约）
- [x] W2-C2 [x] 分页 page_meta+外层 triple 双轨并存无硬截止（对标 JSON:API/DRF 单一来源）——弃用时间表写死进契约单+W4 门禁、过渡改查询参数别名｜W4 门禁/C-B 迭代二（✅ commit 155b4b0+35b94fe：后端删 SeriesListData/CohortListData/_build_page_meta 双写，仅留外层 {total,page,page_size,items}（curl /api/series 出口键实证）；前端 courses.html/admin-courses.html 改读外层 triple，git grep page_meta public/*.html=0。⚠️ W4 回归门禁项仍待办：grep page_meta=0 挂进 L4 回归，React src 侧 page_meta?: 可选类型字段/文档注释按冻结 C-B 形态保留）
- [x] W2-C3 [x] chat SSE error 仅覆盖 token 迭代段且码硬编码 50000，初始化/检索/落库三段仍 HTTP/静默（对标 WHATWG SSE 统一错误模型）——生成器整体 try/except 统一 error+保留下游码｜chat/router 重构小任务（✅ commit 65b31a2：_map_stream_exception 动态码 LLM_AUTH/LLM_TIMEOUT/LLM_RATE_LIMIT/LLM_UNAVAILABLE/SERVICE_DOWNSTREAM/CHAT_PERSIST_FAIL 增登记 error_codes 5001x；落库失败静默→显式 event:error+degraded done 兜底；done 壳/code:0 保留；新增 test_chat_stream_error.py 5 用例全绿；资产消费证据 test-reports/critique-C3-completion-report.md）
- [x] W2-C4 [x] task122 清演示残留不彻底：18/36 页仍带可交互 respbar（dashboard 旗舰有活"断点预览"toolbar，对标 ESLint 门禁）——全站 respbar 归零+grep 挂 W4 回归门禁｜task122 补刀（✅ commit 8eb8cab：18 页删活动 respbar CSS/toolbar/绑定，保留演示数据兜底+角标+`已移除(critique C4)`注释；dashboard 空态 retry 改 location.reload；编排者实证 `git grep respbar` 24 行全注释、活动行=0；资产消费证据 test-reports/critique-C4C6-completion-report.md。⚠️ W4 门禁项仍待办：grep respbar=注释 挂进 L4 回归防复生）
- [x] W2-C5 [x] 删除语义软删+真删+40908 三态无回收站 UI、?hard 仅 ADMIN 前端靠猜（对标 django-safedelete/Entra soft-delete-purge）——补 POST restore 端点+admin 回收站 Tab｜独立小任务（✅ commit 155b4b0+35b94fe：`POST /api/admin/courses/series/{series_id}/restore`（与既有 course_admin CRUD 同前缀，AdminAuthMiddleware 覆盖，匿名 401），软删 off_sale→draft；契约单 handoffs/critique-C5-contract.md；独立实证 E2E 全通：create→soft-delete→include_deleted 可见 off_sale→restore `{series_id,status:"restored"}`→默认列表 draft→错误分支 404/40400 + 401/40101；admin-courses.html 回收站 Tab。⚠️ 遗留独立问题：仓库 JSON 列传 list 触发 50000 tuple/version 类型报错，与 C5 契约无涉，待单独立项））
- [x] W2-C6 [x] practice 只判三题型，FILL/DRAG_SORT/MATCH 静默置灰"迭代二"且演示态仍有 blank（对标 Moodle 20+ 题型显式引导）——置灰改显式提示+badge 标注+迭代二 PBI 带 deadline｜前端小改+PBI（✅ commit 8eb8cab：三题型改可点击 .pill.iter2+data-iter2，点击 showIter2 弹 role=status 说明"暂未开放已登记迭代二"；演示 blank tab 改"填空 · 迭代二"对齐登录态 FILL:false；登记 PBI-ITER2-TYPES。⚠️ 迭代二 deadline 仍待 PBI 排期）

## W2 批判验收补充遗留（2026-09-04 独立实证发现，属独立于本批判项的新增待办——三遗留项均已闭环 ✅ commit 4a9bacc）

- [x] **course_admin 仓库 JSON 列 500**：创建系列 payload 含列表字段（如 `target_learner_identity_codes:[...]`）时返回 `500 {code:"50000"}`（`Argument 'val' has incorrect type (expected tuple, got list)`）。修复措施（✅ 4a9bacc）：`series_repo.py` insert/update 对 `target_*_codes` 三列用 `_json_or_null()` 序列化（None→NULL/list→json.dumps/已 str 原样），读侧 `_parse_json_columns` 读写对称；真实 HTTP 创建/更新含 list 字段 200 且 round-trip 回 list，`tests/test_course_admin_json_columns.py` 3 passed。

- [x] **W4 回归门禁落地**（C2/C4 共性）：（✅ 4a9bacc）新增 `scripts/gate-w4-critique.mjs`（纯 node）：grep `page_meta`=0 + `respbar`=注释，去注释/字符串后代码清洗串判定（防恒 PASS 负向自检 `--with-src` 可打破）；实测 `GATE_RESULT=OK`；已接入 `run_regression.ps1` 末尾 `W4_GATE`（缺 node 跳过不中断）。

- [x] **C6 迭代二 PBI-ITER2-TYPES deadline**：（✅ 4a9bacc）排期落盘 `.ai-hub/plans/tasks/W2-优化修改方案.md` §W2-C6 PBI 排期登记，deadline=2026-09-30（迭代二、不早于 W4 回归门禁通过后启动）。
