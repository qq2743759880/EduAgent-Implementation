# Bili-Study 当前功能与展示盘点

2026-10-07。依据当前源码、242项真实 OpenAPI 操作、25页 standalone 与既有原始验收记录。盘点时做了17项管理员/学生读取冒烟，正确参数下均200；读取可用不等于完整写流程通过。接口存在与完整业务验收分开标注。

## 读法

“实机”指有真实媒体/文档/用户请求证据；“可读”只证明此次接口响应；“待复验”不得写成完整可演示；“离线”是页面预览。依赖、API和页面不是同一完成标准。

## 学生产品

| 功能 | 当前涉及的能力 | 展示/验收边界 | 入口 | 源码 |
|---|---|---|---|---|
| 账号与个人画像 | 注册、登录、刷新 Token、角色识别、个人资料、学习目标/身份/偏好与学员档案 | 登录与权限已有实证；资料接口可读 | login-register / me | `app/auth; app/users` |
| 课程中心 | 分类、关键词、价格/交付模式筛选、排序分页、系列详情、班次、模块/课次与大纲 | 页面/接口存在；真实课程与历史代表课须区分 | courses / course-detail | `app/domains/course` |
| 报名与我的班次 | 报名关系、班次访问鉴权、课程进度快照、模块/课次完成态、已下架课程已有报名兼容 | 真实学生免费报名/学习已验收 | my-cohorts / learning | `app/domains/enrollment; app/domains/learning` |
| 视频播放器 | 授权播放、Range、播放进度保存、暂停/拖动/章节跳转；原视频与派生资料独立 | 真实媒体已验收 | learning | `app/domains/learning; app/progress` |
| 视频 AI 学习资料 | Summary、AI 笔记、带时间字幕、章节；节点/连线导图、展开子节点、节点详情与回看 | 多视频已有闭环；导图当前有独立节点渲染器 | learning | `app/domains/video_learning; public/video-mindmap.js` |
| 本课答疑 | StudyContext 授权、课程背景、同课历史、正式版本精确检索、视频引用时间跳转、跨课/越权拒绝 | P1/P3/P26及新增视频已有实证；不是完整 Agent 工具循环 | learning → chat | `app/chat/service.py; app/domains/learning/study_context.py` |
| 普通 AI 问答 | SSE 流式回答、非流式问答、多会话、历史、删除会话、引用、检索元数据、失败/降级提示 | 真实知识回答与历史持久化已有实证 | chat | `app/chat` |
| 课程题与独立题库 | 正式题库、题型选择、按课程/薄弱知识点取题、正式版本、学生权限、题库专项练习 | 已有实机题库闭环；本次题库列表可读 | practice | `app/interactive/quiz` |
| 作答与错题复习 | 即时判分、解析、幂等作答、冲突答案拒绝、错题记录、到期复习、原题重做、复习时间 | 真实判错/重做已有实证；本次错题列表可读 | practice | `app/interactive/quiz` |
| 视频自动练习 | 编译阶段生成本视频相关题，绑定课次/题库，随正式版本提供，支持补产习题 | 2026-10-07视频验收含 exercise_count=4；不代表所有旧课有题 | learning / practice | `app/domains/video_learning/exercises.py` |
| 词汇复习 | 今日新词/到期词、SM-2 质量评分、等级进度、打卡/正确率 | 前后端已接线；本次进度接口可读，整条学习闭环需专项复验 | practice 词汇区 | `app/interactive/vocab` |
| 编程练习 | 挑战列表/详情、样例运行、隐藏用例提交、分数与递进提示 | 有实现及题目接口；Piston外部服务和完整执行尚需复验；非 Python fallback 含启发式模拟 | React practice / API | `app/interactive/coding` |
| 数学互动 | 按话题/等级取题、分步反馈、整题规则讲解 | 目前3道内置规则题；不是通用数学推理/题库平台 | React practice / API | `app/interactive/math` |
| 学习看板与行动闭环 | 视频打点、学习时长/连续学习、作业提交、考试作答、正确率、掌握度、学习轮次/下一步行动回执 | 学习/作答链已有实证；本次看板与汇总可读；闭环长期收益未证明 | dashboard / learning / practice | `app/progress; app/domains/learning` |
| 学习路径与推荐 | 个性化路径、下一步学习推荐、难度/兴趣反馈、Neo4j先修路径与环诊断 | 代码及API存在；当前完整路径质量与新学员效果需复验 | React dashboard / API | `app/recommender; app/domains/kg` |
| 知识点思维导图 | 课程图、学科图、个人掌握度着色、前向/后向先修链 | API存在；依赖实际知识点/图谱数据；与视频导图区分 | React / API | `app/mindmap` |
| 社区互助 | 版块/热度/关键词、发帖编辑、帖子详情、评论/回复、点赞、收藏、作者和管理员边界 | 前后端已接线，写流程本轮未重验 | community / community-post | `app/community` |
| 成就与激励 | 徽章解锁进度、积分/等级/流水、日周月总排行榜、合法动作触发徽章 | 本次徽章、积分、排行榜读取成功；不能把手动加分当学习效果 | achievements / dashboard | `app/gamification` |
| 收藏、评价与个人资产 | 课程收藏/取消、已报名课程评价、我的订单/券/班次 | 本次收藏/券/订单可读；评价与取消等写路径需复验 | favorites / me / course-detail | `app/domains/market; app/domains/review` |

## 课程与运营

| 功能 | 当前涉及的能力 | 展示/验收边界 | 入口 | 源码 |
|---|---|---|---|---|
| 课程管理 | 系列→班次→模块→课次 CRUD，资源管理、章节管理、上下架、回收站恢复 | 生产管理员页已使用；不现场演示物理删除 | admin-courses / admin-course-detail | `app/domains/course_admin` |
| 视频上传与来源获取 | 本地分片上传、服务端 ffprobe/字节与播放格式校验、已有视频身份校验、Bilibili链接/分P、字幕优先/ASR | 真实管理员页面已跑通多类来源；任意平台链接不保证获取 | admin-course-detail | `app/domains/course_admin; app/domains/video_learning` |
| 视频生产生命周期 | 创建任务、自动刷新、真实阶段/失败原因、worker/租约、重试、预览、驳回/审核API、自动发布入库 | 已有正式生产闭环；历史人工审核接口保留 | admin-course-detail | `app/domains/video_learning/tasks.py; task_worker.py` |
| 版本与正式发布 | 不可变 Artifact、SHA/lineage、明确重编、重复点击幂等、旧版本保护、READY唯一可见性、ANN前精确scope | 首次 pending 反例与 ready切换已有实证及回归 | admin-course-detail / learning | `app/domains/video_learning/publication.py; app/chat/retrieval_filter.py` |
| 题库与考试管理 | 题库/题目CRUD、五类题型、答案解析编辑/预览、批量导入校验/幂等报告、学生发布/退役、考试组卷/题目快照冻结 | 题库导入和学生发布已有实证；组卷整链待专项复验 | admin-questions / admin-question-detail | `app/domains/question_admin` |
| 用户管理 | 分页搜索、角色分布、账户启停、角色调整、学员资料 | 管理页/API存在；角色/启停写操作需专用对象验收 | admin-users | `app/admin/user_admin` |
| 管理员看板与审计 | 用户指标、课程/题库入口、学习事件分析、交易运营汇总；只读会话/历史审计 | 基础设施读取成功；其他聚合数据需按来源复核 | admin-dashboard / admin-chat-audit | `app/admin; app/domains/analytics` |
| 优惠与免费履约 | 优惠券模板/领券/适用券、无限库存但每人一次；Zero-Pay订单 paid/报名active且不建payment_record；零元携券拒绝 | 已有真实验收与回归 | coupons / course-detail / me | `app/domains/market; app/domains/trade/order` |
| 订单、支付、退款和工单 | 服务端金额/库存/幂等、订单详情/取消；支付轮询/回调闸门/对账；退款申请撤销/HITL审批；工单/申诉/满意度 | 订单查询可读；真实支付渠道未验收；退款/工单有实现和部分过渡路径，不做真实资金演示 | me / refund / React orders,tickets | `app/domains/trade; app/domains/after_sales` |

## 知识与数据

| 功能 | 当前涉及的能力 | 展示/验收边界 | 入口 | 源码 |
|---|---|---|---|---|
| 文档上传/解析 | PDF、MD、TXT、DOCX；SourceAsset身份，MinerU文本PDF/OCR，Document IR页/块来源，解析预览 | 真实PDF/MD已有链路证据；复杂公式/表格/VLM未验收 | admin-rag-upload | `app/knowledge/ir; parser_worker.py` |
| 既有 RAG 入库 | ImportCommand、SourceAsset、IR、chunk准备、BGE-M3、Milvus dense/sparse、tenant/generation/lineage；worker回执/幂等/恢复 | 真实新视频/PDF可召回；保留主RAG，无第二套索引 | admin-rag-upload / learning / chat | `app/knowledge; app/services/source_asset_store.py` |
| 检索与答案证据 | Hybrid、RRF、中文分词、reranker、上下文预算、课程权限/元数据过滤、来源引用；轻量关键词扩展 | 真实RAG已有实证；当前HyDE不是完整LLM假设文档；独立reranker sidecar降级、本地CUDA工作 | chat / admin-rag-upload | `app/chat/retriever.py; app/knowledge/reranker.py` |
| RAG 管理控制台 | collections、检索preset、管理员搜索、审计、任务/分区、文档与graph预览 | 正式页面/API存在；重建/分区删除是管理写能力，本轮不执行 | admin-rag-upload | `app/admin/rag_admin; app/knowledge/routers.py` |
| Neo4j 知识投影 | 正式视频/章节/知识点/canonical chunk，文档MENTIONS/RELATED，版本身份；独立图同步；普通RAG有限邻居扩展 | PDF/视频图谱实证；精确视频Tutor不跨图回填；邻接不是推断先修 | admin-course-detail / admin-rag-upload / Neo4j Browser | `app/domains/video_learning/graph.py; app/knowledge/document_graph.py` |

## Agent 实现

| 功能 | 当前涉及的能力 | 展示/验收边界 | 入口 | 源码 |
|---|---|---|---|---|
| 九节点 LangGraph + 六节点 Harness | route/skill/compact/context_edit/plan/fan_out/merge/reflect/answer，问候短路、反思循环，六个核心节点委托Harness | 真实九节点Trace已验收；不是两条独立流水线，不是每请求九次模型调用 | chat / Jaeger | `app/ai/graph.py; app/ai/harness/sixnode.py` |
| 工具与多通道处理 | 意图分流、知识检索、只读NL2SQL、MCP/计算器/学习工具、并行分支汇总、答案/工具回执校验 | 有接线和部分真实请求；并行任务不是已证明多个自主LLM子Agent | chat / admin-mcp | `app/ai/harness; app/chat/tool_calling.py; app/mcp` |
| 上下文与 Prompt Cache | 稳定前缀、前缀签名/缓存统计、context_edit轻量删冗余、token水位、compaction分预算压缩、最近轮保护 | 代码与观测接口存在；不能无实测宣称缓存命中率或成本收益 | chat / cache-context看板API | `app/ai/prompt_cache.py; context_edit.py; compaction.py` |
| 个人长期记忆 | 偏好/事实提取、异步记忆队列、同步提取、个性化注入、user_memory_event事件HEAD、历史/rewind、Dream整合 | 当前配置启用；曾有远端提取SSL降级，跨会话提取成功与Dream需新实机证据 | chat / memory API | `app/ai/memory` |
| Checkpoint与HITL | Redis thread checkpoint/TTL/HMAC；人工确认pending→confirm/reject→resume；工具分类/角色/风险/超时/熔断；退款审批图 | 有实现与有界测试；高风险写工具、进程崩溃恢复不能由普通Chat通过推断 | chat确认卡 / admin审批/API | `app/ai/checkpoint_redis.py; hitl_gate.py; app/chat/flows; app/domains/trade/refund` |

## 运行与保护

| 功能 | 当前涉及的能力 | 展示/验收边界 | 入口 | 源码 |
|---|---|---|---|---|
| OpenTelemetry / Jaeger | Chat根span、九节点/Harness属性、retrieval/LLM/tool；视频阶段、PDF解析/embedding/load/Neo4j跨worker父子Trace | 真实Chat/PDF/视频Trace已有证据；旧内存Trace可能重启丢失 | admin-infra / Jaeger | `app/observability; app/knowledge; app/domains/video_learning` |
| Prometheus / 日志 / 基础设施面板 | 请求与耗时指标、缓存/上下文联合看板、OTel快照、按Trace观测事件、结构化日志；六存储与Redis队列/锁/熔断/worker心跳 | 管理端快照本次可读；模型/队列具体运行需对应数据证据 | admin-infra / monitoring API | `app/monitoring; app/admin/infra` |
| 权限与运行安全 | JWT/bcrypt、admin/manager/student守卫、报名/对象/tenant scope、SSRF/SQL校验、限流/并发/token预算、错误隔离、签名与幂等 | DEBUG=false及越权边界已有实证；不是整体安全认证 | 各页面 / 服务端 | `app/auth; app/security; app/middleware; app/ai/guard.py` |
| 一键启动 / worker恢复 | 模型/存储readiness、原Redis/Jaeger容器恢复、MinerU/Neo4j入口、文档worker心跳、隐藏启动、日志与有界drain停止 | 原生环境已实测；完整空环境Compose尚未验收 | start-bili-study.cmd / stop-bili-study.cmd | `deploy/local_launcher.py; scripts/manage_workers.py` |

## 展示资源

| 功能 | 当前涉及的能力 | 展示/验收边界 | 入口 | 源码 |
|---|---|---|---|---|
| 25页 standalone 离线预览 | 15学生/通用页 + 10管理页 + 导航；内联原页面样式/JS，接口快照回放 | 离线界面预览；模拟登录/写成功，不含真实视频/在线LLM，不作为业务PASS证据 | showcase/standalone | `showcase/standalone/README.md` |

## 首页展示顺序

1. 一句产品定位：把真实视频/PDF变成带证据的学习资料、练习与课程答疑。
2. 内嵌高层架构：内容获取/解析 → 版本化Artifact/IR → 既有BGE-M3/Milvus → 学习/Tutor，MySQL READY为视频可见性权威；补充Agent、记忆/MCP及OTel。
3. 技术栈职责速览：FastAPI/Python3.11、Next/React、LangGraph/Harness、BGE-M3/Milvus、MinerU/Neo4j、MySQL/Redis/MongoDB/MinIO、OTel/Jaeger。
4. 核心实机画面直接展开：视频学习+导图/字幕、管理员视频生产、PDF解析/图谱、带引用答疑、题目与错题、真实Trace。
5. 25页离线预览作为界面画廊，首批预览直接展开；每页明确快照属性。社区/成就/交易等做次级能力矩阵。
6. 深度技术证据：上下文/cache/记忆/MCP/HITL/Checkpoint、权限失败与恢复。未复验能力保留状态，不填“全部跑通”。

## 242项当前公开接口

以下从运行服务 `/openapi.json` 读取，不以历史任务或注释推断启用状态。

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/health/ready` | Health Ready |
| GET | `/health/warmup` | Health Warmup |
| GET | `/health` | Health Check |
| GET | `/health/detail` | Health Detail |
| GET | `/metrics` | Metrics Endpoint |
| GET | `/api/metrics/cache-context-dashboard` | Cache Context Dashboard |
| GET | `/api/metrics/otel` | Otel Metrics Snapshot |
| GET | `/api/metrics/trace/{trace_id}` | Trace Events |
| POST | `/api/auth/register` | 用户注册 |
| POST | `/api/auth/login` | 用户登录 |
| POST | `/api/auth/refresh` | 刷新访问令牌 |
| GET | `/api/auth/me` | 获取当前登录用户信息 |
| POST | `/api/admin/video-knowledge/videos/{video_id}/graph` | Synchronize Graph |
| POST | `/api/admin/video-knowledge/tasks` | 从已有原视频或真实 Bilibili 分 P 创建课次视频知识任务 |
| GET | `/api/admin/video-knowledge/tasks` | 查看视频知识生产队列 |
| GET | `/api/admin/video-knowledge/tasks/{task_id}` | 查看当前阶段、失败原因、重试或审核状态 |
| GET | `/api/admin/video-knowledge/tasks/{task_id}/preview` | 审核课程笔记、章节、字幕和思维导图 |
| POST | `/api/admin/video-knowledge/tasks/{task_id}/retry` | 复用已完成阶段并重试失败任务 |
| POST | `/api/admin/video-knowledge/tasks/{task_id}/reject` | 拒绝待审核资料，保留原视频并按反馈重新编译 |
| POST | `/api/admin/video-knowledge/tasks/{task_id}/approve` | 审核通过并发布，系统自动进入现有 EDU RAG |
| POST | `/api/knowledge/upload` | Upload Knowledge |
| POST | `/api/knowledge/admin/upload` | Admin Upload Knowledge |
| GET | `/api/knowledge/tasks` | List Knowledge Tasks |
| GET | `/api/knowledge/status/{task_id}` | Get Task Status |
| GET | `/api/knowledge/partitions` | List Partitions |
| DELETE | `/api/knowledge/partitions/{tenant_id}` | Delete Partition |
| GET | `/api/knowledge/admin/document-capabilities` | Capabilities |
| GET | `/api/knowledge/admin/document-inspection/{task_id}` | Document Inspection |
| GET | `/api/series` | 系列列表（学科分类/交付模式/关键词/价格区间/排序/分页） |
| GET | `/api/series/{series_id}` | 系列详情（全列 + 价格区间 + 分类 + 班次数） |
| GET | `/api/series/{series_id}/cohorts` | 系列下全部在售班次 |
| GET | `/api/cohorts/{cohort_id}` | 班次详情（含模块列表） |
| GET | `/api/cohorts/{cohort_id}/modules` | 班次模块列表（每模块含课次与视频） |
| GET | `/api/courses/{series_id}/reviews` | 某系列评价列表（分页） |
| POST | `/api/courses/{series_id}/reviews` | 给已报名该系列提交评价 |
| GET | `/api/admin/reviews` | 管理端评价列表（分页 + series 过滤） |
| DELETE | `/api/admin/reviews/{review_id}` | 软删评价 |
| GET | `/api/users/me/profile` | 获取当前用户的画像 |
| PUT | `/api/users/me/profile` | 部分更新当前用户的画像 |
| GET | `/api/users/me` | 兼容端点：GET /api/users/me（返回 auth info + 画像合并视图，task114 新契约 snake_case） |
| GET | `/api/users/me/student-profile` | 获取当前用户的学员档案 |
| GET | `/api/users/me/learning-summary` | 获取当前用户的学习汇总数据 |
| POST | `/api/chat/sessions` | Sessions Create |
| GET | `/api/chat/sessions` | Sessions List |
| GET | `/api/chat/sessions/{session_id}/history` | Sessions History |
| DELETE | `/api/chat/sessions/{session_id}` | Sessions Delete |
| POST | `/api/chat/search` | Search Endpoint |
| POST | `/api/chat` | Chat Non Stream |
| POST | `/api/chat/stream` | Chat Stream Sse |
| POST | `/api/chat/resume` | Chat Resume |
| GET | `/api/admin/rag/collections` | Collections List |
| POST | `/api/admin/rag/collections/rebuild` | Collections Rebuild |
| GET | `/api/admin/rag/presets` | Presets List |
| POST | `/api/admin/rag/presets` | Presets Create |
| GET | `/api/admin/rag/audit-log` | Audit Log List |
| POST | `/api/admin/rag/search` | Admin Search Endpoint |
| GET | `/api/admin/chat-audit/sessions` | 管理端·会话审计列表（只读·分页·user_id 过滤） |
| GET | `/api/admin/chat-audit/sessions/{session_id}/history` | 管理端·会话审计历史（只读，任意学员会话） |
| GET | `/api/admin/infra/snapshot` | 基础设施实时快照（Redis 四件套 + Mongo + learning_event，只读） |
| GET | `/api/kg/course/{course_id}/path` | 课程内学习路径（先修图最短路 + 环检测） |
| GET | `/api/kg/chapter/{chapter_code}/upstream` | 章节前置知识面（先修知识点 + 所属章节） |
| GET | `/api/kg/chapter/{chapter_code}/downstream` | 章节后续知识面（依赖本章的知识点 + 所属章节） |
| GET | `/api/admin/courses/series` | 管理端·系列列表（筛选+分页） |
| POST | `/api/admin/courses/series` | 管理端·创建系列 |
| GET | `/api/admin/courses/series/{series_id}` | 管理端·系列详情 |
| PATCH | `/api/admin/courses/series/{series_id}` | 管理端·更新系列 |
| DELETE | `/api/admin/courses/series/{series_id}` | 管理端·删除系列（软删下架 / ?hard=true 真删） |
| GET | `/api/admin/courses/series/{series_id}/cohorts` | 管理端·班次列表（按系列） |
| GET | `/api/admin/courses/cohorts/{cohort_id}` | 管理端·班次详情 |
| PATCH | `/api/admin/courses/cohorts/{cohort_id}` | 管理端·更新班次 |
| DELETE | `/api/admin/courses/cohorts/{cohort_id}` | 管理端·软删班次（yn=0；含模块且非 force→40908，force 仅 ADMIN 级联删零课次模块） |
| POST | `/api/admin/courses/cohorts` | 管理端·创建班次 |
| GET | `/api/admin/courses/cohorts/{cohort_id}/modules` | 管理端·模块列表（按班次） |
| GET | `/api/admin/courses/modules/{module_id}` | 管理端·模块详情 |
| PATCH | `/api/admin/courses/modules/{module_id}` | 管理端·更新模块 |
| DELETE | `/api/admin/courses/modules/{module_id}` | 管理端·软删模块（yn=0） |
| POST | `/api/admin/courses/modules` | 管理端·创建模块 |
| GET | `/api/admin/courses/cohorts/{cohort_id}/sessions` | 管理端·课次列表（按班次，task12-fix 批判②） |
| GET | `/api/admin/courses/modules/{module_id}/sessions` | 管理端·课次列表（按模块） |
| GET | `/api/admin/courses/sessions/{session_id}` | 管理端·课次详情 |
| PATCH | `/api/admin/courses/sessions/{session_id}` | 管理端·更新课次 |
| DELETE | `/api/admin/courses/sessions/{session_id}` | 管理端·删除课次（物理删除，不可恢复；被引用则 40908） |
| POST | `/api/admin/courses/sessions` | 管理端·创建课次 |
| GET | `/api/admin/courses/sessions/{session_id}/assets` | 管理端·课次资源列表（含视频信息，供视频面板） |
| GET | `/api/admin/courses/videos/{video_id}/chapters` | 管理端·视频章节列表（按视频） |
| GET | `/api/admin/courses/chapters/{chapter_id}` | 管理端·视频章节详情 |
| PATCH | `/api/admin/courses/chapters/{chapter_id}` | 管理端·更新视频章节 |
| DELETE | `/api/admin/courses/chapters/{chapter_id}` | 管理端·物理删除视频章节 |
| POST | `/api/admin/courses/chapters` | 管理端·创建视频章节 |
| POST | `/api/admin/courses/videos/init-chunked` | 管理端·分片上传 init |
| PUT | `/api/admin/courses/videos/upload-chunk/{upload_id}/{chunk_index}` | 管理端·分片上传单分片 PUT（octet-stream） |
| POST | `/api/admin/courses/videos/finalize-chunked` | 管理端·分片上传 finalize（合并落盘+建 asset/video） |
| POST | `/api/admin/courses/videos/bind-session` | 管理端·绑定视频到课次（修正归属/排序） |
| GET | `/api/admin/courses/videos/{video_id}/transcode-status` | 管理端·转码状态轮询 |
| POST | `/api/admin/courses/series/{series_id}/restore` | 管理端·从回收站恢复已下架系列（C5） |
| GET | `/api/admin/questions/types` | 题型维表列表（只读） |
| GET | `/api/admin/questions/banks` | 题库列表（分页 + 关键词检索） |
| POST | `/api/admin/questions/banks` | 创建题库 |
| GET | `/api/admin/questions/banks/{bank_id}` | 题库详情 |
| PATCH | `/api/admin/questions/banks/{bank_id}` | 更新题库 |
| DELETE | `/api/admin/questions/banks/{bank_id}` | 删除题库（软删 yn=0；非空且非 force→40924，force→级联软删题目，force 仅 ADMIN） |
| POST | `/api/admin/questions/banks/{bank_id}/publish-practice` | 发布题库为独立练习，保留已有课程题权限 |
| GET | `/api/admin/questions/banks/{bank_id}/questions` | 按题库查题目列表（分页 + 题型/关键词检索，LIKE 替代标签） |
| GET | `/api/admin/questions/questions/{question_id}` | 题目详情 |
| PATCH | `/api/admin/questions/questions/{question_id}` | 更新题目 |
| DELETE | `/api/admin/questions/questions/{question_id}` | 删除题目（软删 yn=0） |
| POST | `/api/admin/questions/questions` | 创建题目 |
| POST | `/api/admin/questions/questions/{question_id}/publish` | 校验课程/KP/授权并发布正式 Quiz 题 |
| POST | `/api/admin/questions/questions/{question_id}/retire` | 退役正式 Quiz 题以允许修订 |
| POST | `/api/admin/questions/import-preview` | 批量导入预览（校验 + 报告失败行，不落库） |
| POST | `/api/admin/questions/import-execute` | 批量导入执行（幂等：重复 question_code 跳过但返回原记录信息） |
| GET | `/api/admin/questions/exams` | 考试列表（按 session_id 过滤） |
| POST | `/api/admin/questions/exams` | 创建考试 |
| GET | `/api/admin/questions/exams/{exam_id}` | 考试详情（含快照题目列表） |
| PATCH | `/api/admin/questions/exams/{exam_id}` | 更新考试信息（快照题目不受影响） |
| POST | `/api/admin/questions/exams/{exam_id}/publish` | 发布考试 = 快照题目到 session_exam_question_rel（冻结后改原题不影响考试判分） |
| GET | `/api/admin/users` | Admin List Users |
| POST | `/api/admin/users/{user_id}/role` | Admin Change Role |
| POST | `/api/admin/users/{user_id}/status` | Admin Change Status |
| GET | `/api/admin/users/dashboard/metrics` | Admin Dashboard Metrics |
| POST | `/api/progress/video/sessions` | 创建当前用户的视频播放会话 |
| POST | `/api/progress/video/tick-batch` | 批量视频播放打点 |
| POST | `/api/progress/homework/submit` | 提交课次作业 |
| POST | `/api/progress/exam/submit` | 提交考试答卷 |
| GET | `/api/progress/dashboard` | 个人学习看板 |
| GET | `/api/progress/courses` | 我的课程进度 |
| GET | `/api/recommend/path` | 生成个性化学习路径（完整 6-8 周路径） |
| GET | `/api/recommend/next` | 下一步推荐（首页/学习页卡片式轻量推荐） |
| POST | `/api/recommend/feedback` | 推荐反馈：有帮助/不感兴趣/已学过/太难 |
| GET | `/api/mindmap/course/{series_id}` | 课程系列思维导图（按 series.id 出图） |
| GET | `/api/mindmap/subject/{subject_code}` | 学科全量思维导图（english/programming/math） |
| GET | `/api/mindmap/me/{series_id}` | 「我的」学习图谱：在 /course/{series_id} 基础上叠加个人掌握度颜色 |
| GET | `/api/mindmap/prerequisite` | 某知识点的先修链 forward（全链）/backward（仅前置） |
| GET | `/api/interactive/quiz/banks` | 当前学生可练习的正式题库 |
| GET | `/api/interactive/quiz/next` | 下一道互动习题（优先到期错题，否则按薄弱知识点/学科/题型抽） |
| POST | `/api/interactive/quiz/submit` | 提交作答：即时判分+解析，并写入错题本 |
| GET | `/api/interactive/quiz/wrong-book` | 错题本列表：分页 + status 过滤 + 到期复习过滤 |
| GET | `/api/interactive/quiz/wrong-next` | 错题复习模式：取一道到期错题（=复习模式的「下一道」） |
| GET | `/api/interactive/quiz/types` | 支持题型枚举清单（给前端 Tab/筛选用） |
| GET | `/api/interactive/quiz/question/{custom_code}` | 按 custom_code 取题目详情（打靶/自测用） |
| GET | `/api/interactive/quiz/question-id/{question_id}` | 按正式题目 ID 精确读取（错题重做） |
| GET | `/api/vocab/daily` | 今日单词计划：到期复习 + 新词配额 |
| POST | `/api/vocab/recall` | SM-2 记忆质量 quality 上报（0-5） |
| GET | `/api/vocab/progress` | 单词闯关进度：等级掌握数 / 打卡 / 30 天正确率 |
| GET | `/api/coding/challenges` | 编程挑战题列表：按 lang / level 过滤分页 |
| GET | `/api/coding/challenges/{code}` | 单题详情（含 sample 非隐藏用例） |
| POST | `/api/coding/run` | 运行（只跑 sample 用例，不记录/不影响最终分） |
| POST | `/api/coding/submit` | 提交（含隐藏用例，计分） |
| POST | `/api/coding/hint` | 递进式 Hint（1..N step，到顶后 next_step_available=false） |
| GET | `/api/math/practice` | 数学互动练习题列表（可按 topic / level 过滤） |
| POST | `/api/math/step-check` | 步骤校验：分步给反馈（类似 Photomath） |
| POST | `/api/math/explain` | 整题讲解：本地规则优先（打靶）；生产可由 LLM/RAG 增强 |
| GET | `/api/community/posts` | 社区帖子分页列表（按版块/作者/关键词/热度） |
| POST | `/api/community/posts` | 发帖 |
| GET | `/api/community/posts/{post_id}` | 帖子详情（浏览量自动+1） |
| PATCH | `/api/community/posts/{post_id}` | 改帖（作者本人；置顶/锁帖管理员） |
| POST | `/api/community/posts/{post_id}/like` | 点赞/取消点赞 帖子 |
| POST | `/api/community/posts/{post_id}/favorite` | 收藏/取消收藏 帖子 |
| GET | `/api/community/posts/{post_id}/comments` | 评论列表 |
| POST | `/api/community/posts/{post_id}/comments` | 回帖（一楼或回复） |
| POST | `/api/community/comments/{comment_id}/like` | 点赞评论 |
| GET | `/api/gamification/me/badges` | 徽章清单（含个人解锁进度） |
| GET | `/api/gamification/me/points` | 我的积分 + 等级 + 近期流水 |
| POST | `/api/gamification/me/award` | 手动加积分（打靶用，真实业务走系统触发） |
| GET | `/api/gamification/rankings` | 排行榜：日/周/月/总 × 积分/时长/徽章 |
| POST | `/api/gamification/me/check-badges` | 主动触发徽章检测（返回本次新解锁徽章列表） |
| GET | `/api/coupons/templates` | 可领券模板全量列表 |
| GET | `/api/coupons` | 我的券分页 / 系列适用券模板（series_id） |
| POST | `/api/trade/coupon/receive` | 领券（幂等中间件前缀内，防超发） |
| GET | `/api/favorites` | 我的收藏分页 |
| POST | `/api/favorites` | 新增收藏（服务端幂等） |
| DELETE | `/api/favorites/{series_id}` | 取消收藏（软删幂等） |
| POST | `/api/trade/order` | 下单（幂等，金额服务端重算，防超卖） |
| GET | `/api/trade/orders` | 订单分页（状态过滤 + 分页 + refundable） |
| GET | `/api/trade/order/{order_no}` | 订单详情（items + payments 嵌套） |
| POST | `/api/trade/order/{order_no}/cancel` | 取消订单（仅 pending） |
| POST | `/api/trade/payment/{order_no}` | 发起支付 |
| GET | `/api/trade/payment/{payment_no}` | 支付详情/轮询 |
| POST | `/api/trade/payment/{payment_no}/mock-notify` | mock 回调（仅 mock 渠道） |
| POST | `/payment-notifications/mock` | mock 回调（body {payment_no, third_party_trade_no}，仅 mock 渠道） |
| POST | `/payment-notifications/channel` | 真实渠道回调（alipay/wechat_pay：验商户+验签+验金额闸门） |
| GET | `/api/trade/payments` | 支付分页查询 |
| POST | `/api/trade/payment/{payment_no}/cancel` | 取消支付 |
| POST | `/api/trade/payment/{payment_no}/retry` | 重试支付 |
| GET | `/api/trade/payments/reconcile` | 对账报告 |
| POST | `/api/trade/payments/reconcile` | 对账任务（无重复入账报告） |
| POST | `/api/refunds` | 申请退款（金额服务端强制校验） |
| GET | `/api/refunds` | 我的退款（倒序） |
| POST | `/api/refunds/{refund_id}/cancel` | 撤销退款（仅 pending） |
| GET | `/api/admin/refunds` | 管理端·退款列表（过渡） |
| POST | `/api/admin/refunds/{refund_id}/approve` | 审批通过（HITL interrupt-resume，原子退款 GWT②） |
| POST | `/api/admin/refunds/{refund_id}/reject` | 审批拒绝（HITL，含 remark 拒绝理由 GWT③） |
| GET | `/api/admin/trade/overview` | 交易运营聚合概览（热门榜/营收/订单概况） |
| GET | `/api/enrollments/me/cohorts` | 我的班次（状态过滤 + 进度聚合） |
| GET | `/api/enrollments/me/cohorts/{cohort_id}` | 报名详情（状态 + 进度） |
| GET | `/api/enrollments/me/cohorts/{cohort_id}/progress` | 进度快照（模块/课次明细） |
| GET | `/api/enrollments/me/cohorts/{cohort_id}/status` | 报名状态查询 |
| GET | `/api/study/sessions/{session_id}/video-knowledge` | 本课视频的章节、笔记、字幕与思维导图 |
| POST | `/api/study/loops` | 开始可复核的一门课学习轮次 |
| GET | `/api/study/loops/{loop_id}` | 复核学习轮次与已提交的下一步行动 |
| POST | `/api/study/contexts` | 创建服务端校验的本课学习上下文 |
| GET | `/api/study/contexts/{context_id}` | 当前答疑课程与正式资料状态 |
| GET | `/api/study/courses/{series_id}/access` | 班次访问鉴权 |
| GET | `/api/study/courses/{series_id}/outline` | 学习大纲 |
| POST | `/api/study/sessions/{session_id}/complete` | 课次完成态 |
| GET | `/api/study/sessions/{session_id}` | 课次详情（资源过滤 + transcode） |
| GET | `/api/study/sessions/{session_id}/pilot-material` | 隔离 Pilot 冻结课文 |
| POST | `/api/trade/after_sales/ticket` | 创建工单（含 appeal 人工申诉） |
| GET | `/api/trade/after_sales/tickets` | 我的工单（过滤 + 分页） |
| GET | `/api/trade/after_sales/ticket/{ticket_id}` | 工单详情（越权 404） |
| POST | `/api/trade/after_sales/ticket/{ticket_id}/satisfaction` | 满意度评价（1-5 星，幂等） |
| GET | `/api/analytics/learning-events/summary` | 学习事件聚合（管理端看板数据源；student 仅可查自己） |
| GET | `/api/analytics/learning-events/stream-stats` | 学习事件流运行态（队列/熔断/计数；仅 admin/manager） |
| POST | `/api/mcp/servers` | P8-1 手动注册 MCP Server（stdio / SSE / HTTP） |
| GET | `/api/mcp/servers` | P8-2 MCP Server 列表（分页+transport/enabled/关键词过滤） |
| GET | `/api/mcp/servers/{server_id}` | P8-3 Server 详情（含敏感字段：run_command/args/env/http_headers） |
| PATCH | `/api/mcp/servers/{server_id}` | P8-4 更新 Server 部分字段（局部修改） |
| DELETE | `/api/mcp/servers/{server_id}` | P8-5 注销 Server（软删 yn=0；关联工具同步 yn=0） |
| POST | `/api/mcp/servers/{server_id}/health` | P8-6 立即健康检查（stdio：initialize+ping；SSE：GET base_url 200） |
| POST | `/api/mcp/servers/{server_id}/discover` | P8-7 initialize+tools/list 自动导入所有工具到 mcp_tool（INSERT IGNORE 幂等） |
| POST | `/api/mcp/servers/import-url` | P8-8 一键导入 MCP Server（data://test-stdio 打靶专用或 https:// 实际 SSE URL） |
| GET | `/api/mcp/servers/{server_id}/tools` | P8-9 按 server 查看工具列表（含分页+按名字/描述关键词过滤） |
| GET | `/api/mcp/tools` | P8-10 全局工具列表（跨 server；可按 server_code/category/关键词搜索） |
| POST | `/api/mcp/description-review` | P8-22 立即对全部（或指定 server）MCP 工具做描述体检（规则打分 + <70 分 FAST 重写），供前端『描述体检』按钮调用 |
| GET | `/api/mcp/description-review-log` | P8-23 描述体检审计日志（分页，可按 server_id/tool_id 过滤，时间倒序） |
| POST | `/api/mcp/tools/test` | P8-11 测试调用工具（tool_id 或 server_id+tool_name，结果含 content_text & latency_ms） |
| GET | `/api/mcp/call-log` | P8-12 工具调用审计日志（分页，支持按 server_id/tool_name/status/user_id/created_from/created_to 过滤） |
| GET | `/api/mcp/call-log/{log_id}` | P8-12a【调试】单条 MCP 调用日志详情（含完整 args / result / error_info JSON） |
| GET | `/api/mcp/servers/{server_id}/discover-live` | P8-13【调试】直连 Server 取 tools/list 实时快照（不落库，不写 mcp_tool） |
| POST | `/api/mcp/servers/{server_id}/raw-rpc` | P8-14【调试】管理员直连 Server 发任意 JSON-RPC（initialize/tools/list/ping/…） |
| POST | `/api/mcp/health-scan` | P8-15【调试】同步批量健康扫描（Deprecated：30 天兼容窗，请迁移 POST /api/mcp/health-scan-async；removal 预计 2026-10-12） |
| POST | `/api/mcp/health-scan-async` | B1【调试】异步批量健康扫描：202 受理即返 job_id；同参重复 POST 幂等复用在跑 job |
| GET | `/api/mcp/health-scan/{job_id}` | B1【调试】查询异步健康扫描 job：running/done + result；未知/过期 job → 404 code=40450 |
| GET | `/api/mcp/sessions` | P8-18【调试】列出当前进程内所有活动会话（含 pid/call_count/idle TTL） |
| POST | `/api/mcp/sessions` | P8-17【调试】创建 stdio 长连接会话（initialize 成功后入池，空闲 GC TTL 可配） |
| GET | `/api/mcp/sessions/{session_id}` | P8-19【调试】单个会话快照（不存在 404） |
| DELETE | `/api/mcp/sessions/{session_id}` | P8-21【调试】关闭会话（terminate 子进程 + 移除池） |
| POST | `/api/mcp/sessions/{session_id}/touch` | P8-20【调试】保活：重置 last_used_ms（避免 idle GC 回收） |
| POST | `/api/memory/rewind` | Rewind Memory |
| GET | `/api/memory/history/{entity_id}` | Memory History |
| POST | `/api/memory/admin/dream/run` | Admin Dream Run |
| GET | `/` | Root |

## 技术栈补充与角色

以下区分当前主链和工程中的依赖，不把依赖声明当作功能验收。

| 层 | 当前实现 |
|---|---|
| 后端/API | Python 3.11、FastAPI、Uvicorn、Pydantic、sse-starlette、SQLAlchemy/asyncmy、Alembic |
| 前端 | Next.js 16 / React 19、静态 HTML/EAPI；TypeScript、Tailwind、React Query、Zustand、Refine 等在 React 工程内 |
| 模型与检索 | LangGraph、LangChain Core/OpenAI-compatible、BGE-M3、FlagEmbedding、PyTorch CPU/CUDA、Milvus、RRF、reranker、jieba |
| 视频 | yt-dlp、ffmpeg、ffprobe、faster-whisper ASR；字幕优先，原媒体与派生资产分离 |
| 文档 | 独立 MinerU runtime、Document IR；python-docx/pdfplumber 等兼容解析组件 |
| 存储 | MySQL业务/正式发布；Redis上下文/任务协调；MinIO资产；Milvus向量；Neo4j关联图；MongoDB事件 |
| 观测 | OpenTelemetry SDK + OTLP HTTP、Jaeger、Prometheus-client、结构化日志 |
| 验证 | pytest/pytest-asyncio、Vitest/Testing Library/jsdom、Playwright、真实浏览器与HTTP、GitHub Actions |

