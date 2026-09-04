# task14 优化修改方案（基于技术批判，在现有产物上迭代）

> 依据：`task14-技术批判.md` 3 条批判 ｜ 原则：现有 progress 代码迭代，不另起炉灶
> **默认采用方案 A**（去 answers_json 聚合，符合 edu.sql 权威结构，不改模型）

## 方案总览

| # | 修改点 | 目标文件 | 优先级 | 工作量 |
|---|--------|---------|--------|--------|
| A | dashboard 去 answers_json 聚合（只统计提交数/分数）| `app/progress/service.py` | **P0** | 40min |
| B | submit_homework/submit_exam INSERT 去 answers_json 列 | `app/progress/service.py` | **P0** | 30min |
| C | 作业平均分用 total_score（非 answers 解析）| `app/progress/service.py` | P1 | 20min |

---

## A. P0：dashboard 去 answers_json 聚合

### 修改内容（`app/progress/service.py` get_dashboard）

```python
# 原（bug）：answers_json 列不存在 → 500
# 作业子查询：
#   "SUM(JSON_LENGTH(answers_json)) AS q_a,"
#   "SUM(COALESCE(JSON_LENGTH(JSON_SEARCH(answers_json,'all',true,NULL,'$[*].is_correct')),0)) AS q_c"
# 考试子查询同理

# 改（edu.sql 无 answers_json，只统计提交数与分数）：
# 作业子查询：
"SELECT DATE(submitted_at) AS stat_date,"
" COUNT(*) AS cnt,"
" AVG(COALESCE(total_score,0)) AS avg_score"          # total_score 列存在
" FROM session_homework_submission"
" WHERE user_id=%s AND DATE(submitted_at)>=%s"
" GROUP BY DATE(submitted_at)"

# 考试子查询：
"SELECT DATE(submit_at) AS stat_date,"
" COUNT(*) AS cnt,"
" AVG(COALESCE(score_value,0)) AS avg_score"          # score_value 列存在
" FROM session_exam_submission"
" WHERE user_id=%s AND DATE(submit_at)>=%s"
" GROUP BY DATE(submit_at)"

# 移除作业/考试的 q_a（答题数）/q_c（正确数）字段——edu.sql 无作答明细载体
# DashboardOut schema 同步：去掉 q_a/q_c 字段（或置 null）
```

### 关键点
- DashboardOut schema 需同步删/置 null q_a/q_c（或改名为提交数语义）
- 正确率/答题数**不展示**（权威结构无数据）——若未来要，需新增作答表（架构决策）

---

## B. P0：submit_homework/submit_exam INSERT 去 answers_json

### 修改内容

```python
# 原 INSERT 含 answers_json 列 → 500
# 改：INSERT 列表移除 answers_json
"INSERT INTO session_homework_submission "
"(institution_id, homework_id, user_id, student_id, session_id, submit_no, submit_status, total_score, "
" correction_status, submitted_at, created_at, updated_at) "
"VALUES (1,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW(),NOW())"

# 考试同理移除 answers_json
```

### 注意
- 作答明细（每题答案/得分）暂不持久化——前端 task48/49（学习/练习）提交时只传总分；如需每题明细需新增作答表（另议）

---

## C. P1：作业平均分用 total_score

- 作业 avg 用 `AVG(COALESCE(total_score,0))`（session_homework_submission.total_score 存在，非 answers 解析）

---

## 量化指标（修复后）

- GET /api/progress/dashboard → **200 + 真实聚合**（视频秒数/作业提交数/考试提交数/平均分，无 500）
- submit_homework / submit_exam → 200 落库（无 answers_json 引用）
- /me/learning-summary 回归 200（5 字段不变）
- grep answers_json 在 progress/service.py = 0（运行代码）

## 新风险与应对

| 风险 | 应对 |
|------|------|
| 前端 dashboard 依赖 q_a/q_c | task43（前端 dashboard）实现时以提交数/分数为主，正确率不展示；契约⑤ 交接单注明 |
| 作业/考试平均分无意义（total_score 可能为 0）| 由数据决定；若 total_score 常为 0 则只展示提交数 |

## 实施顺序

A（40min）→ B（30min）→ C（20min）→ 重启 8003 → 实证 dashboard 200 + submit 落库 + learning-summary 回归
