# task14 验收批判（强制技术批判）

> 依据：全局规则「任务审核验收强制技术批判与优化修改」
> 对象：task14 progress/mindmap/recommender/users（Trae，报告 DONE，未 commit）
> 结论：**⛔ 验收不通过（P0）**——dashboard 聚合引用 edu.sql 不存在的 `answers_json` 列 → 500；submit_homework/submit_exam INSERT 亦写该列（提交 500）

---

## 实证结果（8003 最新代码服务）

| 项 | 实测 |
|----|------|
| /me/learning-summary | ✅ 200 + 5 字段（total_watched_seconds/active_cohorts_count/homework_submitted/exam_submitted/exam_avg_score）|
| /me/student-profile | ⚠️ 200 但 data 空（首次未初始化，可接受）|
| **dashboard** | ❌ **500 `Unknown column 'answers_json' in 'field list'`** |
| users P10 bug | ✅ git diff 确认 PATCH /me（UPDATE users + try/except pass）删除 → PUT /me/profile（UPDATE user_profile + 上抛）|
| mindmap/recommender curriculum_ | ✅ task14 模块无残留（53 处命中均为死代码 admin/course_admin + 308 模块 + 文档）|

## 批判 1（P0 阻塞）：dashboard/submit 引用 edu.sql 不存在的 answers_json 列

**问题描述**：
1. `get_dashboard` 作业/考试子查询：`SUM(JSON_LENGTH(answers_json))` + `JSON_SEARCH(answers_json,...)` → 表无该列 → **500**
2. `submit_homework` / `submit_exam` INSERT 列表含 `answers_json` → 提交也会 500
3. 实测：GET /api/progress/dashboard → 500 `Unknown column 'answers_json'`

**证据来源**：
- 实跑 HTTP 500（2026-08-20，8003 服务）
- DB `SHOW COLUMNS`：session_homework_submission / session_exam_submission **均无 answers_json**（列清单见实证）
- edu.sql 全文：**无独立 answer 明细表**（无 answers 表；submission 表只有 total_score/score_value/submit_status）
- progress/service.py 源码（get_dashboard 3 处 + submit 2 处 answers_json）

**与正确做法差距**：dashboard 想算"答题正确率/答题数"（基于 answers_json JSON 解析），但 edu.sql 权威结构**没有作答明细存储**——这是数据模型与功能需求的冲突。报告声称"dashboard 实时聚合 4 张表"但实测 500，验收证据失真。

**优化方案**（二选一，需裁定）：
- **方案 A（推荐，符合权威结构）**：dashboard 去掉 answers_json 相关聚合——只统计：视频（watched_seconds/播放次数，已有）、作业提交数（COUNT）+ 平均分（total_score，若有）、考试提交数 + 平均分（AVG(score_value)）；**正确率/答题数不展示**（无数据载体）；submit_homework/submit_exam INSERT 去掉 answers_json 列（作答明细暂不持久化，或另设计作答表）
- **方案 B（改模型）**：若必须展示答题正确率，需新增作答明细表（如 `session_submission_answer`）——但**改 edu.sql 权威结构需用户确认**，且 task07 数据基线需补灌

**最小验证方法**：修复后 GET /api/progress/dashboard → 200 + 真实聚合（无 answers_json 引用）；submit_homework/submit_exam → 200 落库。

**预期收益与成本**：方案 A ~1h（去 answers_json 聚合 + INSERT）；方案 B 需架构决策 + 重灌。

---

## 批判 2（P2）：task14 未 git commit + 报告路径在 edu-agent/test-reports

**问题描述**：git log 停在 d4fbfbb（task44），task14 5 文件未提交；报告在 edu-agent/test-reports（沙箱路径）。

**证据来源**：git status（progress/users/recommender/mindmap 未提交）；报告位置。

**优化方案**：编排者修复验证后补 commit。

---

## 批判 3（P2）：死代码 app/admin/course_admin 残留 39 处 curriculum_（task12 未清理）

**问题描述**：`app/admin/course_admin/service.py`（旧管理端课程）39 处 curriculum_series/cohort/module/session 引用，但 main.py 已改用 domains/course_admin（task12）——旧模块**未被注册但残留**，若误注册会 500（表已删）。task12 未删除旧模块。

**证据来源**：grep curriculum_ 53 处按文件统计（admin/course_admin 39）；main.py 注册的是 domains.course_admin。

**优化方案**：task37（清理旧代码）删除 app/admin/course_admin 或标注废弃；不阻塞 task14。

---

## 汇总

| GWT | 结果 |
|-----|------|
| ① 学习打点 + dashboard 聚合 | ❌ dashboard 500（answers_json）|
| ② /me/learning-summary | ✅ 200 真实聚合 |
| ③ users 异常上抛 | ✅ P10 bug 修复 |
| ④ mindmap/recommender 数据源 | ✅ 无残留（task14 模块）|

**结论：task14 验收不通过（P0 dashboard 500）**。修复方案 A 已给（去 answers_json 聚合 + INSERT）；契约冻结⑤ 暂缓解锁前端 task54/43/60，待修复复验。
