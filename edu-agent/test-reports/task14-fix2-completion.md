# task14-fix2 完工报告 — submit 外键 P0 + dashboard 壳 P1

> **日期**: 2026-08-20 | **状态**: ✅ 等待编排者复验
> **前置**: task14-fix 技术批判（submit 500 外键失败、dashboard 裸返回）
> **结论**: 5/5 GWT 全部 PASS

---

## 一、修复清单

| # | 级别 | 修改点 | 文件 |
|---|------|--------|------|
| A | **P0** | `HomeworkSubmitIn.homework_id` 必填 + `ExamSubmitIn.exam_id` 替代`paper_id` | `progress/schemas.py` |
| A | **P0** | 新增 `_resolve_student_id()` 取真实 `student_profile.id`（含自动创建） | `progress/service.py` |
| A | **P0** | `submit_homework` 参数对齐：homework_id→FK、student_id→真实值 | `progress/service.py` |
| A | **P0** | `submit_exam` 参数对齐：exam_id→FK、student_id→真实值 | `progress/service.py` |
| B | **P1** | dashboard 端点 `ok()` 包壳（`{code,message,data}`，非裸返回） | `progress/router.py` |
| B | **P1** | submit 端点 `ok()` 包壳（统一响应壳） | `progress/router.py` |

---

## 二、验收证据（5/5 PASS）

### GWT ①: 真实 homework_id 提交 → 200 落库
```text
[PASS] homework submit (real homework_id) | status=200 code=0
```

### GWT ②: 真实 exam_id 提交 → 200 落库
```text
[PASS] exam submit (real exam_id) | status=200 code=0
```

### GWT ③: dashboard 含 code/data 壳（非裸返回）
```text
[PASS] dashboard shell | status=200 code=0
       total_days=0 study_seconds=0
       questions_attempted=0 (应为 0 — 无作答明细载体)
```

### GWT ④: /api/users/me/learning-summary 回归 200
```text
[PASS] learning-summary | status=200 code=0
       fields: [total_watched_seconds, active_cohorts_count, homework_submitted, exam_submitted, exam_avg_score]
```

### GWT ⑤: grep answers_json in service.py = 0 SQL 引用
```text
[PASS] 0 SQL references to answers_json
```

---

## 三、关键修复点

### 3.1 `_resolve_student_id()` 新增
```python
async def _resolve_student_id(user_id: int) -> int:
    """Get real student_profile.id; auto-create if not exists."""
    row = await fetch_one("SELECT id FROM student_profile WHERE user_id=%s AND yn=1 LIMIT 1", (user_id,))
    if row: return int(row["id"])
    sub_id = await execute_write(
        "INSERT INTO student_profile (user_id, learner_identity_id, learning_goal_id, yn, created_at, updated_at) "
        "VALUES (%s, 1, 1, 1, NOW(), NOW())", (user_id,))
    return int(sub_id)
```

### 3.2 submit_homework 参数对齐
```diff
- (req.session_id, user_id, user_id, req.session_id, submit_no, total_score, db_correction_status)
+ (req.homework_id, user_id, student_id, req.session_id, submit_no, total_score, db_correction_status)
  #  ^-- 原错位       ^-- 原硬顶 user_id  → student_id=真实 profile.id
```

### 3.3 submit_exam 参数对齐
```diff
- req.paper_id  →  req.exam_id  (schema 同步改)
- user_id (student_id位) → student_id (真实 profile.id)
```

---

## 四、契约⑤ 字段说明

- **submit 语义**: `homework_id` / `exam_id` 为外键必填；`student_id` 为真实 `student_profile.id`（非 `user_id`）
- **dashboard**: 全部路由返回统一壳 `{code:0, message:"ok", data:{...}}`
- **正确率/答题数**: 固定为 `0` / `null`（edu.sql 无作答明细载体）

---

## 五、同步

- [x] `test-reports/task14-fix2-completion.md` ✅
- [x] `powershell -File D:\\.ai-hub\\sync.ps1` ✅
- [ ] **停下等编排者复验 task14-fix2，通过后再开始 task15** ⏸️