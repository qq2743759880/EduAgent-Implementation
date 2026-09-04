# EduAgent 平台重构 — 任务划分计划（dev-plan）v3.0

> **数据权威**：`E:\stu\project\stu\edu-data\sql\edu.sql`（66 表）｜**总纲**：`.opencode/plans/edu-data-refactor-plan.md` v2.0
> **前端规范**：`.opencode/plans/doc-frontend-design-spec.md`｜**后端架构**：`.opencode/plans/doc-architect-tech-arch.md`
> **任务总数**：task00 ~ task91 共 92 个（后端 47 + 前端 45）｜**文档版本**：v3.0｜**状态**：待评审

## 版本变更记录

| 版本 | 日期 | 变更点 |
|------|------|--------|
| v1.0 | 2026-08-16 | 初版：59 任务（P0~P9），前端 18 页 + 适配页组 |
| v2.0 | 2026-08-16 | 补全 task36~58 详述、依赖图、检查点、风险清单 |
| **v3.0** | 2026-08-16 | **① 前端范围扩大为"全部页面重建"**：27 个页面任务（每页一任务，不再打包"适配页组"；/ 根路由并入 task42、login/register 合并、RAG 上传入口并入 task61 admin/rag）→ 前端任务 30 个；**② 全部技术选型注明参考来源**：引用 `tech-source-audit.md`；**③ 新增前后端联调编排**：契约冻结①~⑭对齐 `orchestration-frontend-backend.md`；**④ 新增开发者对接守则引用**：`collaboration-protocol.md`；**⑤ 每任务生成详细文档**：`tasks/taskNN-*.md`（agent 调度链/workflow 参数/联调节点/选型依据），`task-agent-matrix.md` 按新编号重排（见本文件附录） |
| v3.1 | 2026-08-16 | 管理端补全 P0+P1：新增 task70~91（订单/退款/学员/工单/公告/报表/券/CRM，对标云朵课堂实爬） |
| **v3.2** | 2026-08-16 | **AI 8 项修订（self-critique 落地）**：新增 task92~97（子代理独立上下文/skill runtime/MCP tool search/context editing/缓存监控）；修订 task24~33（R1~R8）；**知识库重建前移至 AI 之前**；新增 §执行顺序 优化说明 |
| **v3.3** | 2026-08-17 | **新增 6 点数据库验收原则**（db-acceptance-principles.md：先文档后脚本/精确断言/动态计算/CI门禁/5维度质量/口径漂移声明）+ 新增 task98（生产可复用验收体系 verify.py 框架）→ 99 任务 |
| **v3.4** | 2026-08-17 | **新增 task99**（批量 auth 补生成：100K 用户登录可用，来源 task08 批判②）→ 100 任务 |

## 选型审计引用（v3.0 新增）

> **规则**：凡涉及技术选型的任务，必须引用 `E:\stu\project\stu\EduAgent实施手册\.opencode\plans\tech-source-audit.md` 对应条目作为依据；实施中不得偏离审计结论（偏离需先更新审计文件）。

| 审计章节 | 覆盖选型 | 主要消费任务 |
|---------|---------|-------------|
| §一 后端基础栈 | Python 3.11+FastAPI / 模块化单体 / asyncmy+repository / 响应壳 | task09~23 |
| §二 AI 助手架构 | LangGraph 1.2 / orchestrator-worker / 三层记忆+遗忘 / compaction / artifact / effort scaling / LLM-as-judge / HITL | task24~29 |
| §三 RAG/MCP | Contextual Retrieval / bge-reranker-v2-m3 / Milvus / MCP 描述审查 | task30~33 |
| §四 数据/中间件 | Redis 多角色 / 缓存三防 / Polaris 熔断 / 幂等三层纵深 / 读写分离 | task09/10/23 |
| §五 前端技术栈 | Next.js 16.3+React 19+Tailwind v4+shadcn / TanStack Query 5+zustand / echarts | task40~69 |
| §六 前端设计 | indigo #4F46E5 / 单主色红线 / 状态色 / HTML 原型审核流 / 断点 375~1440 | task40~69 |
| §七 数据重灌/运维 | full 档分夜跑批断点续跑 / NetworkManager 隔离 | task00/06/07/39 |

## 协作机制引用（v3.0 新增）

| 文档 | 作用 | 消费方 |
|------|------|--------|
| `orchestration-frontend-backend.md` | 前后端联调编排：执行工具分工（Trae=后端/TraeWork=前端/opencode=编排者）、任务排序、跨工具交接单机制、并行窗口 | 全体（依赖图 §3 与之一致） |
| `collaboration-protocol.md` | 工作对接守则：可写范围边界、契约纪律、AI-Hub 记忆分区（trae-projects/codex/project-handoff）、冲突上浮、开工检查单 | 全体 |
| `task-agent-matrix.md` | 任务×agent/skill/workflow/MCP 调度矩阵（本文件附录已按新编号重排） | 全体 |
| `tech-source-audit.md` | 选型来源审计 | 全体 |

**执行工具分工**：Trae = 后端/数据库/AI/RAG/MCP/运维（task00~39 中除编排项）；TraeWork = 前端（task40~69）；opencode = 编排/契约冻结发布/验收仲裁。

## 执行顺序（v3.2 优化后）

> 依据：self-critique（知识库依赖前移/AI 修订设计先行/前端滚动解锁）。
> 完整依赖图见 §3。此处给出流水线级执行顺序。

```
A 数据主线   task00→08（Trae 串行，先决）
B 后端底座   task09→15（Trae）→ 契约①~⑤ 逐批解锁前端
C 交易/学习  task16→23（Trae）→ 契约⑥~⑭
D 知识库重建 task30→34→31→32（Trae，依赖 task07；前移至 AI 之前，保证 agent 有检索数据）
E AI 修订+实现 task92→24 → 93/94→27 → 95→33 → 96→26 → 97 → 25/30 改造 → 29（修订设计先于实现）
F 管理端补全 task70→77b（Trae，依赖 C；与 E 并行）
G 前端       task36→37 → 按契约滚动解锁（TraeWork；与 B/C/F 并行）
H 收尾       task55→58
I 验收基座   task98（生产可复用 verify.py，紧随 task07 修复，后续所有数据库迭代复用）
```

**前端解锁节奏**：契约①后 task36/37；契约②~⑤ 后 task42~53；契约⑥~⑭ 后 task78~91。TraeWork 每批契约释放即开工，不干等。

## 0. 全局执行原则（所有任务共同遵守）

1. 字段/表结构一律 edu.sql 为准；前端字段统一 snake_case，删除全部别名兜底与 MOCK fallback
2. 响应壳统一 `{code:0, message:"ok", data}` 成功 / `{code:<字符串错误码>, message, data:null}` 失败（SSE 事件流除外）
3. 写操作失败必须上抛（R-7 红线沿用）；管理端 RBAC 仅 admin
4. **每个前端页面必须走 HTML 原型审核流**（§2.11.0 通用循环），APPROVED 后才写 React
5. 事务只包 MySQL 行操作；LLM/Redis/Milvus/MinIO/Neo4j 一律事务外；事务内禁嵌套独立连接
6. 所有降级点写 `degraded_reason`；所有外部依赖（Milvus/Neo4j/Mongo/Redis/MinIO/LLM/MCP）挂熔断器
7. 契约纪律（collaboration-protocol.md §二）：契约唯一权威 = 后端 Pydantic schemas.py；冻结后字段变更走契约变更单；前端不自行造接口；越界上浮
8. 工作量档位：S（≤0.5 天）/ M（0.5~1 天）/ L（1~2 天）/ XL（2~4 天）

---

## 1. 任务总览表

| 编号 | 标题 | 类型 | 工具 | 前置依赖 | 联调节点 | 并行组 | 工作量 | 验收摘要 |
|------|------|------|------|----------|---------|--------|--------|----------|
| task00 | P0 全量备份与快照（mysqldump + Milvus/Neo4j） | ops | Trae | — | — | W1 | M | 备份文件生成 + 恢复演练通过 |
| task01 | 66 表 DDL 重建脚本（动作 A/D，按 edu.sql） | database | Trae | —（与 task00 并行） | — | W1 | XL | 66 表结构 diff 为空、27 表保留不受影响 |
| task02 | 13 张平行旧表删除 + 代码引用清理（动作 C） | database | Trae | task01 | — | W1 | M | 全库代码零引用 + 删除确认报告 |
| task03 | sys_user 改造 + 外键语义恢复 + 查询索引（动作 B/E） | database | Trae | task01 | — | W1 | M | 登录可用、外键生效、EXPLAIN 走索引 |
| task04 | knowledge_import_task 新表 + 通用 task 任务表（动作 F） | database | Trae | task01 | — | W1 | S | 建表成功、与 RAG 管道双写可用 |
| task05 | 库表结构 diff 校验脚本 + CI 集成 | test | Trae | task01~03 | — | W1 | M | 校验脚本可重复执行、CI 全绿 |
| task06 | full 档生成脚本适配（layers 1..7、断点续跑） | ops | Trae | task01~04 | — | W1 | L | 分夜跑批可续跑、batch_size=5000、幂等 |
| task07 | full 档执行 + 计数校验（219/657/73/1752/10万/8万） | ops | Trae | task06 | 「数据基线冻结」 | W1 | XL | 六项计数全部达标 + 校验报告 |
| task08 | admin 账号恢复 + 全链路冒烟 | ops | Trae | task07 | — | W1 | M | admin 登录 + 冒烟链路全通 |
| task09 | core/ 框架层（resp/cache/lock/idempotency/breaker/trace/queue） | backend | Trae | —（与 P1/P2 并行） | — | W2 | XL | 各组件单测通过（含熔断三态/缓存三防） |
| task10 | middleware/ 目录 + 响应壳全模块统一 + 错误码分段 | backend | Trae | task09 | **契约冻结①→前端 task40** | W2 | XL | 契约测试遍历全部 router 100% 统一壳 |
| task11 | 课程域改造：curriculum→series（C 端 5 端点 + 重定向 + repository） | backend | Trae | task10, task03, task07 | **契约冻结②→前端 task44/45/46** | W2 | XL | /api/series 全筛选可用、旧路由重定向 |
| task12 | course_admin 重写（四级 CRUD + 视频三表 + 分片上传） | backend | Trae | task11 | **契约冻结③→前端 task56/57** | W2 | XL | 系列→班次→模块→课次→视频全链路 CRUD |
| task13 | question 域：question_admin 重写 + quiz 出题源改造 + 批量导入 | backend | Trae | task10, task07 | **契约冻结④→前端 task58/59/49** | W2 | L | 1752 题导入、quiz 出题源切换、analysis_text 贯通 |
| task14 | progress/mindmap/recommender 改造 + users bug 修复 + /me 新接口 | backend | Trae | task11, task13 | **契约冻结⑤→前端 task54/43/60** | W2 | L | UPDATE 写 sys_user、student-profile/learning-summary 可用 |
| task15 | 存量模块响应壳适配（auth/chat/community/gamification/mcp/rag_admin） | backend | Trae | task10 | **契约冻结⑬→前端 task42/50~53/55/60/62** | W2 | M | 契约测试全绿、gamification 排行走 ZSET |
| task16 | market 域新建（coupons 3 端点 + favorites 3 端点） | backend | Trae | task10 | **契约冻结⑦→前端 task63/67** | W2 | L | 领券防超发、收藏 CRUD、幂等唯一键 |
| task17 | trade/order 域新建（5 端点 + 状态机 + 三层幂等纵深） | backend | Trae | task16 | **契约冻结⑧→前端 task64** | W2 | L | 下单单事务、金额服务端重算、取消状态机 |
| task18 | trade/payment 域新建（8 端点 + mock 回调 + 报名联动） | backend | Trae | task17 | **契约冻结⑨→前端 task65** | W2 | XL | 回调幂等、支付→订单→报名→核销单事务 |
| task19 | trade/refund 域新建（退款申请/撤销 + HITL 预留） | backend | Trae | task18 | **契约冻结⑩→前端 task66** | W2 | M | 退款状态机、金额≤已付校验、refund_no 幂等 |
| task20 | enrollment 域新建（/me/cohorts 4 端点 + 满班并发控制） | backend | Trae | task18, task11 | **契约冻结⑪（与 task21）→前端 task47/48** | W2 | M | enroll_status 过滤、条件更新防超员 |
| task21 | study 域新建（10 端点 + progress 提交表改造） | backend | Trae | task20 | **契约冻结⑪（与 task20）→前端 task47/48** | W2 | L | 15s 打点写 edu-data 表、作业/考试外键语义 |
| task22 | tickets 域新建（5 端点 + appeal 人工申诉类型） | backend | Trae | task17, task20 | **契约冻结⑫→前端 task68** | W2 | M | 工单全流程 + appeal 类型可用 + user 隔离 |
| task23 | Redis 缓存落地（三防 + 热点 + 排行 ZSET）+ 慢查询索引治理 | backend+infra | Trae | task09, task11, task13 | **契约冻结⑭→前端 task43/48 性能验收** | W2 | L | 命中后 P95 下降、写后 DEL、慢查询无 >500ms 热点 |
| task24 | AI 助手：LangGraph 图重构（route→plan→fan-out→merge→reflect→answer）+ Redis checkpointer + effort scaling | agent | Trae | task09, task10, task23 | —（chat 页不依赖新契约） | W3 | XL | 四类意图路由、L0 直答、checkpoint 恢复、无硬编码 user_id |
| task25 | AI 助手：三层记忆 + 遗忘机制（user_memory 表 + Milvus collection） | agent | Trae | task24 | — | W3 | XL | 会话结束异步写、召回 top-3 进 plan、500 条淘汰 |
| task26 | AI 助手：compaction + artifact 轻引用 + Redis 防过载（队列削峰/会话并发/大 key 治理） | agent+infra | Trae | task24 | — | W3 | L | >6k token 触发压缩、压缩后 ≤6k、并发 ≤2、排队 10s 提示 |
| task27 | AI 助手：tool_specs 规范 + CoT/token 优化（prompt caching + 双模型） | agent | Trae | task24 | — | W3 | M | system+工具清单 ≤300 token、前缀稳定、caching 命中 ≥80% |
| task28 | AI 助手：HITL 退款审批（LangGraph interrupt + 超时升级工单） | agent+backend | Trae | task19, task24 | — | W3 | L | 审批通过 resume 执行退款、72h 超时升级 high |
| task29 | AI 助手评估：评估集 + LLM-as-judge + 延迟/成本验证 | test | Trae | task24~27 | — | W3 | M | 路由准确率 ≥ 基线、P95 ≤8s、首包 ≤3s |
| task30 | RAG：contextualize 写入步骤（chunk 上下文前缀 + 降级） | rag | Trae | —（可与 AI 并行） | — | W4 | L | 知识型 chunk 带前缀、失败降级原 chunk、raw_content 保留 |
| task31 | RAG：reranker 接入（top-150→rerank→top-20→断崖→5）+ course_public 分区 | rag | Trae | task30 | — | W4 | L | bge-reranker-v2-m3 接入、GPU 不可用降级规则重排、分区隔离 |
| task32 | RAG：rag_evaluator top-20 指标 + 离线评估（+15% 目标） | rag+test | Trae | task31 | — | W4 | M | 离线评估对比规则基线 ≥+15%、评估报告 |
| task33 | MCP 增强：工具描述评分/重写 + per-server 熔断 + 权限过滤 | mcp | Trae | task09 | —（前端 task62 消费契约） | W5 | M | <70 分自动重写、连续 5 败 30s 快断、admin_only 不进决策 |
| task34 | Milvus/Neo4j 清除 + 课程/题目知识切片生成与批量入库 | ops+rag | Trae | task07, task30 | — | W6 | XL | edu_knowledge 重建、行数/分区/索引校验、pf_bagu_kb 保留 |
| task35 | Neo4j 图谱重建（5 节点 + 3 边）+ 重建校验报告 | ops+rag | Trae | task34 | — | W6 | M | 节点/关系计数报告 + 检索/图谱查询冒烟 |
| task36 | RAG 上传后端增强（tasks 接口 + Redis/表双写 + MinIO edu-upload 留存） | backend+rag | Trae | task04, task10 | **契约冻结⑥→前端 task61** | W2 | M | 任务持久化重启不丢、源文件留存 30 天 |
| task37 | 旧代码清理（别名兜底/三套题库残留/未引用 schema） | ops | Trae | 全部 | — | W8 | M | grep 零残留 + 清理报告 |
| task38 | 文档交付（接口文档/数据字典/运维手册/回滚手册） | ops | Trae | 全部 | — | W8 | M | 四份文档 + degraded_reason 清单 |
| task39 | 性能压测（Locust P95 ≤800ms）+ 容灾演练（六存储宕机） | test+ops | Trae | task69, task23 | — | W8 | L | 压测报告 + 故障注入无 500 + 降级验证 |
| task40 | 前端接口层：api-client 解包 + 8 新客户端 + 10 改造 | frontend | TraeWork | task10 | 消费契约① | W7 | L | code===0 解包、ApiError 携带 message、tsc+vitest 绿 |
| task41 | UI 组件基础 C1~C14 + 全局枚举映射表（StatusBadge） | frontend | TraeWork | task40 | — | W7 | L | 14 组件 + 单测 + a11y + grep 无非法色值 |
| task42 | /login + /register 认证页（含 / 根路由重定向附项） | frontend | TraeWork | task41, task15 | 消费契约⑬ | W7 | M | 登录/注册重构、根路由登录态重定向、HTML 签收 |
| task43 | /dashboard 学习仪表盘（15 处 MOCK 删除） | frontend | TraeWork | task41, task14, task15, task23 | 消费契约⑤+⑭ | W7 | L | 全部真实 API、echarts 色板、radar 保留 |
| task44 | /courses 课程中心 | frontend | TraeWork | task41, task11 | 消费契约② | W7 | L | 筛选/搜索防抖/分页、MOCK 兜底清零 |
| task45 | /courses/search 课程搜索 | frontend | TraeWork | task41, task11 | 消费契约② | W7 | M | 搜索参数联动、结果页分页、与 task44 复用 CourseCard |
| task46 | /courses/[seriesId] 课程详情（四级展示 + 报名/领券/收藏） | frontend | TraeWork | task44, task16, task17, task20 | 消费契约②+⑦+⑧ | W7 | XL | 四级树、满员 disabled、下单跳转支付 |
| task47 | /my-courses 我的班次（enrollments 语义） | frontend | TraeWork | task41, task20, task21 | 消费契约⑪ | W7 | L | enroll 状态 tab、进度聚合、继续学习跳转 |
| task48 | /learning/[seriesId]/[sessionId] 学习播放页 | frontend | TraeWork | task41, task21, task23 | 消费契约⑪+⑭ | W7 | L | enrolled 守卫、15s 打点、作业/考试提交、转码占位 |
| task49 | /practice/[mode] 复习中心（错题本出题源切 question） | frontend | TraeWork | task41, task13, task14 | 消费契约④+⑤ | W7 | M | 出题源 question、analysis_text 展示、SM-2 词卡不动 |
| task50 | /chat AI 问答页（SSE 流式，多 agent 接口对齐） | frontend | TraeWork | task41, task15 | 消费契约⑬（不依赖 AI 新契约） | W7 | M | SSE 流式渲染、done/error 壳解析、历史消息 |
| task51 | /community 社区列表 | frontend | TraeWork | task41, task15 | 消费契约⑬ | W7 | M | 帖子列表/筛选/发布入口 |
| task52 | /community/[postId] 帖子详情 | frontend | TraeWork | task51, task15 | 消费契约⑬ | W7 | M | 评论/点赞（react）/详情渲染 |
| task53 | /achievements 成就中心 | frontend | TraeWork | task41, task15, task23 | 消费契约⑬ | W7 | M | 徽章墙/积分日志/排名真实数据 |
| task54 | /me 个人中心（student-profile/learning-summary 新接口） | frontend | TraeWork | task41, task14, task15 | 消费契约⑤ | W7 | M | 档案表单、4 StatCard 真实数据、入口列表 |
| task55 | /admin/dashboard 管理端仪表盘 | frontend | TraeWork | task41, task14, task15 | 消费契约⑤+⑬ | W7 | M | 管理端 KPI 真实数据、echarts |
| task56 | /admin/courses 管理端课程（系列+班次总览） | frontend | TraeWork | task41, task12 | 消费契约③ | W7 | L | 系列 CRUD、上下架、软删 |
| task57 | /admin/courses/[seriesId] 管理端系列详情（四级 CRUD） | frontend | TraeWork | task56, task12 | 消费契约③ | W7 | XL | 四级管理、视频分片上传+转码轮询、章节管理 |
| task58 | /admin/questions 管理端题库（两级 + 批量导入） | frontend | TraeWork | task41, task13 | 消费契约④ | W7 | L | 两级 CRUD、导入预览+进度+结果报告 |
| task59 | /admin/questions/[id] 管理端题目（解析编辑） | frontend | TraeWork | task58, task13 | 消费契约④ | W7 | M | analysis_text 必填 + Markdown 预览、题型联动 |
| task60 | /admin/users 管理端用户 | frontend | TraeWork | task41, task14, task15 | 消费契约⑤+⑬ | W7 | M | 学习详情 Dialog、最后 admin 保护 |
| task61 | /admin/rag RAG 控制台（含新增上传入口） | frontend | TraeWork | task41, task36 | 消费契约⑥ | W7 | L | 上传→任务轮询→分区管理→行数刷新全链路 |
| task62 | /admin/mcp MCP 控制台 | frontend | TraeWork | task41, task15, task33 | 消费契约⑬ | W7 | M | server/tool 列表、描述体检按钮、调用日志 |
| task63 | /coupons 优惠券中心 | frontend | TraeWork | task41, task16 | 消费契约⑦ | W7 | M | 三 tab、领取防超发、倒计时 warning |
| task64 | /orders 我的订单 | frontend | TraeWork | task41, task17 | 消费契约⑧ | W7 | M | 状态机 tab、取消、去支付、退款入口 |
| task65 | /orders/[orderId]/pay 支付页 | frontend | TraeWork | task64, task18 | 消费契约⑧+⑨ | W7 | L | 轮询 ≤15s、防双击、5s 倒计时、报名 CTA |
| task66 | /refunds 退款记录 | frontend | TraeWork | task41, task19 | 消费契约⑩ | W7 | M | 申请 Dialog、Timeline 轨迹、撤销 |
| task67 | /favorites 我的收藏（服务端） | frontend | TraeWork | task41, task16 | 消费契约⑦ | W7 | M | 服务端列表、取消 ConfirmDialog、分页 |
| task68 | /tickets 售后工单 + 人工申诉 | frontend | TraeWork | task41, task22 | 消费契约⑫ | W7 | M | appeal 类型、跟进 Timeline、满意度评分 |
| task69 | E2E 回归（Playwright 全链路 + 状态机 + 视觉验收） | test | TraeWork | task42~68（前端）+ 后端全部上线 | — | W8 | XL | 25+ 跳转全通 + 8 状态机 + 截图矩阵 |

**并行组说明**：W1 数据主线（task00~08）｜W2 后端底座+业务域（task09~23, task36）｜W3 AI 助手（task24~29）｜W4 RAG（task30~32）｜W5 MCP（task33）｜W6 知识库重建（task34~35）｜W7 前端（task40~68）｜W8 收尾（task37~39, task69）。W2 后半段与 W3/W4/W5/W7 可大范围并行；W7 内部 27 页面按契约冻结逐批解锁。

---

## 2. 任务详述

> 每个任务的**完整验收全文、agent 调度链、workflow 调用参数、实现规划要点、选型依据**见 `tasks/taskNN-*.md`；此处给出摘要版（每任务 2 条 GWT 节选 + 交付物）。

### 2.1 P0 — 备份（安全网）

#### task00：P0 全量备份与快照
- **类型/工具**：ops / Trae ｜**依赖**：无 ｜**并行组**：W1 ｜**工作量**：M ｜**选型依据**：tech-source-audit.md §七（回滚安全网）
- **交付物**：mysqldump 全库备份（--routines --triggers --single-transaction）、Milvus `edu_knowledge` 健康报告、Neo4j 计数快照（基线 4981 条/1330 节点/6194 关系）、备份清单 + SHA256、恢复演练报告
- **验收**：① Given 三存储可用 When 执行备份 Then 全库 dump + 两集合 schema 定义 + 计数快照落盘且校验和通过；② Given 备份生成 When 独立实例恢复 Then 恢复成功且行计数一致（详见 tasks/task00-*.md）

### 2.2 P1 — 数据库重构（task01~05）

#### task01：66 表 DDL 重建脚本（动作 A/D）
- **类型/工具**：database / Trae ｜**依赖**：无（与 task00 并行）｜**并行组**：W1 ｜**工作量**：XL
- **交付物**：`refactor_sql/`（66 表 DROP+CREATE 按 edu.sql + 27 保留表清单 + `order`/`question` 保留字转义规范 + 回滚脚本）
- **验收**：① Given 测试库执行 When 对比 Then 66 表与 edu.sql diff 为空；② Given 27 扩展表 When 重构 Then 零影响
- **风险**：保留字转义。缓解：全量反引号 + 单测

#### task02：13 表删除 + 引用清理（动作 C）
- **类型/工具**：database / Trae ｜**依赖**：task01 ｜**并行组**：W1 ｜**工作量**：M
- **交付物**：DROP 脚本 + 删除表→替代表映射清单 + 全库代码 grep 零引用报告
- **验收**：① Given 13 表 DROP When 全量 grep 旧表名/旧路由 Then 零引用（豁免列清单）；② Given 外键巡检 Then 无孤儿外键

#### task03：sys_user 改造 + 外键恢复 + 索引（动作 B/E）
- **类型/工具**：database / Trae ｜**依赖**：task01 ｜**并行组**：W1 ｜**工作量**：M
- **交付物**：sys_user ALTER（+account/username/status）、3 组外键恢复、10 组查询索引
- **验收**：① Given 注册/登录/JWT When 全流程 Then 可用且 account 唯一约束生效；② Given 6 大查询 EXPLAIN Then 全部走索引

#### task04：knowledge_import_task + 通用 task 表（动作 F）
- **类型/工具**：database / Trae ｜**依赖**：task01 ｜**并行组**：W1 ｜**工作量**：S
- **交付物**：knowledge_import_task DDL + 通用 task 状态表（pending/running/succeeded/failed + progress_json）
- **验收**：① Given 状态流转写入 When 重启 Then 可从表恢复；② Given 双写 Redis+MySQL Then 对账一致

#### task05：diff 校验脚本 + CI
- **类型/工具**：test / Trae ｜**依赖**：task01~03 ｜**并行组**：W1 ｜**工作量**：M
- **交付物**：`scripts/verify_schema.py` + CI workflow + 校验报告
- **验收**：① Given 全部 DDL 执行 When 运行脚本 Then 0 差异退出码 0；② Given CI 集成 When DDL 变更 Then 差异即构建失败

### 2.3 P2 — 数据重灌（task06~08）

#### task06：full 档生成脚本适配
- **类型/工具**：ops / Trae ｜**依赖**：task01~04 ｜**并行组**：W1 ｜**工作量**：L ｜**选型依据**：tech-source-audit.md §七
- **交付物**：`--layers 1..7` 分层参数 + 断点续跑 checkpoint + batch_size=5000 + 分夜跑批手册
- **验收**：① Given layer4 中断 When 重跑 Then 跳过已完成层仅续跑；② Given 执行两次 Then 幂等计数一致

#### task07：full 档执行 + 计数校验
- **类型/工具**：ops / Trae ｜**依赖**：task06 ｜**并行组**：W1 ｜**工作量**：XL ｜**联调节点**：「数据基线冻结」
- **交付物**：full 档全量数据 + 六项计数校验报告
- **验收**：① Given 六项 SQL（219/657/73/1752/10万/8万）When 校验 Then 全达标偏差 ≤0.5%；② Given 抽样 3 系列四级关联 Then 无孤儿记录

#### task08：admin 恢复 + 冒烟
- **类型/工具**：ops / Trae ｜**依赖**：task07 ｜**并行组**：W1 ｜**工作量**：M
- **交付物**：admin 恢复脚本 + 冒烟报告
- **验收**：① Given admin 恢复 When 登录 Then RBAC 正确；② Given 冒烟链路 Then 每步成功

### 2.4 P3 — 后端改造：底座与存量域（task09~15）

#### task09：core/ 框架层
- **类型/工具**：backend / Trae ｜**依赖**：无（与 P1/P2 并行）｜**并行组**：W2 ｜**工作量**：XL ｜**选型依据**：tech-source-audit.md §一（FastAPI/asyncmy）、§四（缓存三防/Polaris 熔断/幂等/Redis 多角色）
- **交付物**：resp.py/cache.py/lock.py/idempotency.py/breaker.py/trace.py/queue.py/crud_mixin.py
- **验收**：① Given 50% 错误率注入 Then 熔断三态切换 + Gauge 指标；② Given 100 并发热点 key Then 仅 1 个重建 + 空值 30s 缓存
- **风险**：Redis 多角色爆炸半径（薄弱点 W4）。缓解：组件级降级路径 + 故障注入用例

#### task10：middleware/ + 响应壳统一
- **类型/工具**：backend / Trae ｜**依赖**：task09 ｜**并行组**：W2 ｜**工作量**：XL ｜**联调节点**：**契约冻结①→前端 task40**
- **交付物**：middleware/（auth/rate_limit 双维度/trace/idempotency/circuit_breaker）+ error_codes.py 分域段码 + RespWrapMiddleware + 注册顺序表
- **验收**：① Given 契约测试遍历全部 router Then 100% 统一壳（SSE 例外）；② Given 幂等键重复 POST Then 返回首次缓存响应
- **交接**：完成后写 `handoffs/task10-contract.md`（响应壳/错误码清单 + 真实 curl 示例）→ 看板 READY_FOR_FRONTEND

#### task11：课程域 curriculum→series
- **类型/工具**：backend / Trae ｜**依赖**：task10, task03, task07 ｜**并行组**：W2 ｜**工作量**：XL ｜**联调节点**：**契约冻结②→前端 task44/45/46**
- **交付物**：domains/course/（repository 四件套）+ C 端 5 端点 + /api/curriculum/series 308 重定向
- **验收**：① Given 全筛选参数 Then snake_case 返回 + page_meta + P95<200ms；② Given 四级逐级查询 Then 层级语义与 edu.sql 一致
- **交接**：`handoffs/task11-contract.md`（5 端点 curl 示例 + 字段表）

#### task12：course_admin 重写
- **类型/工具**：backend / Trae ｜**依赖**：task11 ｜**并行组**：W2 ｜**工作量**：XL ｜**联调节点**：**契约冻结③→前端 task56/57**
- **交付物**：四级 CRUD + 视频三表 + 分片上传 init/finalize/bind + 转码轮询端点
- **验收**：① Given 系列→班次→模块→课次→视频全链 Then 落库正确 + transcode 状态可查；② Given 唯一约束冲突 Then 409xx 业务码
- **交接**：`handoffs/task12-contract.md`

#### task13：question 域
- **类型/工具**：backend / Trae ｜**依赖**：task10, task07 ｜**并行组**：W2 ｜**工作量**：L ｜**联调节点**：**契约冻结④→前端 task58/59/49**
- **交付物**：question_bank/question CRUD + 批量导入 + 组卷快照 + quiz 出题源切换 + tag 逻辑删除（全文检索替代）
- **验收**：① Given 1752 题导入 Then 失败行报告 + 幂等；② Given 考试期间改题 Then 按快照判分
- **交接**：`handoffs/task13-contract.md`

#### task14：progress/mindmap/users 改造
- **类型/工具**：backend / Trae ｜**依赖**：task11, task13 ｜**并行组**：W2 ｜**工作量**：L ｜**联调节点**：**契约冻结⑤→前端 task54/43/60**
- **交付物**：progress 提交表改造 + dashboard 四级聚合 + mindmap/recommender 数据源切换 + users bug 修复 + /me/student-profile、/me/learning-summary
- **验收**：① Given 打点提交 Then 落 edu-data 表外键生效；② Given UPDATE 失败 Then 异常上抛（P10 bug 关闭）
- **交接**：`handoffs/task14-contract.md`

#### task15：存量模块响应壳适配
- **类型/工具**：backend / Trae ｜**依赖**：task10 ｜**并行组**：W2 ｜**工作量**：M ｜**联调节点**：**契约冻结⑬→前端 task42/50/51/52/53/55/60/62**
- **交付物**：auth/chat/community/gamification/mcp/rag_admin 逐点 ok() 改造 + 排行榜 ZSET + SSE 事件内嵌壳
- **验收**：① Given 契约测试 Then 上述模块 100% 统一壳；② Given /rankings Then 数据来自 ZSET
- **交接**：`handoffs/task15-contract.md`（存量模块端点清单）

### 2.5 P4 — 后端新建：交易/报名/学习/售后 + 缓存（task16~23）

#### task16：market 域（coupons + favorites）
- **类型/工具**：backend / Trae ｜**依赖**：task10 ｜**并行组**：W2 ｜**工作量**：L ｜**联调节点**：**契约冻结⑦→前端 task63/67**
- **交付物**：GET /api/coupons、GET /api/coupons/me、POST /api/coupons/{id}/receive、favorites 3 端点
- **验收**：① Given 500 并发领取 500 张券 Then 恰 500 成功无超发；② Given 重复收藏 Then 返回原记录
- **交接**：`handoffs/task16-contract.md`

#### task17：trade/order 域
- **类型/工具**：backend / Trae ｜**依赖**：task16 ｜**并行组**：W2 ｜**工作量**：L ｜**联调节点**：**契约冻结⑧→前端 task64**
- **交付物**：5 端点 + 状态机 + 单事务下单 + order_no 唯一键幂等 + 服务端金额重算
- **验收**：① Given 篡改价格下单 Then 金额服务端计算值；② Given 100 并发同 order_no Then 仅 1 条记录
- **风险**：资金安全。缓解：三层幂等纵深 + 并发压测
- **交接**：`handoffs/task17-contract.md`

#### task18：trade/payment 域
- **类型/工具**：backend / Trae ｜**依赖**：task17 ｜**并行组**：W2 ｜**工作量**：XL ｜**联调节点**：**契约冻结⑨→前端 task65**
- **交付物**：8 端点 + mock 回调 + 支付→订单→报名→核销单事务 + 对账
- **验收**：① Given 100 并发回调同 payment_no Then 仅一次生效；② Given 支付成功 Then order/报名/券三态原子一致
- **交接**：`handoffs/task18-contract.md`

#### task19：trade/refund 域
- **类型/工具**：backend / Trae ｜**依赖**：task18 ｜**并行组**：W2 ｜**工作量**：M ｜**联调节点**：**契约冻结⑩→前端 task66**
- **交付物**：申请/撤销/列表 + refund_no 幂等 + HITL 挂载点预留
- **验收**：① Given 金额>实付 Then 拒绝业务码；② Given 撤销 Then 状态不可再撤
- **交接**：`handoffs/task19-contract.md`

#### task20：enrollment 域
- **类型/工具**：backend / Trae ｜**依赖**：task18, task11 ｜**并行组**：W2 ｜**工作量**：M ｜**联调节点**：**契约冻结⑪（与 task21）→前端 task47/48**
- **交付物**：/me/cohorts 4 端点 + 满班条件更新
- **验收**：① Given 余位 1 双并发报名 Then 仅 1 成功；② Given 报名查询 Then 进度聚合真实

#### task21：study 域
- **类型/工具**：backend / Trae ｜**依赖**：task20 ｜**并行组**：W2 ｜**工作量**：L ｜**联调节点**：契约冻结⑪（与 task20）
- **交付物**：10 端点 + access_scope 鉴权 + 15s 打点写 edu-data 表
- **验收**：① Given 未报名访问 enrolled_only Then 403；② Given tick-batch Then play_event 外键正确
- **交接**：`handoffs/task21-contract.md`（task20 合并写或分写）

#### task22：tickets 域
- **类型/工具**：backend / Trae ｜**依赖**：task17, task20 ｜**并行组**：W2 ｜**工作量**：M ｜**联调节点**：**契约冻结⑫→前端 task68**
- **交付物**：5 端点 + appeal 类型 + user_id 隔离
- **验收**：① Given appeal 工单 Then 落库 + 文案映射；② Given 跨用户访问 Then 404
- **交接**：`handoffs/task22-contract.md`

#### task23：Redis 缓存 + 慢查询治理
- **类型/工具**：backend+infra / Trae ｜**依赖**：task09, task11, task13 ｜**并行组**：W2 ｜**工作量**：L ｜**联调节点**：**契约冻结⑭→前端 task43/48 性能验收**｜**选型依据**：tech-source-audit.md §四（缓存三防/读写分离）
- **交付物**：热点缓存接入 + 写后 DEL + 排行榜 ZSET + keyset 分页 + 日志批量缓冲 + 连接池调参
- **验收**：① Given 100 并发详情 Then P95 ≤50ms 且主库 QPS 不线性增长；② Given 慢查询监控 Then 无 >500ms 热点

### 2.6 AI 助手重构（task24~29，与 W2/W4/W5/W7 并行）

#### task24：LangGraph 图重构（R1 子代理独立上下文，runner 见 task92）+ Redis checkpointer + effort scaling
- **类型/工具**：agent / Trae ｜**依赖**：task09, task10, task23 ｜**并行组**：W3 ｜**工作量**：XL ｜**选型依据**：tech-source-audit.md §二（LangGraph/orchestrator-worker/effort scaling/artifact）
- **交付物**：graph.py 主图（plan→fan-out 走 task92 runner 独立会话→merge→reflect→answer）+ AsyncRedisSaver + 4 子代理定义引用 task92 + effort scaling L0~L3 + user_id 真实注入
- **验收**：① Given 四类意图 Then 路由正确 + chitchat 直答；② Given kill 后同 thread_id Then 从 checkpoint 恢复不重复
- **风险**：薄弱点 W1（LLM 成本/延迟）。缓解：保守 scaling + 并发闸 + 评估攻防

#### task25：三层记忆 + 遗忘（R7 显式触发 + MEMORY.md 索引模式）
- **类型/工具**：agent / Trae ｜**依赖**：task24 ｜**并行组**：W3 ｜**工作量**：XL ｜**选型依据**：tech-source-audit.md §二（三层记忆/遗忘曲线）
- **交付物**：user_memory 表 + Milvus user_memory collection + MEMORY.md 索引（≤200 行常驻，topic 按需读）+ 显式触发钩子（纠正/明确要求立即写）+ 遗忘机制（exp 衰减/500 条）+ 异步写入队列
- **验收**：① Given 会话含偏好 Then 会话结束异步落库不阻塞；② Given 超 500 条 Then 最低分淘汰

#### task26：compaction + artifact + Redis 防过载（R4 context_edit，见 task96）
- **类型/工具**：agent+infra / Trae ｜**依赖**：task24 ｜**并行组**：W3 ｜**工作量**：L ｜**选型依据**：tech-source-audit.md §二（compaction/artifact）、§四（Redis 多角色）
- **交付物**：context_edit.py（轻量删消息保留前缀，见 task96）+ tool_result_clearing + artifact 分流 + 队列削峰（10s 超时提示）+ 会话并发 ≤2 + 大 key 治理
- **验收**：① Given >6k token Then 压缩后 ≤6k 保留决策语义；② Given 并发闸满 Then 排队 >10s 友好提示

#### task27：tool_specs + CoT/token 优化（R5 缓存三层组织，见 task97）
- **类型/工具**：agent / Trae ｜**依赖**：task24 ｜**并行组**：W3 ｜**工作量**：M ｜**选型依据**：tech-source-audit.md §二、§五（双模型）
- **交付物**：tool_specs.py（五要素规范）+ prompt ≤300 token + 三层缓存前缀（system/project/对话）+ 失效清单文档化 + Pydantic 校验 + answer 升级 strong
- **验收**：① Given 前缀测量 Then ≤300 token 且逐字节稳定；② Given 非法 JSON Then 重试 1 次保守回退

#### task28：HITL 退款审批
- **类型/工具**：agent+backend / Trae ｜**依赖**：task19, task24 ｜**并行组**：W3 ｜**工作量**：L ｜**选型依据**：tech-source-audit.md §二（HITL interrupt）
- **交付物**：审批图 interrupt/resume + 72h 超时升级工单
- **验收**：① Given interrupt 挂起 Then 重启可 resume；② Given 审批通过 Then 退款+order+报名原子完成

#### task29：AI 评估（R8 harness 对比：6 节点图 vs 循环 harness）
- **类型/工具**：test / Trae ｜**依赖**：task24~27 ｜**并行组**：W3 ｜**工作量**：M ｜**选型依据**：tech-source-audit.md §二（LLM-as-judge）
- **交付物**：评估集 + 对比组（图 vs 循环 harness）+ LLM-as-judge + 延迟/成本对照表 + 选型结论（若循环更优则简化主图）
- **验收**：① Given 回放 Then 路由准确率 ≥ 基线 + L0 误升 L3 <5%；② Given 压测 Then P95 ≤8s 首包 ≤3s

### 2.7 RAG 重构（task30~32）

#### task30：contextualize 写入步骤（R6 tree-sitter 语法感知切分）
- **类型/工具**：rag / Trae ｜**依赖**：无（写入链路独立）｜**并行组**：W4 ｜**工作量**：L ｜**选型依据**：tech-source-audit.md §三（Contextual Retrieval）
- **交付物**：chunker 新增 tree_sitter 模式（代码按 AST 边界，函数/类为最小 chunk）+ 文档走纯文本 + contextualize 前缀 + raw_content 保留 + 并发 8 限速
- **验收**：① Given 讲义切片 Then 知识型 chunk 带前缀 raw 保留；② Given LLM 失败 Then 降级原 chunk 入库

#### task31：reranker 接入 + course_public 分区
- **类型/工具**：rag / Trae ｜**依赖**：task30 ｜**并行组**：W4 ｜**工作量**：L ｜**选型依据**：tech-source-audit.md §三（bge-reranker-v2-m3/Milvus）
- **交付物**：reranker.py（懒加载降级）+ retriever top-150→20→断崖→5 + course_public 分区
- **验收**：① Given 模型可用 Then 链路 150→20→5；② Given 加载失败 Then 降级规则重排 + degraded_reason
- **风险**：薄弱点 W3（多 worker 显存）。缓解：懒加载单例降级

#### task32：rag_evaluator top-20 指标
- **类型/工具**：rag+test / Trae ｜**依赖**：task31 ｜**并行组**：W4 ｜**工作量**：M
- **交付物**：top-20 命中率指标 + 离线评估报告
- **验收**：① Given 评估集 Then 命中率较基线 ≥+15%；② Given 报告 Then 指标可复现

### 2.8 MCP 增强（task33）

#### task33：MCP 描述审查 + per-server 熔断 + 权限过滤（R3 工具延迟加载，认证/重连见 task95）
- **类型/工具**：mcp / Trae ｜**依赖**：task09 ｜**并行组**：W5 ｜**工作量**：M ｜**选型依据**：tech-source-audit.md §三（MCP 描述审查）
- **交付物**：description_reviewer.py（改写存延迟加载层，不进前缀保护缓存）+ 工具摘要列表稳定（name+一句话常驻）+ per-server 熔断 + admin_only 过滤 + schema 版本告警 + 只读缓存 60s
- **验收**：① Given <70 分工具 Then 自动重写 + 审计；② Given 连续 5 败 Then 30s 快断；③ Given 普通用户 Then 决策不含 admin_only
- **联调**：前端 task62 消费（MCP 控制台"描述体检"按钮）

### 2.9 Milvus/Neo4j 重建（task34~35，P8）

#### task34：Milvus/Neo4j 清除 + 切片生成与批量入库
- **类型/工具**：ops+rag / Trae ｜**依赖**：task07, task30 ｜**并行组**：W6 ｜**工作量**：XL ｜**选型依据**：tech-source-audit.md §三（Milvus）
- **交付物**：edu_knowledge drop+rebuild + courses.json/questions.json + 200/批双向量入库（断点续跑）+ 分区分布
- **验收**：① Given 中断重跑 Then upsert 跳过不重复；② Given 校验 Then 行数/分区/索引正确 + pf_bagu_kb 保留

#### task35：Neo4j 图谱重建 + 校验报告
- **类型/工具**：ops+rag / Trae ｜**依赖**：task34 ｜**并行组**：W6 ｜**工作量**：M
- **交付物**：5 节点 3 边图谱 + 计数报告
- **验收**：① Given 层级查询 Then 计数正确孤立 ≈0；② Given 三通道冒烟 Then RAG 全链路可用

### 2.10 P7 — RAG 上传后端增强（task36）

#### task36：RAG 上传后端增强
- **类型/工具**：backend+rag / Trae ｜**依赖**：task04, task10 ｜**并行组**：W2 ｜**工作量**：M ｜**联调节点**：**契约冻结⑥→前端 task61**｜**选型依据**：tech-source-audit.md §四（Redis 多角色）
- **交付物**：GET /api/knowledge/tasks + Redis/表双写 + MinIO edu-upload 留存 30 天
- **验收**：① Given 运行中重启 Then 状态恢复不丢；② Given 导入完成 Then 源文件留存 + object_key 关联
- **交接**：`handoffs/task36-contract.md`

### 2.11 P5~P6 — 前端（task40~69）

#### 2.11.0 HTML 原型审核循环（全部页面任务必经，用户强制要求）

```
① fe-spec-writer 出该页 spec（doc-frontend 已有规范页直接引用；规范缺失页先补规范，见各任务"规范状态"）
② fe-implementer 产出 test-reports/fe-html/{page}.html（单文件：文档头注释块[页面名/路由/FR/依赖API/状态机/版本]
   + 内联 <style> 全 token hex + 完整交互态 loading/empty/error/hover/active/disabled/focus + <!-- DATA:{json} -->
   + AUDIT LOG 区块）
③ 【用户 gate】提交用户审核（SUBMITTED）→ 用户讲解修改点/给设计图（逐条编号 ① ② ③）
④ fe-implementer 按图返工（REVISING，修改点 <!-- FIX-R{轮}-{序号} --> 标注）
⑤ 循环至用户签收 APPROVED（无 REJECTED 遗留）
⑥ fe-architect（复杂页）→ fe-implementer 写 React（tokens 语义 class，禁 arbitrary）
⑦ fe-styler tokens 应用 → fe-server-infra dev server → fe-perf / fe-a11y-auditor / fe-visual-auditor 并行审查
⑧ 修正 ≤3 轮 → fe-tester（Vitest + Testing Library + Playwright）
⑨ 视觉截图矩阵：375/768(双态)/1024/1280/1440 × 成功/空/错误三态
```

**fe 工作流调度链**：`fe-spec-writer → fe-implementer(HTML) → 用户审核 gate → fe-architect → fe-implementer(React) → fe-styler → fe-server-infra → fe-perf/fe-a11y-auditor/fe-visual-auditor 并行 → 修正≤3轮 → fe-tester`（详见 tasks/ 各任务文档）。

#### task40：api-client 解包 + 8 新客户端 + 10 改造
- **类型/工具**：frontend / TraeWork ｜**依赖**：task10 ｜**并行组**：W7 ｜**工作量**：L ｜**选型依据**：tech-source-audit.md §五
- **交付物**：api-client.ts 解包（code===0→data；非 0→reject ApiError；code string|number）+ 8 新建（enrollments/study/coupons/favorites/orders/payments/tickets/admin-rag 增 5 方法）+ 10 改造（curriculum/learning/admin-courses/admin-questions/dashboard/admin-users/chat/community/mcp/rag）
- **验收**：① Given `{code:0,...}` When 调用 Then 直接拿 data；② Given 字符串错误码 Then ApiError 兼容；③ Given tsc+vitest Then 全绿 + grep 无别名兜底/MOCK
- **联调**：消费契约①；开工前读 handoffs/task10-contract.md

#### task41：UI 组件基础 C1~C14 + 映射表
- **类型/工具**：frontend / TraeWork ｜**依赖**：task40 ｜**并行组**：W7 ｜**工作量**：L ｜**选型依据**：tech-source-audit.md §六（indigo/红线）
- **交付物**：DataTable/Pagination/StatusBadge(11 组枚举映射)/Stepper/Uploader/Timeline/EmptyState/ErrorState/FilterBar/ConfirmDialog/DropdownMenu/Select/Accordion/PriceText + 单测 + a11y
- **验收**：① Given vitest Then 全绿 + a11y 断言；② Given grep Then 无 arbitrary 色值/非法色

#### task42~task68：27 个页面任务（每页一个任务）

> 每页任务统一结构：HTML 审核循环（§2.11.0）+ 交付物（HTML + React + 测试）+ 消费契约（见总览表）+ 详细文档见 tasks/。规范状态：doc-frontend-design-spec.md 已有 18 页规范（dashboard/courses/search/detail/my-courses/learning/practice/me/coupons/orders/pay/refunds/favorites/tickets/admin-courses×2/admin-questions×2/admin-users/admin-rag）；**规范缺失页 6 个：task42（login/register）、task51/52（community 列表/详情）、task53（achievements）、task55（admin/dashboard）、task62（admin/mcp）——fe-spec-writer 须先行补充该页规范（布局草图+组件清单+交互+状态机+数据依赖，格式对齐 doc-frontend §二）再出 HTML**（task50 chat 规范已补充：P20）。

| 任务 | 页面 | 关键验收节选（全文见 tasks/） |
|------|------|------------------------------|
| task42 | /login + /register（附：/ 根路由登录态重定向） | 登录/注册表单重构；redirect 回跳；未登录访问受保护页跳 /login?redirect=；HTML 签收 |
| task43 | /dashboard 学习仪表盘 | 15 处 MOCK 清零、echarts 8 色板、radar/趋势/KPI/徽章/排行真实数据 |
| task44 | /courses 课程中心 | FilterBar 筛选重查、防抖 400ms、page_meta 分页、仅 on_sale、无 fallback |
| task45 | /courses/search 课程搜索 | 关键词参数联动、结果复用 CourseCard、空态「未找到相关课程」 |
| task46 | /courses/[seriesId] 课程详情 | 四级 TreeAccordion、满员 disabled、领券/收藏、POST /api/orders 跳支付 |
| task47 | /my-courses 我的班次 | enroll 三 tab、进度聚合、继续学习/售后跳转 |
| task48 | /learning 学习页 | enrolled 守卫 403、15s 打点、章节跳转、作业/考试提交、转码占位 |
| task49 | /practice/[mode] 复习中心 | 出题源 question、analysis_text 展示、SM-2 词卡不动 |
| task50 | /chat AI 问答页 | SSE 流式、done/error 内嵌壳解析、历史消息加载（规范缺失→先补规范） |
| task51 | /community 社区列表 | 帖子列表/分页/筛选、发布入口（规范缺失→先补规范） |
| task52 | /community/[postId] 帖子详情 | 评论/点赞 react/详情（规范缺失→先补规范） |
| task53 | /achievements 成就中心 | 徽章墙/积分日志/排行（规范缺失→先补规范） |
| task54 | /me 个人中心 | student-profile 表单、4 StatCard、7 入口行 |
| task55 | /admin/dashboard 管理端仪表盘 | KPI 真实数据（规范缺失→先补规范） |
| task56 | /admin/courses | 系列 CRUD、上下架、软删 |
| task57 | /admin/courses/[seriesId] | 四级 CRUD、视频分片+转码轮询、章节管理 |
| task58 | /admin/questions | 两级管理、批量导入预览/进度/结果报告 |
| task59 | /admin/questions/[id] | analysis_text 必填+Markdown 预览、题型联动 |
| task60 | /admin/users | 学习详情 Dialog 6 指标、最后 admin 保护 |
| task61 | /admin/rag（含上传入口） | UploadPanel/TaskTable 5s 轮询/PartitionPanel/_default 禁删/行数刷新 |
| task62 | /admin/mcp | server/tool 列表、描述体检按钮、调用日志（规范缺失→先补规范） |
| task63 | /coupons | 三 tab、领取防超发、倒计时 warning |
| task64 | /orders | 状态机 tab、取消、去支付、退款入口 |
| task65 | /orders/[orderId]/pay | 轮询 ≤15s、防双击、5s 倒计时、报名 CTA |
| task66 | /refunds | 申请 Dialog、Timeline、撤销 |
| task67 | /favorites | 服务端收藏、取消确认、分页 |
| task68 | /tickets | appeal 类型、跟进 Timeline、满意度 |

#### task69：E2E 回归（Playwright）
- **类型/工具**：test / TraeWork ｜**依赖**：task42~68 + 后端全部上线 ｜**并行组**：W8 ｜**工作量**：XL
- **交付物**：E2E 套件（主链路 + 25 跳转 + 8 状态机 + 截图矩阵 + RBAC 越权 + 响应壳断言）
- **验收**：① Given 全套运行 Then 全链路通过 25 跳转可达；② Given 截图矩阵 Then 无溢出/遮挡；③ Given RBAC Then student 访问管理端 403

### 2.12 P9 — 收尾（task37~39）

#### task37：旧代码清理
- **类型/工具**：ops / Trae ｜**依赖**：全部 ｜**并行组**：W8 ｜**工作量**：M
- **交付物**：清理报告（别名兜底/三套题库残留/未引用 schema/废弃代码）
- **验收**：① Given 全量 grep Then 业务代码零命中；② Given 回归 Then 无回归

#### task38：文档交付
- **类型/工具**：ops / Trae ｜**依赖**：全部 ｜**并行组**：W8 ｜**工作量**：M
- **交付物**：接口文档 + 数据字典 + 运维手册 + 回滚手册
- **验收**：① Given 运维演练 Then 可独立操作；② Given 错误码清单 Then 与前端映射一致

#### task39：性能压测 + 容灾演练
- **类型/工具**：test+ops / Trae ｜**依赖**：task69, task23 ｜**并行组**：W8 ｜**工作量**：L ｜**选型依据**：tech-source-audit.md §七
- **交付物**：Locust 压测报告 + 六存储故障注入报告
- **验收**：① Given 压测 Then P95 ≤800ms（缓存命中）/ chat ≤8s；② Given 逐一 kill 六存储 Then 核心链路无 500 且 degraded_reason 齐全

---


## 2.11 生产可复用数据库验收体系（task98，6 点原则落地）

> 依据：`db-acceptance-principles.md`（用户 6 点验收原则：P1 先文档后脚本 / P2 精确断言== / P3 动态计算 / P4 CI 门禁 / P5 5 维度质量 / P6 口径漂移声明）
> 性质：**可复用基础设施**——生产环境用户注册、增添功能、修改表结构时均沿用，非 per-task 一次性脚本。

#### task98：生产可复用数据库验收体系（verify.py 统一框架）
- **类型/工具**：infra / Trae ｜**依赖**：task05 + task07 修复 + db-acceptance-principles.md ｜**工作量**：L
- **交付物**：`scripts/verify.py`（schema/counts/quality/all 四子命令，统一入口）+ `.schema-acceptance.yaml`（容差/枚举/白名单，文档定义标准）+ `.github/workflows/db-acceptance.yml`（CI gate，失败禁合并）+ `docs/db-acceptance-guide.md`（生产使用手册）
- **验收**：① Given 生产改表，When `verify.py schema`，Then 0 差异 exit 0，失败 CI 拒绝合并（P4）；② Given 数据变更，When `verify.py all`，Then 计数精确== + 5 维度质量全绿（P2/P5）；③ Given 机构数变化，When `verify.py counts`，Then 期望值自动重算（P3 无硬编码）；④ Given 口径变更，Then 文档/yaml 先行 + 变更日志（P1/P6）
- **关键**：5 维度质量（完整性=外键+引用必达/唯一性=唯一键+逻辑重复/有效性=值域金额日期/一致性=order=SUM(items)+payment=order/时序性=created_at<=updated_at），每维度≥1 断言
- **生产复用**：后续所有数据库任务（task11~14 改表、用户功能新增）直接用 `verify.py all` 作验收


#### task99：批量 auth 补生成（100K 用户登录可用）
- **类型/工具**：ops/data / Trae ｜**依赖**：task07 + task08 ｜**并行组**：W2 ｜**工作量**：S
- **来源**：task08-技术批判.md 批判②（sys_user_auth 仅 200 条 vs sys_user 100003 条）
- **交付物**：`scripts/backfill_auth.py`（bcrypt 预哈希、--limit/--role、幂等 INSERT IGNORE、抽样验证登录）+ 报告含默认密码
- **验收**：① Given 执行，When 抽样 10 新账号登录，Then 全 200 + JWT role=student；② Given 重复执行，Then 幂等（不翻倍/无冲突）；③ Given 全量，Then auth≈user 数量级；④ Given 重跑 verify_schema，Then 0 差异（不破坏冻结）
- **关键**：不改 edu-data 生成脚本（避免重灌）；默认密码写入报告供 E2E/压测

## 3. 任务依赖图（对齐 orchestration-frontend-backend.md 契约冻结①~⑭）

### 3.1 数据主线（W1：P0~P2，Trae 独占）

```
[task00 备份]══════════════════════════════════════╗
        ║（并行）                                     ║（安全网，全阶段可用）
[task01 66表DDL]──┬──► [task02 13表删除] ──────────┐  ║
        │         ├──► [task03 sys_user+索引] ─────┤  ║
        │         └──► [task04 任务表] ────────────┤  ║
        │                                          ▼  ║
        └────────────────► [task05 diff校验] ◄──────┘  ║
                              (CI)                      ║
        ▼                                               ║
[task06 生成适配] ──► [task07 full档+计数] ──► [task08 admin+冒烟]
                         「数据基线冻结」通报 TraeWork
```

### 3.2 后端主线 + 契约冻结（W2：P3~P4/P7）

```
[task09 core/] ──► [task10 middleware+响应壳] ──【契约①】──► FE task40
                        │
        ┌───────────────┼──────────────────────┬──────────────────┬─────────────┐
        ▼               ▼                      ▼                  ▼             ▼
  [task11 course] ─【②】 FE 44/45/46    [task13 question] ─【④】 FE 58/59/49
        │               │
  [task12 cadmin] ─【③】 FE 56/57    [task14 progress/users] ─【⑤】 FE 54/43/60
        │
        ├──► [task16 market] ─【⑦】 FE 63/67
        │            └──► [task17 order] ─【⑧】 FE 64
        │                        └──► [task18 payment] ─【⑨】 FE 65
        │                                ├──► [task19 refund] ─【⑩】 FE 66
        │                                └──► [task20 enrollment] ──► [task21 study] ─【⑪】 FE 47/48
        │                                        └──► [task22 tickets] ─【⑫】 FE 68
        │
  [task15 存量适配] ─【⑬】 FE 42/50/51/52/53/55/60/62
  [task23 缓存] ─【⑭】 FE 43/48 性能验收
  [task04/10] ──► [task36 RAG上传后端] ─【⑥】 FE 61
```

### 3.3 AI / RAG / MCP / KB 支线（W3/W4/W5/W6）

```
[task09/10/23] ──► [task24 图+checkpointer+effort] ─┬─► [task25 记忆]
                                                     ├─► [task26 compaction+防过载]
                                                     ├─► [task27 tool_specs] ────► [task29 评估]
                                                     └─► [task28 HITL]（另依赖 task19）
[task30 contextualize] ══► [task31 reranker+分区] ══► [task32 评估]
[task09] ──► [task33 MCP]（FE task62 消费）
[task07+30] ──► [task34 KB清除重建] ──► [task35 图谱+校验]
```

### 3.4 前端主线（W7：P5~P6，TraeWork）

```
【契约①】task10 ──► task40 api-client ──► task41 组件基础 ──► 27 页面按契约逐批解锁：
  批1（契约②③④⑤⑬⑭ 陆续冻结）: task42~62 中的存量页（44/45/46/56/57/58/59/54/43/60/42/50/51/52/53/55/62）
  批2（契约⑦~⑫ 交易域）: task63/64/65/66/67/68 + 依赖报名学习域 task47/48
  批3（契约⑥）: task61 RAG 上传
  收尾: task69 E2E（依赖全部页面 + 后端上线）
```

### 3.5 收尾（W8：P9）

```
[全部] ──► task37 清理 ══► task38 文档
[task42~68] ──► task69 E2E ──► task39 压测+容灾
```

### 3.6 跨工具并行窗口（对齐 orchestration §四）

| 窗口 | Trae 在做 | TraeWork 在做 | 前提 |
|------|----------|-----------|------|
| W-A | task09~15（后端底座） | 规范准备：读 doc-frontend-design-spec、搭 test-reports/fe-html 模板、预读 api-client.ts（不写正式代码） | 契约①未发布 |
| W-B | task16~23 + task24~35 + task36 | task40→41→42~68 逐页（契约随发随做） | 每域契约冻结即解锁对应页 |
| W-C | task34~35（知识库重建） | 任意剩余页面 | 互不依赖 |
| W-D | task37/38/39（收尾） | task69（E2E） | 后端全部上线 |

---

## 4. 阶段检查点（P0~P9 里程碑）

| 阶段 | 任务范围 | 检查点 | 可验收里程碑 |
|------|---------|--------|-------------|
| P0 | task00 | CP0：备份可恢复 | 恢复演练报告通过（独立实例恢复 + 计数一致） |
| P1 | task01~05 | CP1：数据库结构就绪 | verify_schema.py 输出 0 差异；13 表删除零引用；登录/外键/索引验证通过 |
| P2 | task06~08 | CP2：full 档数据就绪 | 六项计数 219/657/73/1752/10万/8万 全达标；admin 恢复登录；数据层冒烟通过 |
| P3 | task09~15 | CP3：后端底座+存量域完成 | pytest 全绿；契约测试 100% 统一壳；契约①②③④⑤⑬冻结交接单齐备；/api/series 冒烟通过 |
| P4 | task16~23 | CP4：后端新域+缓存就绪 | 交易/报名/学习/售后联调通过；契约⑦~⑫⑭冻结交接单齐备；支付并发 100 重试幂等验证；慢查询无 >500ms |
| P4.5 | task24~33 | CP4.5：AI/RAG/MCP 升级完成 | AI 路由准确率 ≥ 基线、P95 ≤8s、compaction ≤6k；RAG top-20 命中 +15%；MCP 描述体检全过 |
| P5 | task40~41 | CP5：前端接口层+组件就绪 | tsc+vitest 全绿；grep 无别名兜底/MOCK；组件 a11y 通过 |
| P6 | task42~68 | CP6：全部 27 页面完成 | 27 页全部 APPROVED 签收 + React 实现 + 截图矩阵通过（每页独立签收台账） |
| P7 | task36（+task61 联动） | CP7：RAG 上传入口闭环 | 上传→任务进度→分区管理→检索可见全链路；重启不丢任务；MinIO 留存验证 |
| P8 | task34~35 | CP8：知识库重建完成 | 重建计数报告 + 检索/图谱查询冒烟通过；pf_bagu_kb 保留确认 |
| P9 | task37/38/69/39 | CP9：整体可交付 | E2E 全链路通过；压测 P95 ≤800ms；六存储容灾演练无 500；文档齐备 |

**阶段门禁规则**：任一检查点未通过，不得进入下一阶段；CP0~CP2 为数据安全红线（可回滚点）；契约冻结发布（CP3/CP4）后字段变更必须走契约变更单（collaboration-protocol.md §二）。

---

## 5. 风险清单

| # | 风险 | 关联任务 | 等级 | 缓解措施 |
|---|------|---------|------|---------|
| R1 | full 档生成耗时超单夜窗口 | task06/07 | 高 | 分夜跑批 + checkpoint 到 layer 内批次 + 每日进度报告 + 幂等重入 |
| R2 | 支付/退款资金安全（重复入账、少核销、退款后仍可上课） | task17/18/19/20/28 | 高 | 三层幂等纵深 + 100 并发回调压测 + 对账任务 + HITL resume 原子落库 |
| R3 | AI 多子代理成本/延迟放大（L3 10+ 调用） | task24/29 | 高 | effort scaling 保守化 + 评估集攻防 + 并发闸 8 + 会话并发 ≤2 + prompt caching |
| R4 | 多 worker 模型重复加载 OOM（~17GB） | task31/34 | 高 | 懒加载+单例+降级规则重排；必要时独立 reranker 服务；压测内存水位 |
| R5 | Redis 多角色单点故障爆炸半径 | task09/23/26 | 高 | 组件级显式降级路径 + 故障注入用例 + 大 key 治理 |
| R6 | 66 表迁移与存量自建表冲突（保留字/字段映射） | task01/02/05/07 | 高 | 反引号规范 + verify_schema CI 卡口 + grep 零引用 + P0 备份随时回滚 |
| R7 | **前端 27 页 × 审核循环节奏失控**（v3.0 范围扩大后的最大新增风险） | task42~68 | 高 | 按契约分批解锁（存量页批1 → 交易页批2 → RAG 批3）+ 每页独立签收台账 + 7 个规范缺失页由 fe-spec-writer 先行补规范 + 审核轮次记录进 HTML AUDIT LOG |
| R8 | Milvus 重建向量化耗时跨夜 | task34 | 中 | EMBED_BATCH_SIZE 32 + 先课程后题目 + upsert 断点续跑 |
| R9 | 缓存一致性（DEL 遗漏 → 旧价格/旧余位） | task23 | 中 | 写路径 DEL 穷尽清单 + 短 TTL 兜底 + task39 压测验证 |
| R10 | 响应壳统一破坏存量前端 | task10/15/40 | 中 | 契约测试遍历 + RespWrapMiddleware 兜底 + task40 同步改造 |
| R11 | 前后端并行契约漂移（冻结后字段悄悄改） | 契约①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭ | 高 | contract-diff.py 每次交接前跑（差异=阻断）；越界上浮；编排者 30 分钟仲裁 |
| R12 | 存量 10 个 API 客户端改造破坏现有页面 | task40 | 中 | 契约先行 + 逐客户端单测 + 页面消费兜底回归 |
| R13 | 13 旧表隐藏引用（动态 SQL） | task02/37 | 中 | f-string 表名 grep + 观察期监控 + task37 终检 |
| R14 | 规范缺失页（7 个）设计失控 | task42/50/51/52/53/55/62 | 中 | fe-spec-writer 先补规范再出 HTML；规范格式对齐 doc-frontend §二；用户审核 gate 兜底 |
| R15 | 收尾 E2E/压测发现跨域缺陷返工 | task69/39 | 中 | 阶段门禁 + P4 联调前置 + task69 早启动（页面完成即补用例） |

**回滚总原则**：P0 备份（task00）可在任一步骤前恢复；数据库重构（task01~04）在 P2 生成前可整体回退；Milvus 重建（task34）前保留集合 schema 定义与 Neo4j 计数快照；代码走 git 分支回退，每 task 独立提交。

---


## 2.9 管理端补全任务（task70~91，P0+P1 范围）

#### task70：M5 公告+站内信后端（新表+接口）

- **类型**：backend｜**依赖**：task03, task10｜**并行组**：W2｜**工作量**：L｜**执行工具**：Trae
- **交付物**：announcement/user_notification 2 张新表 DDL + 公告 CRUD（发布/下线/范围选择）+ 站内信（发送/未读列表/已读）+ C 端 GET /api/me/notifications
- **验收标准**：
  - Given 管理端发布公告，When 选范围(all/cohort/grade)并发布，Then 目标学员 GET /api/me/notifications 可见且未读角标+1；已读置位后不再出现
- **选型依据**：见 tech-source-audit.md §一/§三（响应壳/Redis 等）
- **联调节点**：契约冻结（见 orchestration-frontend-backend.md）
#### task71：M1 订单管理后端

- **类型**：backend｜**依赖**：task17｜**并行组**：W2｜**工作量**：M｜**执行工具**：Trae
- **交付物**：app/domains/trade/order/admin.py：GET /api/admin/orders（status/时间/金额/分页）、GET /api/admin/orders/{id}（含 items+payments）、POST /api/admin/orders/{id}/cancel、POST /api/admin/orders/{id}/note
- **验收标准**：
  - Given admin 请求订单列表，When 按状态/时间过滤，Then 返回分页订单含学员/班次/金额/状态徽章数据；详情含支付流水；代取消仅限 pending 态
- **选型依据**：见 tech-source-audit.md §一/§三（响应壳/Redis 等）
- **联调节点**：契约冻结（见 orchestration-frontend-backend.md）
#### task72：M2 退款审批后端（HITL）

- **类型**：backend｜**依赖**：task19, task28｜**并行组**：W2｜**工作量**：L｜**执行工具**：Trae
- **交付物**：GET /api/admin/refunds（status/原因/分页）、GET /api/admin/refunds/{id}、POST /api/admin/refunds/{id}/approve（执行退款+订单回滚+报名联动）、POST /api/admin/refunds/{id}/reject（含 remark）；对接 task28 LangGraph interrupt
- **验收标准**：
  - Given 退款单 pending，When admin 审批通过，Then 退款落库+order=refunded+student_cohort_rel=refunded 原子完成；拒绝时返回 remark 供 C 端展示；并发重复审批仅一次生效
- **选型依据**：见 tech-source-audit.md §一/§三（响应壳/Redis 等）
- **联调节点**：契约冻结（见 orchestration-frontend-backend.md）
#### task73：M3 报名/学员画像后端

- **类型**：backend｜**依赖**：task20, task21｜**并行组**：W2｜**工作量**：XL｜**执行工具**：Trae
- **交付物**：GET /api/admin/cohorts/{id}/students（学员列表+进度聚合）、GET /api/admin/students/{id}/profile（学习画像）、GET /api/admin/students/{id}/answers（作答详情：每题答案/判分/解析）、POST /api/admin/cohorts/{id}/students/{sid}/kick
- **验收标准**：
  - Given 班级学员列表，When 请求，Then 返回姓名/进度条/出勤/作业完成/考试分聚合；学员详情含作答明细（引用 question 表解析）；移出班级后 student_cohort_rel 状态联动
- **选型依据**：见 tech-source-audit.md §一/§三（响应壳/Redis 等）
- **联调节点**：契约冻结（见 orchestration-frontend-backend.md）
#### task75：M6 工单管理后端

- **类型**：backend｜**依赖**：task22｜**并行组**：W2｜**工作量**：M｜**执行工具**：Trae
- **交付物**：GET /api/admin/tickets（type/status/priority/分页）、GET /api/admin/tickets/{id}、POST /api/admin/tickets/{id}/reply（客服回复→follow_record）、POST /api/admin/tickets/{id}/assign、POST /api/admin/tickets/{id}/close、GET /api/admin/tickets/satisfaction-stats
- **验收标准**：
  - Given 工单列表，When 按类型/优先级过滤，Then 返回含 first_response_at 的工单；详情含多轮时间线；客服回复写入 follow_record；满意度统计聚合 score 分布
- **选型依据**：见 tech-source-audit.md §一/§三（响应壳/Redis 等）
- **联调节点**：契约冻结（见 orchestration-frontend-backend.md）
#### task77b：M8 报表后端

- **类型**：backend｜**依赖**：task71, task73｜**并行组**：W2｜**工作量**：M｜**执行工具**：Trae
- **交付物**：GET /api/admin/reports/revenue（营收趋势/渠道/课程维度）、GET /api/admin/reports/funnel（曝光→咨询→领券→下单→支付→报名 漏斗）、GET /api/admin/reports/attendance（出勤率/完课率）
- **验收标准**：
  - Given 报表接口，When 请求，Then 返回按日/周/月聚合数据（Redis 缓存 60s）；漏斗各环节计数与 C 端真实事件一致
- **选型依据**：见 tech-source-audit.md §一/§三（响应壳/Redis 等）
- **联调节点**：契约冻结（见 orchestration-frontend-backend.md）
#### task88：M10 营销管理后端（券管理）

- **类型**：backend｜**依赖**：task16｜**并行组**：W2｜**工作量**：M｜**执行工具**：Trae
- **交付物**：GET/POST /api/admin/coupons（发券/券模板 CRUD）、GET /api/admin/coupons/receives（领取/核销统计）、POST /api/admin/coupons/{id}/offline（停发）；拼团/分销表留二期
- **验收标准**：
  - Given admin 发券，When 创建券模板，Then 用户端可领列表可见；核销统计按状态聚合；停发后不可再领
- **选型依据**：见 tech-source-audit.md §一/§三（响应壳/Redis 等）
- **联调节点**：契约冻结（见 orchestration-frontend-backend.md）
#### task89：M11 CRM 线索后端

- **类型**：backend｜**依赖**：task10｜**并行组**：W2｜**工作量**：M｜**执行工具**：Trae
- **交付物**：GET/POST /api/admin/crm/leads（线索列表/新建，复用 consultation_record）、POST /api/admin/crm/leads/{id}/follow（跟进）、GET /api/admin/crm/stats（销售漏斗）、POST /api/admin/crm/leads/{id}/transfer（流转/回收）
- **验收标准**：
  - Given 线索列表，When 按渠道/状态过滤，Then 返回来源渠道/跟进时间/状态；跟进记录时间线；销售漏斗 线索→成单 计数一致
- **选型依据**：见 tech-source-audit.md §一/§三（响应壳/Redis 等）
- **联调节点**：契约冻结（见 orchestration-frontend-backend.md）
#### task78：/admin/orders 订单管理页

- **类型**：frontend｜**依赖**：task41, task71｜**并行组**：W7｜**工作量**：L｜**执行工具**：TraeWork
- **交付物**：订单列表（状态 Tab+筛选+分页）+ 详情抽屉（items+支付流水+退款入口）+ 代取消（ConfirmDialog）+ 备注
- **验收标准**：
  - Given 订单列表，When 切换状态 Tab/筛选，Then 重查分页；详情展示支付流水；代取消 pending 单成功并 toast；HTML 原型审核通过
- **选型依据**：见 tech-source-audit.md §一/§三（响应壳/Redis 等）
- **联调节点**：契约冻结（见 orchestration-frontend-backend.md）
#### task79：/admin/refunds 退款审批页

- **类型**：frontend｜**依赖**：task41, task72｜**并行组**：W7｜**工作量**：L｜**执行工具**：TraeWork
- **交付物**：退款单列表（状态/原因筛选）+ 详情+审批弹窗（通过/拒绝填理由）+ 拒绝理由展示
- **验收标准**：
  - Given 退款单，When admin 审批，Then 通过后状态流转+报名联动提示；拒绝填理由；HTML 原型审核通过
- **选型依据**：见 tech-source-audit.md §一/§三（响应壳/Redis 等）
- **联调节点**：契约冻结（见 orchestration-frontend-backend.md）
#### task80：/admin/cohorts/[id] 班级学员页

- **类型**：frontend｜**依赖**：task41, task73｜**并行组**：W7｜**工作量**：L｜**执行工具**：TraeWork
- **交付物**：班级学员列表（姓名/进度条/出勤/作业/考试分）+ 学员移出（ConfirmDialog）+ 分页
- **验收标准**：
  - Given 班级学员列表，When 请求，Then 展示进度聚合；移出确认后状态联动；HTML 原型审核通过
- **选型依据**：见 tech-source-audit.md §一/§三（响应壳/Redis 等）
- **联调节点**：契约冻结（见 orchestration-frontend-backend.md）
#### task81：/admin/students/[id] 学员详情+作答页

- **类型**：frontend｜**依赖**：task41, task73｜**并行组**：W7｜**工作量**：XL｜**执行工具**：TraeWork
- **交付物**：学员画像（课次进度/出勤/作业/成绩统计卡）+ 作答明细（每题题干/答案/判分/解析，analysis_text 展示）
- **验收标准**：
  - Given 学员详情，When 请求，Then 画像统计真实聚合；作答明细按题展示解析；HTML 原型审核通过
- **选型依据**：见 tech-source-audit.md §一/§三（响应壳/Redis 等）
- **联调节点**：契约冻结（见 orchestration-frontend-backend.md）
#### task83：/admin/tickets 工单+申诉页

- **类型**：frontend｜**依赖**：task41, task75｜**并行组**：W7｜**工作量**：L｜**执行工具**：TraeWork
- **交付物**：工单列表（类型含 appeal/优先级/状态）+ 详情时间线（多轮回复）+ 回复框+分配+关闭+满意度统计卡
- **验收标准**：
  - Given 工单详情，When 客服回复，Then 时间线追加+状态更新；申诉类型专属流程；HTML 原型审核通过
- **选型依据**：见 tech-source-audit.md §一/§三（响应壳/Redis 等）
- **联调节点**：契约冻结（见 orchestration-frontend-backend.md）
#### task84：/admin/announcements 公告发布页

- **类型**：frontend｜**依赖**：task41, task70｜**并行组**：W7｜**工作量**：M｜**执行工具**：TraeWork
- **交付物**：公告列表（状态）+ 编辑器（标题/内容/范围选择 all/cohort/grade）+ 发布/下线
- **验收标准**：
  - Given 新建公告，When 选择范围并发布，Then 状态=published+学员可见；HTML 原型审核通过
- **选型依据**：见 tech-source-audit.md §一/§三（响应壳/Redis 等）
- **联调节点**：契约冻结（见 orchestration-frontend-backend.md）
#### task85：/admin/messages 站内信台

- **类型**：frontend｜**依赖**：task41, task70｜**并行组**：W7｜**工作量**：M｜**执行工具**：TraeWork
- **交付物**：站内信发送台（选班级/学员+模板）+ 发送记录列表
- **验收标准**：
  - Given 选目标发送，When 提交，Then 目标用户收到通知；HTML 原型审核通过
- **选型依据**：见 tech-source-audit.md §一/§三（响应壳/Redis 等）
- **联调节点**：契约冻结（见 orchestration-frontend-backend.md）
#### task90：/admin/marketing 营销管理页

- **类型**：frontend｜**依赖**：task41, task88｜**并行组**：W7｜**工作量**：M｜**执行工具**：TraeWork
- **交付物**：券模板管理（新建/停发/列表）+ 领取/核销统计图表
- **验收标准**：
  - Given 券管理页，When 新建/停发，Then 状态联动+统计刷新；HTML 原型审核通过
- **选型依据**：见 tech-source-audit.md §一/§三（响应壳/Redis 等）
- **联调节点**：契约冻结（见 orchestration-frontend-backend.md）
#### task91：/admin/crm CRM 线索页

- **类型**：frontend｜**依赖**：task41, task89｜**并行组**：W7｜**工作量**：M｜**执行工具**：TraeWork
- **交付物**：线索列表（渠道/状态/跟进时间筛选）+ 详情跟进时间线+销售漏斗统计
- **验收标准**：
  - Given 线索列表，When 筛选，Then 返回渠道来源；跟进追加；漏斗计数真实；HTML 原型审核通过
- **选型依据**：见 tech-source-audit.md §一/§三（响应壳/Redis 等）
- **联调节点**：契约冻结（见 orchestration-frontend-backend.md）
#### task86：/admin/reports 报表页

- **类型**：frontend｜**依赖**：task41, task77b｜**并行组**：W7｜**工作量**：L｜**执行工具**：TraeWork
- **交付物**：营收趋势（折线）+ 转化漏斗（漏斗图）+ 出勤/完课率（柱状/环形）+ echarts 图表色板
- **验收标准**：
  - Given 报表页，When 切换维度/周期，Then echarts 渲染真实聚合数据；空态处理；HTML 原型审核通过
- **选型依据**：见 tech-source-audit.md §一/§三（响应壳/Redis 等）
- **联调节点**：契约冻结（见 orchestration-frontend-backend.md）

| task70 | M5 公告+站内信后端 | backend | Trae | task03, task10 | W2 | L | 公告/站内信 2 新表+CRUD+C 端未读接口 |
| task71 | M1 订单管理后端 | backend | Trae | task17 | W2 | M | admin orders 4 接口+状态过滤 |
| task72 | M2 退款审批后端(HITL) | backend | Trae | task19, task28 | W2 | L | admin refunds 4 接口+HITL 挂载 |
| task73 | M3 报名/学员画像后端 | backend | Trae | task20, task21 | W2 | XL | cohort students+profile+answers 聚合 |
| task75 | M6 工单管理后端 | backend | Trae | task22 | W2 | M | admin tickets 6 接口+满意度统计 |
| task77b | M8 报表后端 | backend | Trae | task71, task73 | W2 | M | 营收/漏斗/出勤报表 |
| task88 | M10 营销管理后端(券) | backend | Trae | task16 | W2 | M | 券模板 CRUD+核销统计 |
| task89 | M11 CRM 线索后端 | backend | Trae | task10 | W2 | M | leads CRUD+follow+stats+transfer |
| task78 | /admin/orders 订单管理页 | frontend | TraeWork | task41, task71 | W7 | L | 订单列表+详情+代取消+备注 |
| task79 | /admin/refunds 退款审批页 | frontend | TraeWork | task41, task72 | W7 | L | 退款单+审批弹窗+拒绝理由 |
| task80 | /admin/cohorts/[id] 班级学员页 | frontend | TraeWork | task41, task73 | W7 | L | 学员列表+进度+移出 |
| task81 | /admin/students/[id] 学员详情+作答页 | frontend | TraeWork | task41, task73 | W7 | XL | 画像+作答明细(解析) |
| task83 | /admin/tickets 工单+申诉页 | frontend | TraeWork | task41, task75 | W7 | L | 工单时间线+回复+满意度 |
| task84 | /admin/announcements 公告发布页 | frontend | TraeWork | task41, task70 | W7 | M | 公告编辑器+范围发布 |
| task85 | /admin/messages 站内信台 | frontend | TraeWork | task41, task70 | W7 | M | 发送台+记录 |
| task86 | /admin/reports 报表页 | frontend | TraeWork | task41, task77b | W7 | L | echarts 营收/漏斗/出勤 |
| task90 | /admin/marketing 营销管理页 | frontend | TraeWork | task41, task88 | W7 | M | 券管理+核销统计 |
| task91 | /admin/crm CRM 线索页 | frontend | TraeWork | task41, task89 | W7 | M | 线索+跟进+漏斗 |

## 2.10 AI 助手 8 项修订任务（task92~97，self-critique 落地）

> 依据：`.opencode/plans/self-critique-ai-agent-vs-competitors.md`（九维度批判）+ `ai-agent-revision-plan.md`（8 项修订）。
> 原则：修订设计（R1~R8）先于 task24~27 实现，避免返工。

#### task92：子代理定义 + 独立上下文 runner（R1）
- **类型/工具**：agent / Trae ｜**依赖**：task09, task10 ｜**并行组**：W3 ｜**工作量**：XL ｜**选型依据**：self-critique §三 R1 + tech-source-audit §二
- **交付物**：`app/ai/subagents/runner.py`（独立 LLM 会话循环：独立 messages/system prompt/工具集/maxTurns）+ `definitions.yaml`（子代理 frontmatter：name/description/tools/model/maxTurns/memory_scope，对齐 Claude Code）+ 4 内置子代理（search/tool/learning/memory）+ artifact 写入
- **验收**：① Given 2 个并行子代理，When 执行，Then 各自独立上下文（非共享 state），主 state 仅收 ≤2000 token 蒸馏摘要 ② Given 子代理检索 100 文档，When 完成，Then 原文在 artifact、主上下文只含摘要 ③ Given 子代理崩溃，When 重试，Then 不污染主上下文
- **关键**：修复 self-critique 维度3 结构性缺陷（原计划子代理共享 state，丢失上下文隔离）

#### task93：skill runtime（R2）
- **类型/工具**：agent / Trae ｜**依赖**：task92 ｜**并行组**：W3 ｜**工作量**：L ｜**选型依据**：self-critique §三 R2 + tech-source-audit 新增
- **交付物**：`app/ai/skills/runtime.py`（SKILL.md 解析：frontmatter description/name/paths/context/disable-model-invocation/allowed-tools）+ `registry.py`（扫描 AI-Hub skills + 项目 .claude/skills）+ `loader.py`（渐进式披露：description 列表常驻 ≤1536 字符/条，body 按需加载）+ `trigger.py`（description 匹配 + paths 条件触发）+ `fork_exec.py`（context:fork 走 task92 runner）
- **验收**：① Given AI-Hub 56 skills，When registry 启动，Then 全部索引 ② Given 触发匹配，When 决策，Then body 按需注入（不进前缀）③ Given allowed-tools，When 执行，Then 该轮工具免授权
- **关键**：补 self-critique 维度4 结构性缺失（skill 机制是三家通用标准 agentskills.io）

#### task94：AI-Hub 56 skills 接入验证（R2 落地）
- **类型/工具**：agent / Trae ｜**依赖**：task93 ｜**并行组**：W3 ｜**工作量**：S
- **交付物**：56 个 skills 全量注册验证 + 抽 3 个代表性 skill（如 dev-standard/audit/knowledge-trace）跑通渐进式披露
- **验收**：Given 全部 skills 注册，When 请求触发代表性 skill，Then 正确加载执行；无 404/死链 skill

#### task95：MCP 认证/重连/动态更新/子代理隔离（R3）
- **类型/工具**：agent / Trae ｜**依赖**：task09, task33 ｜**并行组**：W3 ｜**工作量**：L ｜**选型依据**：self-critique §三 R3 + Claude Code prompt-caching（tool search 保护前缀）
- **交付物**：MCP 工具延迟加载（摘要列表常驻，完整描述按需拉取，变更不破坏缓存前缀）+ OAuth 认证（Authorization Code + API key）+ 自动重连（指数退避 ≤5）+ 动态工具更新监听 + 子代理级 mcpServers 隔离 + per-tool 结果大小限制
- **验收**：① Given MCP 工具列表变更，When 会话中，Then 缓存前缀不受影响（deferred 语义）② Given server 进程退出，When 检测，Then 自动重连 ③ Given 子代理配置 mcpServers 子集，Then 主上下文不含这些工具
- **关键**：修复 self-critique 维度2/9 结构性缺陷（MCP 描述进前缀导致缓存失效）

#### task96：context editing + 上下文监控（R4）
- **类型/工具**：agent / Trae ｜**依赖**：task26 改造 ｜**并行组**：W3 ｜**工作量**：L ｜**选型依据**：self-critique §三 R4 + Claude Code（context editing 最轻量手段）
- **交付物**：`context_edit.py`（精确删除历史消息保留前缀缓存：删工具调用+结果/冗余中间消息，保留用户意图/未完成决策）+ `tool_result_clearing`（工具结果 N 轮后精简为一行结论，原文进 artifact）+ 上下文使用率监控 + 阈值策略配置（context_edit 优先，compaction 兜底）
- **验收**：① Given 历史 3 条工具调用各 1500 token，When context_edit，Then 减 ~4.5k token 且前缀不变 ② Given 工具结果超 N 轮，Then 精简为一行 ③ Given 超阈值，Then 先 context_edit 后 compaction

#### task97：缓存监控（R5）
- **类型/工具**：agent / Trae ｜**依赖**：task95, task27 改造 ｜**并行组**：W3 ｜**工作量**：M ｜**选型依据**：self-critique §三 R5 + Claude Code prompt-caching（cache_read/creation 指标）
- **交付物**：description_reviewer.py（改写存延迟加载层）+ 摘要列表稳定 + per-server 熔断 + admin_only 过滤 + schema 版本告警 + 只读缓存 60s
- **验收**：① Given 多轮对话，When 观察 /metrics，Then 命中率持续上报 >50% ② Given MCP 变更，Then 命中率不受影响（R3 生效）③ Given 模型切换，Then 命中率下降且记录失效原因

## 附录 A：交付物总清单

1. 数据库：重构 SQL（66 表重建 + 13 删除 + 改造 + 索引 + 任务表）+ diff 校验脚本
2. 数据：full 档全量数据 + 六项计数校验报告 + 分层生成手册
3. 后端：core/ + middleware/ + 7 新域（market/order/payment/refund/enrollment/study/tickets）+ 4 改造域 + Redis 缓存层 + 响应壳统一 + pytest
4. AI 助手：LangGraph 新图 + Redis checkpointer + 三层记忆 + compaction + tool_specs + HITL + 评估报告
5. RAG：contextualize + reranker + course_public 分区 + rag_evaluator 报告
6. MCP：描述审查器 + per-server 熔断 + 审计日志
7. 前端：api-client 改造 + 8 新/10 改造客户端 + 14 基础组件 + **27 页面**（每页：HTML 审核台账 + React + 测试）
8. RAG 上传：前端 UploadPanel/PartitionPanel/TaskTable + 后端 tasks 接口 + Redis/表双写 + MinIO edu-upload 留存
9. 知识库：Milvus/Neo4j 重建报告
10. 收尾：清理报告 + 四份文档 + E2E 套件 + Locust 压测报告 + 容灾演练报告

## 附录 B：task-agent-matrix.md 重排说明（v3.0）

> 旧矩阵（59 任务编号）已随本文件重排，映射关系：旧 task36→新 task40、旧 task37→新 task41、旧 task38~53（18 页+适配组）→新 task42~68（27 页，每页一任务）、旧 task54→新 task36、旧 task55→新 task37、旧 task56→新 task38、旧 task57→新 task69、旧 task58→新 task39；后端 task00~35 编号不变。新矩阵以本文件总览表 + `tasks/taskNN-*.md` 的「Agent 调度链」节为准；`task-agent-matrix.md` 本体由编排者在下次维护时同步（本文件为规划权威）。
