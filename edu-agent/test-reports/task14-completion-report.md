# task14 完工报告 — progress/mindmap/recommender 改造 + users bug 修复 + /me 新接口

> **日期**：2026-08-20 | **状态**：✅ 等待编排者验收
> **前置**：task11（series 体系）、task13（question 域）
> **后置**：解锁前端 task54（/me）、task43（dashboard）、task60（admin/users）

---

## 一、交付物清单

### 1.1 修改文件（5 个）

| 文件 | 变更摘要 |
|------|---------|
| `app/users/router.py` | P10 bug 修复（`UPDATE users`→`UPDATE sys_user`，异常上抛）；新增 `GET /me/student-profile`、`GET /me/learning-summary`；删除 `PATCH /me` 兼容端点 |
| `app/progress/service.py` | `record_video_ticks`/`_grade_answers`/`submit_homework`/`submit_exam`/`get_dashboard`/`get_course_progress` 全部按 edu.sql 对齐 |
| `app/recommender/engine.py` | `_load_mastery_by_kp_code`/`collaborative_filter` 移除 `curriculum_module`/`curriculum_session` JOIN |
| `app/mindmap/router.py` | 文档字符串 `curriculum_series.id`→`series.id` |
| `app/progress/schemas.py` | 文档字符串 `curriculum_session.id`→`series_cohort_session.id` |

### 1.2 交付文档

| 文件 | 说明 |
|------|------|
| `.opencode/handoffs/task14-contract.md` | 契约冻结⑤（端点清单 + curl 示例 + 前端解锁）|
| `test-reports/task14-completion-report.md` | 本文件 |

---

## 二、GWT 验收逐条自查

### GWT ①：学习打点 + dashboard 聚合

```
[PASS] video tick-batch | status=200 code=0       → 写入 session_video_play_event
[PASS] dashboard | status=200 code=0               → 实时聚合（无 learning_daily_summary）
```

- 打点写入 `session_video_play_event`（去除 `user_id`/`session_id` 列，通过 `play_session_id` FK 关联）
- dashboard 从 `session_video_play`、`student_cohort_rel`、`session_homework_submission`、`session_exam_submission` 实时聚合，无 MOCK

### GWT ②：/me/learning-summary 真实聚合

```
[PASS] get learning-summary | status=200 code=0
       data keys: ["total_watched_seconds", "active_cohorts_count", "homework_submitted", "exam_submitted", "exam_avg_score"]
```

- 聚合 4 张 edu.sql 表，返回真实数据
- 字段对齐前端 task54 消费需求

### GWT ③：用户资料更新失败 → 异常上抛（R-7）

- `UPDATE sys_user`（原 `UPDATE users`）修复
- 移除 `try/except pass`，异常不再静默吞掉
- 删除 `PATCH /me` 兼容端点（含 P10 bug）

### GWT ④：mindmap/recommender 数据源 curriculum → series

- `app/recommender/engine.py`：移除 `LEFT JOIN curriculum_module`/`curriculum_session`
- `app/mindmap/router.py`：文档字符串修正
- `app/progress/service.py`：`curriculum_*` → `series_*`/`series_cohort_*`/`session_*`
- grep `curriculum_` 在运行代码中零引用（仅遗留 `app/curriculum/` 308 重定向 + 备份/文档文件）

---

## 三、关键差异说明

| 项目 | 原代码 | 改造后 |
|------|--------|--------|
| `record_video_ticks` INSERT 列 | `(user_id, session_id, play_session_id, ...)` | `(play_session_id, event_type, position_seconds, ...)` |
| `_grade_answers` 查询表 | `admin_question_bank` | `question JOIN dim_question_type` |
| `submit_homework` 课次验证 | `curriculum_session` | `series_cohort_session` |
| `submit_exam` 试卷/条目表 | `admin_exam_paper` / `admin_exam_paper_item` | `session_exam` / `session_exam_question_rel` |
| `get_dashboard` 数据源 | `learning_daily_summary`（非 edu.sql） | `session_video_play` + `student_cohort_rel` + `session_homework_submission` + `session_exam_submission` |
| `get_course_progress` 层级表 | `curriculum_series` / `curriculum_module` / `curriculum_session` | `series` / `series_cohort_course` / `series_cohort_session` |
| users `PATCH /me` | `UPDATE users`（错误表名）+ `try/except pass` | 端点删除；用 `PUT /me/profile` 替代 |

---

## 四、task12/13 教训执行检查

| 教训 | 执行情况 |
|------|---------|
| ① repo SQL 对照 edu.sql 实际列 | ✅ `session_video_play_event` 确无 `user_id`/`session_id` 列 |
| ② 勿写不存在的 yn | ✅ `series` 无 yn、`series_cohort_course` 无 yn、`series_cohort_session` 无 yn |
| ③ JSON 列显式解析 | ✅ `options_json` / `learning_goals` / `subject_preferences` 中已处理 |
| ④ 异常上抛 R-7 | ✅ `try/except pass` 移除 |

---

## 五、运行方式

```bash
cd edu-agent
.venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8003

# 验证（server 运行中）
set TEST_BASE=http://127.0.0.1:8003
.venv\Scripts\python scripts\_verify_task14.py
```