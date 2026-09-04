# task14-fix 补充修复方案（基于修复验收批判）

> 依据：`task14-修复验收批判.md` 3 条批判 ｜ 原则：现有 progress 代码迭代

## 方案总览

| # | 修改点 | 目标文件 | 优先级 | 工作量 |
|---|--------|---------|--------|--------|
| A | submit_homework/exam 参数错位修复 + schema 补 homework_id | `progress/schemas.py` + `progress/service.py` | **P0** | 1h |
| B | dashboard 包响应壳（ok()）| `progress/router.py` | **P1** | 20min |
| C | 补测试（真实 homework_id/exam_id 提交落库）| `test_progress.py` 或脚本 | P1 | 30min |

---

## A. P0：submit 参数错位 + schema 补字段

### schema（`progress/schemas.py`）

```python
class HomeworkSubmitIn(BaseModel):
    session_id: int = Field(..., gt=0, description="课次 ID = series_cohort_session.id")
    homework_id: int = Field(..., gt=0, description="作业 ID = session_homework.id")  # 新增（外键必填）
    answers: list[SubmittedAnswerIn] = Field(..., min_length=1, max_length=100)

class ExamSubmitIn(BaseModel):
    exam_id: int = Field(..., gt=0, description="考试 ID = session_exam.id")  # paper_id → exam_id（表外键）
    answers: list[SubmittedAnswerIn] = ...
    duration_seconds: int = ...
    start_at: datetime = ...
```

### service（`progress/service.py`）

```python
# submit_homework 参数修正（列与参数一一对应）：
# INSERT 列：(institution_id, homework_id, user_id, student_id, session_id, submit_no, submit_status, total_score, correction_status, ...)
# VALUES (1, %s, %s, %s, %s, %s, 'submitted', %s, %s, NULL, NULL, NOW(), ...)
execute_write(sql, (
    req.homework_id,      # homework_id（外键 → session_homework.id）
    user_id,              # user_id
    student_id,           # student_id（须真实 student_profile.id，非 user_id）
    req.session_id,       # session_id
    submit_no,
    total_score,
    db_correction_status,
))
# 注：student_id 需先查 student_profile（user_id → student_profile.id），不可用 user_id 硬顶（FK 到 student_profile）

# submit_exam 同理：paper_id→exam_id，参数对齐 (exam_id, user_id, student_id, attempt_no, duration_seconds, score_value, ...)
```

### 关键点
- **student_id 须真实**：FK→student_profile.id，不能复用 user_id（sys_user.id ≠ student_profile.id）
- submit_exam：`session_exam_submission` 无 session_id，用 exam_id

---

## B. P1：dashboard 包壳

### router（`progress/router.py`）

```python
# 原：return await service.get_dashboard(...)   # 裸 dict
# 改：return ok(await service.get_dashboard(...))  # 统一壳
```

---

## C. P1：测试补全

- 用真实存在的 homework_id（SELECT id FROM session_homework LIMIT 1）+ exam_id（SELECT id FROM session_exam LIMIT 1）提交 → 断言 200 + 落库
- 补 dashboard 壳断言（code in body）

---

## 量化指标（修复后）

- POST submit_homework（真实 homework_id）→ **200 + 落库**（SQL 查 session_homework_submission 有记录）
- POST submit_exam（真实 exam_id）→ 200 + 落库
- GET dashboard → **200 + 含 code/data 壳**
- learning-summary 回归 200

## 新风险与应对

| 风险 | 应对 |
|------|------|
| student_profile 无记录（生成用户无 profile）| submit 前 get_or_create student_profile（参考 users 模块）|
| homework/exam 数据不全 | 用现有 full 档数据（session_homework 66528 条 / session_exam 15444 条 实证存在）|

## 实施顺序

A（1h）→ B（20min）→ C（30min）→ 重启 8003 → 实证 4 项
