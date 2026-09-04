# EduAgent 自建数据库表文档

> 生成时间：2026-08-16
> 数据源：`alembic/baseline_schema.sql`（105 表）
> 对比基准：`E:\stu\project\stu\edu-data\sql\edu.sql`（66 表）

## 一、总览

| 分类 | 数量 | 说明 |
|------|------|------|
| 基准表（edu.sql） | 60 | 与 edu.sql 66 表对齐（部分表未创建） |
| 自建表 | 45 | 项目自行创建，不在 edu.sql 中 |
| 总计 | 105 | |

## 二、自建表分类（45 张）

### 2.1 管理端模块（7 张）

| 表名 | 用途 | 代码依赖 | 可删除？ |
|------|------|---------|---------|
| `admin_course_video_asset` | 课程视频资产（MinIO 对象键/转码状态） | `app/admin/course_admin/` | ⚠️ 需迁移到 session_asset/session_video |
| `admin_exam_paper` | 试卷主表 | `app/admin/question_admin/` | ⚠️ 需迁移到 session_exam |
| `admin_exam_paper_item` | 试卷条目（题目-分数映射） | `app/admin/question_admin/` | ⚠️ 需迁移到 session_exam_question_rel |
| `admin_question` | 互动答题题库（旧） | `app/interactive/quiz/` | ⚠️ 需迁移到 question |
| `admin_question_bank` | 管理端题库（旧） | `app/admin/question_admin/` | ⚠️ 需迁移到 question_bank |
| `admin_question_tag` | 题目标签 | `app/admin/question_admin/` | ✅ 删除（标签功能改为全文检索） |
| `admin_question_to_tag` | 题目-标签关联 | `app/admin/question_admin/` | ✅ 删除 |

### 2.2 课程体系（旧，4 张）

| 表名 | 用途 | 代码依赖 | 可删除？ |
|------|------|---------|---------|
| `curriculum_series` | 旧课程系列 | `app/curriculum/` | ⚠️ 需迁移到 series |
| `curriculum_cohort` | 旧班次 | `app/curriculum/` | ⚠️ 需迁移到 series_cohort |
| `curriculum_module` | 旧模块 | `app/curriculum/`, `app/progress/`, `app/mindmap/` | ⚠️ 需迁移到 series_cohort_course |
| `curriculum_session` | 旧课次 | `app/curriculum/`, `app/progress/` | ⚠️ 需迁移到 series_cohort_session |

### 2.3 聊天/对话（2 张）

| 表名 | 用途 | 代码依赖 | 可删除？ |
|------|------|---------|---------|
| `chat_session` | 对话会话 | `app/chat/service.py` | ❌ 不能删（核心功能） |
| `chat_message` | 对话消息 | `app/chat/service.py` | ❌ 不能删（核心功能） |

### 2.4 社区/论坛（3 张）

| 表名 | 用途 | 代码依赖 | 可删除？ |
|------|------|---------|---------|
| `community_post` | 社区帖子 | `app/community/` | ❌ 不能删 |
| `community_comment` | 社区评论 | `app/community/` | ❌ 不能删 |
| `community_react` | 社区反应（点赞/收藏） | `app/community/` | ❌ 不能删 |

### 2.5 互动学习（5 张）

| 表名 | 用途 | 代码依赖 | 可删除？ |
|------|------|---------|---------|
| `coding_challenge` | 编程挑战 | `app/interactive/coding/` | ❌ 不能删 |
| `coding_submission` | 编程提交 | `app/interactive/coding/` | ❌ 不能删 |
| `quiz_answer_session` | 答题会话 | `app/interactive/quiz/` | ❌ 不能删 |
| `quiz_wrong_book` | 错题本 | `app/interactive/quiz/` | ❌ 不能删 |
| `vocab_entry` | 词汇条目 | `app/interactive/vocab/` | ❌ 不能删 |

### 2.6 游戏化/成就（4 张）

| 表名 | 用途 | 代码依赖 | 可删除？ |
|------|------|---------|---------|
| `gamification_badge` | 徽章定义 | `app/gamification/` | ❌ 不能删 |
| `user_badge` | 用户徽章 | `app/gamification/` | ❌ 不能删 |
| `user_point_log` | 积分日志 | `app/gamification/` | ❌ 不能删 |
| `ranking_snapshot` | 排行榜快照 | `app/gamification/` | ❌ 不能删 |

### 2.7 知识图谱（2 张）

| 表名 | 用途 | 代码依赖 | 可删除？ |
|------|------|---------|---------|
| `graph_node` | 图谱节点 | `app/mindmap/`, `app/recommender/` | ❌ 不能删（MySQL 版图谱存储） |
| `graph_edge` | 图谱边 | `app/mindmap/`, `app/recommender/` | ❌ 不能删 |

### 2.8 MCP 工具（3 张）

| 表名 | 用途 | 代码依赖 | 可删除？ |
|------|------|---------|---------|
| `mcp_server` | MCP 服务器注册 | `app/mcp/` | ❌ 不能删 |
| `mcp_tool` | MCP 工具注册 | `app/mcp/` | ❌ 不能删 |
| `mcp_tool_call_log` | MCP 调用日志 | `app/mcp/` | ❌ 不能删 |

### 2.9 RAG 管理（3 张）

| 表名 | 用途 | 代码依赖 | 可删除？ |
|------|------|---------|---------|
| `rag_audit_log` | RAG 审计日志 | `app/admin/rag_admin/` | ❌ 不能删 |
| `rag_collection_meta` | Milvus 集合元数据 | `app/admin/rag_admin/` | ❌ 不能删 |
| `rag_param_preset` | RAG 参数预设 | `app/admin/rag_admin/` | ❌ 不能删 |

### 2.10 学习进度/用户画像（5 张）

| 表名 | 用途 | 代码依赖 | 可删除？ |
|------|------|---------|---------|
| `learning_daily_summary` | 每日学习汇总 | `app/progress/` | ❌ 不能删 |
| `user_profile` | 用户画像 | `app/users/`, `app/recommender/` | ❌ 不能删 |
| `user_vocab_card` | 用户词汇卡 | `app/interactive/vocab/` | ❌ 不能删 |
| `recommend_feedback` | 推荐反馈 | `app/recommender/` | ❌ 不能删 |
| `student_cohort_rel` | 学生-班次关系 | `app/progress/` | ❌ 不能删 |

### 2.11 其他（7 张）

| 表名 | 用途 | 代码依赖 | 可删除？ |
|------|------|---------|---------|
| `cohort_discussion_topic` | 班次讨论话题 | — | ⚠️ 待确认 |
| `cohort_discussion_post` | 班次讨论帖 | — | ⚠️ 待确认 |
| `cohort_review` | 班次评价 | — | ⚠️ 待确认 |
| `consultation_record` | 咨询记录 | — | ✅ 删除（改为人工申诉） |
| `session_attendance` | 课次考勤 | — | ⚠️ 待确认 |
| `session_teacher_rel` | 课次-教师关系 | — | ⚠️ 待确认 |
| `risk_disposal_record` | 风控处置记录 | — | ⚠️ 待确认 |

## 三、删除评估汇总

| 结论 | 数量 | 表名 |
|------|------|------|
| ✅ 可安全删除 | 3 | admin_question_tag, admin_question_to_tag, consultation_record |
| ⚠️ 需迁移后删除 | 7 | admin_course_video_asset, admin_exam_paper, admin_exam_paper_item, admin_question, admin_question_bank, curriculum_series, curriculum_cohort, curriculum_module, curriculum_session |
| ❌ 不能删除 | 29 | chat_*, community_*, coding_*, quiz_*, vocab_*, gamification_*, graph_*, mcp_*, rag_*, user_*, learning_*, recommend_*, ranking_*, student_cohort_rel |
| ⚠️ 待确认 | 6 | cohort_discussion_*, cohort_review, consultation_record, session_attendance, session_teacher_rel, risk_disposal_record |

## 四、删除策略

**不能直接全部删除重建**。必须分阶段：

1. 先删 3 张可安全删除的表（无代码依赖或已废弃）
2. 迁移 9 张管理端+课程旧表到 edu.sql 对应表（task02 + task11~13）
3. 保留 29 张核心功能表不动
4. 确认 6 张待确认表的去留