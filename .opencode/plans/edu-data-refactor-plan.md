# EduAgent 以 edu-data 为权威的数据模型重构 — PRD 与修改规划

| 项 | 内容 |
|----|------|
| 文档版本 | v2.0（含 RAG 上传入口新增需求） |
| 状态 | 待评审 |
| 数据权威 | `E:\stu\project\stu\edu-data`（sql/edu.sql 66 表 + seeds + generate 脚本） |
| 已确认决策 | ① pf_bagu_kb 保留；② 题目标签删除后重构；③ 响应壳全模块统一；④ 支持分夜跑批；⑤ 前端全域建页面（排除购物车/咨询，咨询改人工申诉），每页 HTML 原型审核流 |

---

## 1. 背景与目标

### 1.1 背景

当前 EduAgent 系统存在三套并存且互不相通的数据模型：

1. **edu-data 权威模型**（66 张表）：系列→班次→模块→课次四级课程结构、题库/题目两表（含解析 analysis_text）、机构(institution)多租户、交付模式(delivery_mode)、完整交易链（订单/支付/退款）、营销链（优惠券/曝光/收藏）、工单售后。数据仅导入了 smoke 档（36/219 系列）。
2. **EduAgent 自建课程体系**（curriculum_* 4 表）：模块挂系列（series_id），无机构/交付模式维度，与 edu-data 的 series_* 表零关联、零代码互通。
3. **三套题库**：admin_question_bank（管理端）、admin_question（互动答题）、question（edu-data 权威），字段互不兼容。

前端同样存在三套命名（series_title/series_name/seriesName 并存）、12 个业务域中 7 个无页面、课程是"系列→模块→课次"两级而 edu-data 是"系列→班次→模块→课次"四级。

### 1.2 目标

1. 数据库业务表结构**以 edu.sql 66 张表为唯一权威**重建；
2. 数据按 **full 档**重灌（219 系列 / 657 模块 / 73 题库 / 1752 题 / 10万用户 / 8万订单），Redis 等缓存保障性能；
3. 后端课程/题库/学习/交易/售后模块按 edu-data 模型改造或新建；
4. 前端全部业务域建页面（排除购物车、咨询；咨询改为**人工申诉**），每页走 **HTML 参考文件→用户审核→用户给图→React 实现** 流程；
5. **管理端 RAG 新增通用文件上传入口**（后端接口已有、前端缺失）；
6. Milvus `edu_knowledge` 与 Neo4j 旧数据清除后用课程+题目重建；`pf_bagu_kb` 保留。

---

## 2. 现状问题（证据摘要）

| # | 问题 | 证据 |
|---|------|------|
| P1 | 课程数据只有 36/219 系列（smoke 档） | DB series 432 行 = 36 base × 2 交付模式 × 6 机构 |
| P2 | 后端课程读写完全绕开 edu-data 表 | app/ 代码零引用 series/series_cohort*；全走 curriculum_* |
| P3 | 模块挂错父级 | edu.sql 模块挂 cohort_id（series_cohort_course）；后端 curriculum_module 挂 series_id |
| P4 | 交付模式未建模 | 后端代码 grep delivery_mode 零命中 |
| P5 | 题库三套并存互不相通 | admin_question_bank / admin_question / question 字段完全不一致 |
| P6 | 前端 7 个业务域无页面 | favorites/consultations/coupons/cart/orders/payments/tickets 前端零覆盖 |
| P7 | 前端三套字段命名并存 | series_title/series_name/seriesName 三轨 + 别名兜底代码 curriculum.ts:184 |
| P8 | 响应壳不统一 | 错误统一 {code,message,detail}；成功有裸对象也有 {code:0,message,data} 混用 |
| P9 | RAG 管理端无上传入口 | 后端 POST /api/knowledge/admin/upload 已存在（upload.py:263），前端 /admin/rag 无上传 UI，admin/rag.ts 无 upload 封装 |
| P10 | 遗留 bug | app/users/router.py:83 `UPDATE users`（表不存在且异常被吞） |

---

## 3. 范围与原则

### 3.1 范围内
- edu.sql 66 张业务表结构重建 + 数据 full 档重灌
- 后端课程/题库/学习/交易/售后/报名模块改造与新建 + 响应壳统一 + Redis 缓存
- 前端 12 域页面（排除购物车/咨询）+ RAG 上传入口 + HTML 原型审核流
- Milvus edu_knowledge + Neo4j 清除重建

### 3.2 范围外
- `pf_bagu_kb`（保留不动）
- 购物车、咨询域（不建页面不建接口；consultation_record 表保留结构但不接入）
- EduAgent 平台功能（auth JWT/chat/community/gamification/mcp/rag_admin 核心）业务逻辑不改，仅响应壳适配
- 支付渠道真实对接（用模拟支付回调 /payment-notifications/mock）

### 3.3 原则
1. 字段/表结构一律 edu.sql 为准；前端字段统一 snake_case
2. 唯一键/外键严格按 edu.sql；机构分片（institution_id）全链路贯通
3. 认证维持 JWT（auth 体系不动）；业务数据模型才以 edu-data 为准
4. 写操作失败必须上抛（R-7 红线沿用）；管理端 RBAC 沿用
5. 每个前端页面必须过 HTML 原型审核后才能写 React

---

## 4. 功能需求

### 4.1 数据库（FR-DB）

**FR-DB-01** 按 edu.sql 原样重建 66 张业务表（字段/类型/唯一键/外键/注释一致）。

**FR-DB-02** 废弃删除 13 张平行旧表：

| 删除表 | 替代者 |
|--------|--------|
| curriculum_series / curriculum_cohort / curriculum_module / curriculum_session | series / series_cohort / series_cohort_course / series_cohort_session |
| admin_question_bank / admin_question | question_bank / `question` |
| admin_exam_paper / admin_exam_paper_item | session_exam / session_exam_question_rel |
| admin_question_tag / admin_question_to_tag | 删除后重构：标签能力改为"题目知识点文本检索"（基于 stem+analysis_text 全文检索），不再维护标签表 |
| admin_course_video_asset | session_asset / session_video / session_video_chapter |

**FR-DB-03** sys_user 合并：edu.sql 原列 + 扩展列 account(唯一)/username/status；sys_user_auth 不动。

**FR-DB-04** 恢复 edu.sql 原外键语义：session_homework_submission.homework_id→session_homework、session_exam_submission.exam_id→session_exam、session_video_play_event.play_session_id→session_video_play。

**FR-DB-05** 补充查询索引（§6.1 清单）。

**FR-DB-06** 保留平台扩展表 27 张（清单见 §6.1）。

### 4.2 后端 API（FR-API）

**FR-API-01** 响应壳全模块统一：成功 `{code:0, message:"ok", data}`；失败 `{code:<字符串错误码>, message, data:null}`。

**FR-API-02** 课程域（改造）：
- C 端：GET `/api/series`（学科/分类/交付模式/关键词/分页）、GET `/api/series/{id}`、GET `/api/series/{id}/cohorts`、GET `/api/cohorts/{id}`（含模块）、GET `/api/cohorts/{id}/modules`（含课次）
- 管理端 `/api/admin/courses`：series/cohorts/modules/sessions 四级 CRUD + session_asset/session_video/session_video_chapter 视频三表

**FR-API-03** 题库域（改造）：question_bank CRUD、question CRUD+批量导入（1752 题）、analysis_text（解析）字段贯通；组卷=session_exam+session_exam_question_rel；quiz 出题改从 `question` 表。

**FR-API-04** 交易域（新建）：coupons（3 端点）、favorites（3 端点）、orders（5 端点）、payments（8 端点，含 mock 支付回调）、refund-requests。

**FR-API-05** 报名与学习域（新建）：enrollments（/me/cohorts 系列 4 端点）、study（sessions/videos/chapters/video-history/homeworks/exams 10 端点）；progress 提交改写 edu-data 提交表。

**FR-API-06** 售后域（新建）：service-tickets（5 端点）+ 工单类型新增 `appeal`（人工申诉）；咨询域不实现接口。

**FR-API-07** 改造：curriculum 模块废弃（路由迁移到 series）、mindmap/recommender 数据源切 series 体系、users 修复 UPDATE users bug 并新增 /me/student-profile、/me/learning-summary。

**FR-API-08** Redis 缓存：系列/题库/课程树热点缓存、排行榜 ZSET、防穿透互斥锁（§6.7）。

### 4.3 前端页面（FR-FE）

**FR-FE-01** 重构 12 页（课程中心/搜索/详情/学习页/我的课程/复习中心/个人中心/管理端课程×2/管理端题库×2/管理端用户），字段统一 snake_case，删除别名兜底。

**FR-FE-02** 新建 6 页：优惠券中心 /coupons、我的订单 /orders、支付 /orders/[orderId]/pay、退款 /refunds、售后工单+人工申诉 /tickets、我的收藏 /favorites。

**FR-FE-03** 课程详情改为四级展示：系列→班次（价格/人数/日期/报名按钮）→模块→课次；新增领券/收藏入口。

**FR-FE-04** 管理端题库：题库+题目两级管理、批量导入、题目解析编辑（analysis_text）。

**FR-FE-05** HTML 原型审核流：每页先产出 `test-reports/fe-html/{页面}.html` 静态参考文件 → 用户审核并给出设计图 → 修改 HTML 至通过 → 再写 React。页面顺序：课程中心→课程详情→我的班次→优惠券→订单/支付→退款→收藏→售后工单/申诉→管理端课程→管理端题库→RAG 上传→其余。

### 4.4 管理端 RAG 通用文件上传入口（FR-RAG，新增）

**FR-RAG-01** 检测结论：后端已有 `POST /api/knowledge/admin/upload`（RBAC admin/manager、_default 分区、≤50 文件、单文件≤200MB、.md/.txt/.markdown/.pdf/.docx、parse→chunk→embed→load(Milvus)→graph_build(Neo4j) 管道）+ `GET /api/knowledge/status/{task_id}` + 分区管理端点；**前端 /admin/rag 无上传入口、无 API 封装** → 本次补齐前端入口并增强后端。

**FR-RAG-02** 前端 /admin/rag 新增"知识文件上传"区块：
- 多选文件（拖拽/点击），格式与大小校验，上传进度条（axios onUploadProgress）
- 任务列表 + 状态轮询（pending→running→done/failed，chunks 进度展示）
- 分区管理面板（列表/删除，`_default` 保护提示）
- 上传完成后的集合行数自动刷新

**FR-RAG-03** 后端增强：
- 新增 `GET /api/knowledge/tasks`（admin，任务列表倒序，含状态/进度/文件数/错误）
- 任务持久化：task_store 内存存储 → Redis（key `edu:knowledge:task:{id}`，TTL 24h），重启不丢
- 上传原文件留存 MinIO `edu-upload` bucket（当前临时落盘即删）；导入完成后源文件保留供审计/重新导入，30 天过期策略

**FR-RAG-04** 上传导入的数据进 Milvus `_default` 分区（全用户可见）+ 同步构建 Neo4j 图谱节点。

### 4.5 Milvus / Neo4j（FR-KB）

**FR-KB-01** 清除：drop+重建 `edu_knowledge` 集合（保留 loader.py 的 id/chunk_id/content/content_type/source_file/dense_vec 1024/sparse_vec/tenant_id/visibility schema 与索引）；`pf_bagu_kb` 保留。Neo4j `MATCH (n) DETACH DELETE n` 清空。

**FR-KB-02** 重建数据源：课程（219 系列 name+description+分类+目标人群 + 657 模块 name+keywords）+ 题目（1752 题 stem+analysis_text）→ 切片（200 chunks/批）→ 向量化（硅基流动 bge-m3）→ 入 Milvus（公共知识进 `_default`，按机构 visibility 分区）。

**FR-KB-03** Neo4j 图谱重建：节点 Series/Module/Session/Question/KnowledgePoint（从题目解析提取），边 CONTAINS/BELONGS_TO/RELATED。

**FR-KB-04** 重建校验：collection health（行数/分区/索引加载）、图谱节点关系计数报告。

### 4.6 性能（FR-PERF，full 档 10万用户/8万订单）

**FR-PERF-01** 热点缓存：series 列表/详情/树、question_bank/question、dashboard 聚合，TTL 60~600s，写后失效（DEL）。
**FR-PERF-02** 排行榜 ZSET；**FR-PERF-03** 防穿透（空结果 30s 缓存 + SETNX 互斥重建）；**FR-PERF-04** 列表强制分页（page_size≤100）；**FR-PERF-05** 保留读写分离与慢查询监控；**FR-PERF-06** 生成侧 batch_size=5000 批量插入。

---

## 5. 非功能需求

- 安全：管理端全部 require_role(ADMIN)；上传 RBAC admin/manager；日志脱敏沿用；R-7 写失败上抛沿用
- 兼容：JWT 认证体系不动；前端 axios+React Query 技术栈不动
- 可观测：慢查询日志、导入任务状态可查、审计日志（RAG）
- 回滚：重构前全量备份（mysqldump + Milvus/Neo4j 快照清单）

---

## 6. 详细修改规划

### 6.1 数据库修改规划

**动作 A — 重建（66 表，DROP+CREATE 按 edu.sql）**：
dim_*(7)、org_*(10)、staff/student_profile、series、series_category_rel、series_cohort、series_cohort_course、series_cohort_session、session_teacher_rel、session_asset、session_video、session_video_chapter、session_homework、session_exam、question_bank、`question`、session_homework_question_rel、session_exam_question_rel、coupon×3、series_*_log×3、series_favorite、consultation_record、shopping_cart_item、coupon_receive_record、`order`、order_item、payment_record、refund_request、student_cohort_rel、session_attendance、session_video_play、session_video_play_event、session_homework_submission、session_exam_submission、cohort_discussion_topic/post、cohort_review、service_ticket×3、teacher_compensation×2、channel_commission×2、risk_alert_event、risk_disposal_record、ugc_moderation_task

**动作 B — 改造（2 表）**：
- sys_user：edu.sql 列 + account/username/status 三列合并
- session_homework_submission / session_exam_submission / session_video_play_event：恢复 edu.sql 外键

**动作 C — 删除（13 表）**：curriculum_*(4)、admin_question_bank、admin_question、admin_exam_paper、admin_exam_paper_item、admin_question_tag、admin_question_to_tag、admin_course_video_asset

**动作 D — 保留（27 表）**：alembic_version、sys_user_auth、chat_session、chat_message、community_post、community_comment、community_react、gamification_badge、user_badge、user_point_log、learning_daily_summary、learning_path_instance、recommend_feedback、graph_node、graph_edge、rag_collection_meta、rag_param_preset、rag_audit_log、mcp_server、mcp_tool、mcp_tool_call_log、vocab_entry、user_vocab_card、coding_challenge、coding_submission、quiz_answer_session、quiz_wrong_book、user_profile

**动作 E — 新增索引**：
- series(institution_id,sale_status)、series_cohort(series_id,sale_status)、series_cohort_session(series_cohort_course_id,session_no)
- question(bank_id)、`order`(user_id,order_status,created_at)、order_item(order_id)、payment_record(order_id)、student_cohort_rel(user_id,enroll_status)
- session_attendance(session_id,attendance_status)、service_ticket(user_id,ticket_status)、series_visit_log(series_id,created_at)

**动作 F — 新增知识任务表**（RAG 上传持久化，替代内存 task_store 的 Redis 方案兜底）：knowledge_import_task（task_id PK、task_type、tenant_id、visibility、status、total_chunks、imported_chunks、source_files JSON、error、created_at、started_at、finished_at）

### 6.2 后端修改规划（模块 × 动作）

| 模块 | 动作 | 关键改动点 |
|------|------|-----------|
| app/curriculum | 废弃迁移 | service.py 重写为 series 体系查询；路由迁移 /api/series（兼容期保留 /api/curriculum/series 重定向） |
| app/admin/course_admin | 重写 | 四级 CRUD + 视频三表 + institution/delivery_mode 字段；schemas 对齐 edu.sql 列 |
| app/admin/question_admin | 重写 | question_bank/question CRUD、批量导入、组卷改 session_exam；删除 tag 逻辑 |
| app/interactive/quiz | 改造 | 出题源 admin_question → `question`；错误码/响应壳统一 |
| app/progress | 改造 | 提交写 edu-data 提交表（恢复外键语义）；dashboard 从 student_cohort_rel+series 聚合 |
| app/mindmap / app/recommender | 改造 | 数据源 curriculum_* → series 体系 + question |
| app/users | 修复+扩展 | 修 UPDATE users bug→sys_user；新增 /me/student-profile、/me/learning-summary |
| app/auth | 适配 | 响应壳统一（code/message/data） |
| app/chat / community / gamification / mcp / rag_admin | 适配 | 响应壳统一；gamification 排行榜走 Redis ZSET |
| app/knowledge | 增强 | +GET /tasks；task_store→Redis+knowledge_import_task 表双写；原文件存 MinIO edu-upload |
| **新建** app/market（coupons/favorites） | 新建 | 按 edu-data routers/coupons.py、favorites.py 移植 |
| **新建** app/trade（orders/payments/refunds） | 新建 | 按 edu-data routers/orders.py、payments.py 移植（订单依赖 student_cohort_rel 报名闭环） |
| **新建** app/enrollment（报名/我的班次） | 新建 | /me/cohorts 4 端点 |
| **新建** app/study（课次/视频/作业/考试查询） | 新建 | 10 端点 |
| **新建** app/tickets（工单+人工申诉） | 新建 | 5 端点 + appeal 类型 |
| app/common | 统一 | 全局响应包装器（code=0/data）、错误码字符串化映射 |

### 6.3 前端修改规划（页面 × 动作 × 接口）

**API 客户端**：
- api-client.ts：解包 {code,message,data}，code 放宽 string|number
- 新建：enrollments.ts、study.ts、coupons.ts、favorites.ts、orders.ts、payments.ts、tickets.ts、admin/rag 增 upload/tasks/partitions
- 改造：curriculum.ts、learning.ts、admin/courses.ts、admin/questions.ts、dashboard.ts、admin/users.ts、chat.ts、community.ts、mcp.ts、rag.ts（响应壳）

**页面（HTML 原型审核流，顺序即实施顺序）**：
1. /courses 课程中心（重构）：series 接口、交付模式/机构筛选、班级数
2. /courses/[seriesId] 课程详情（重构）：系列→班次→模块→课次四级、报名/领券/收藏
3. /my-courses 我的班次（重构为 enrollments）：/me/cohorts + 进度
4. /coupons 优惠券中心（新建）
5. /orders + /orders/[orderId]/pay 订单与支付（新建）
6. /refunds 退款记录（新建）
7. /favorites 我的收藏（新建，服务端）
8. /tickets 售后工单+人工申诉（新建）
9. /admin/courses 管理端课程（重构四级管理）
10. /admin/questions 管理端题库（重构两表+解析）
11. /admin/rag 新增上传入口（FR-RAG-02）
12. /learning、/practice、/me、/admin/users、/dashboard 等适配重构

### 6.4 RAG 上传入口修改规划

后端：
1. knowledge_import_task 表（6.1 动作 F）+ task_store 双写
2. GET /api/knowledge/tasks（admin，分页倒序）
3. 上传留存 MinIO edu-upload（`minio_uploader.py` 已有 put 能力），管道成功后不删源文件，记录 object_key 到任务表
4. 响应壳统一

前端 /admin/rag：
1. 新增 UploadPanel 组件（文件选择/拖拽/校验/进度/任务轮询）
2. 新增 PartitionPanel 组件（列表/删除）
3. admin/rag.ts 新增 uploadKnowledgeFiles、listKnowledgeTasks、getKnowledgeTaskStatus、listKnowledgePartitions、deleteKnowledgePartition
4. 上传完成后刷新 CollectionTable

### 6.5 Milvus/Neo4j 重建规划

1. 快照：当前集合健康报告 + Neo4j 计数（已记录：4981 条/1330 节点 6194 关系）
2. drop+rebuild edu_knowledge（loader.py ensure_collection_exists 复用）
3. Neo4j 全清
4. 生成知识切片：courses.json（219系列+657模块，含分类/目标人群/关键词）+ questions.json（1752 题干+解析）
5. 批量入库（200/批，dense+sparse 双向量）+ 图谱构建（Series/Module/Session/Question/KnowledgePoint 节点 + CONTAINS/BELONGS_TO/RELATED 边）
6. 校验报告：行数/分区/索引 + 节点/关系计数

### 6.6 数据重灌规划（full 档）

1. mysqldump 全库备份 + admin 账号行备份
2. 按 6.1 执行 DDL（动作 A~F）
3. `uv run init_db.py` 重建 + `uv run -m generate.main --profile full`（分批 --layers 1..7，断点续跑）
4. 校验：series base=219、module_code 去重=657、bank=73、question=1752、用户≈10万、订单≈8万
5. 恢复 admin/manager 账号与角色
6. 全链路冒烟：登录→课程浏览→班次→领券→下单→支付(mock)→报名→学习→作业/考试→工单

### 6.7 性能优化规划（Redis）

1. 缓存层封装 `app/common/cache.py`：`cache_get/cache_set(cache_del)` 基于现有 get_redis()
2. 缓存点：series 列表/详情/cohorts/modules/tree（TTL 300s）、question_bank/question（600s）、dashboard 聚合（60s）、gamification 排行（ZSET 永久+定时刷新）
3. 失效策略：写操作后精确 DEL；列表缓存按查询参数 hash key
4. 防穿透：空结果缓存 30s；热点 key SETNX 互斥重建（30s 锁）
5. 压测验证：Locust 现有脚本改造跑课程浏览/下单链路，P95 ≤ 800ms（命中缓存）

---

## 7. 实施计划（阶段与验收）

| 阶段 | 内容 | 验收标准 |
|------|------|---------|
| P0 备份 | mysqldump + 快照 | 备份文件可恢复验证 |
| P1 数据库重构 | 6.1 动作 A~F | 66 表结构与 edu.sql diff 一致；删除表确认无残留引用 |
| P2 数据重灌 | full 档生成+校验+admin 恢复 | 计数校验 219/657/73/1752；冒烟通过 |
| P3 后端改造 | 6.2 改造组 | pytest 全绿；/api/series 等新接口冒烟 |
| P4 后端新建+缓存 | 交易/售后/报名/学习域 + 响应壳 + Redis | 新接口联调；慢查询无 >500ms 热点；错误壳全模块统一 |
| P5 前端接口层 | 6.3 API 客户端 | tsc + vitest 全绿 |
| P6 前端页面 | 6.3 逐页 HTML 审核→React | 每页用户签收；全部页面完成 |
| P7 RAG 上传入口 | 6.4 | 上传→任务进度→分区管理→检索可见全链路 |
| P8 Milvus/Neo4j | 6.5 | 重建计数报告 + 检索/图谱查询验证 |
| P9 收尾 | 旧代码清理、文档、E2E 回归 | 全链路 E2E 通过 |

**风险与回滚**：
- 风险：full 档生成耗时（分夜跑批）；Milvus 重建向量化耗时（批量+断点）；前端页面量大（逐页审核节奏）。
- 回滚：P0 备份可在任一步骤前恢复；数据库重构在 P2 生成前可整体回退；Milvus 重建前保留集合 schema 定义。

## 8. 交付物清单

1. 数据库：重构 SQL + 索引 + diff 校验脚本
2. 数据：full 档全量数据 + 校验报告
3. 后端：改造/新建模块代码 + pytest + 响应壳统一 + Redis 缓存层
4. 前端：HTML 参考文件（逐页）+ React 页面 + API 客户端 + 测试
5. RAG：上传入口 + 任务持久化 + MinIO 留存
6. 知识库：Milvus/Neo4j 重建报告
7. 文档：本 PRD、接口文档、数据字典
