# task14-fix 验收批判（补充）

> 依据：全局规则「任务审核验收强制技术批判与优化修改」
> 对象：task14-fix（answers_json P0 修复，Trae 报告 5/5）
> 结论：**⛔ P0 修复有效，但复验发现 2 个新 P0/P1 缺陷**——submit 外键失败 + dashboard 无壳；需修复后复验

---

## 修复实证（8003 最新代码服务）

| 项 | 实测 | 判定 |
|----|------|------|
| ① dashboard 500（answers_json）| ✅ 200 真实聚合（total_days=0 等，无 MOCK）| P0 修复有效 |
| ④ learning-summary 回归 | ✅ 200 + 5 字段 | 通过 |
| ⑤ grep answers_json | ✅ 3 处均注释（零 SQL 引用）| 通过 |
| ②③ submit_homework/exam | ❌ **500 外键失败** | **新 P0** |
| dashboard 壳 | ❌ 裸返回（无 code/data）| **新 P1** |

## 批判 1（P0）：submit_homework/exam 外键失败 —— schema 缺 homework_id + 参数错位

**问题描述**：`POST /api/progress/homework/submit`（session_id=1 + answers）实测 **500 `Cannot add or update a child row: foreign key constraint fails`**。根因在 progress/service.py submit_homework：

```python
# INSERT 列：(institution_id, homework_id, user_id, student_id, session_id, submit_no, submit_status, total_score, ...)
# 参数：    (req.session_id, user_id, user_id, req.session_id, submit_no, total_score, db_correction_status)
#           ↑ homework_id 位被 req.session_id 占用（session_id=1 不是有效 homework_id → 外键失败）
```

- **schema 无 homework_id 字段**（HomeworkSubmitIn 只有 session_id + answers）
- 参数错位：`homework_id ← req.session_id`（应为真实 homework_id）
- submit_exam 同理：表要 `exam_id`（FK→session_exam.id），schema 用 `paper_id` 且 service 未正确映射

**证据来源**：
- 实跑 HTTP 500（2026-08-20，8003 服务）
- progress/service.py:198-210（INSERT + 参数）
- `SHOW CREATE TABLE`：session_homework_submission.homework_id FK→session_homework.id；session_exam_submission.exam_id FK→session_exam.id

**与正确做法差距**：提交作业/考试需要 `homework_id`/`exam_id`（外键必填），但 schema 未提供 → 参数错位。报告"②③ 200 落库"与实测 500 矛盾（报告证据失真或用了 mock）。

**优化方案**：
1. `HomeworkSubmitIn` 增加 `homework_id: int`（对应 session_homework.id）
2. submit_homework 参数修正：`homework_id, user_id, student_id, session_id, ...` 一一对应（student_id 用真实 student_profile.id 而非 user_id）
3. `ExamSubmitIn.paper_id` → `exam_id`（或 service 映射 paper_id→exam_id），submit_exam 参数对齐
4. 补测试：真实 homework_id/exam_id 提交 → 200 落库

**最小验证方法**：用存在的 homework_id/exam_id 提交 → 200 + 落库（SQL 查表确认）。

**预期收益与成本**：~1h（schema + service 参数修正）。

---

## 批判 2（P1）：dashboard 裸返回（无响应壳，契约① 违规）

**问题描述**：`GET /api/progress/dashboard` 实测返回裸 JSON（`{"total_days":0,...}` 顶层字段），**无 `{code,message,data}` 壳**。同模块 learning-summary 有壳（`{"code":0,"data":{...}}`）——**接口间响应壳不一致**，违反契约①"全模块统一响应壳"。前端 task43（dashboard）解包会失败（它期望 code/data）。

**证据来源**：实跑对比：learning-summary `code in body`=True；dashboard `code in body`=False。

**与正确做法差距**：契约① 要求所有业务接口成功 `{code:0,message:"ok",data}`。dashboard 直接 return 裸 dict（未走 ok()）→ RespWrap 只包非 2xx，200 裸响应不补壳。

**优化方案**：progress/router.py dashboard 端点改 `return ok(data)`（统一壳）；前端 task43 按壳解包。

**最小验证方法**：dashboard 返回含 code/data。

**预期收益与成本**：~20min。

---

## 批判 3（P2）：task14-fix 未 git commit

**问题描述**：progress/users/recommender/mindmap 5 文件改动未提交（git log 停在 d4fbfbb）。

**证据来源**：git status（5 个 M）。

**优化方案**：编排者修复验证后补 commit。

---

## 汇总

| 项 | 状态 |
|----|------|
| answers_json P0 | ✅ 已修（dashboard 200）|
| submit 外键 P0 | ❌ 待修（schema 缺 homework_id + 参数错位）|
| dashboard 壳 P1 | ❌ 待修 |
| learning-summary | ✅ 回归 |

**结论：task14-fix 的原始 P0（answers_json）修复有效，但复验发现 submit 外键 P0 + dashboard 壳 P1，需继续修复后复验**。契约⑤ 仍暂缓。
