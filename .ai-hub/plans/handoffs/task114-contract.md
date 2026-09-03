# task114 契约冻结单（C-A）— 全站响应壳统一 + `/api/users/me` 新契约 + DashboardOut 扩展（D4）

- **域**：后端契约 ｜ 编号：**C-A** ｜ 状态：待验收 →（测试 agent 独立核验后）已验收
- **冻结范围**：全站 JSON 响应壳 `{code, message, data}`、`GET /api/users/me` snake_case 视图、
  `GET /api/progress/dashboard` DashboardOut 扩展。
- **技术路线（选型审计）**：默认 **① RespWrap 中间件统一包裹**（`app/middleware/resp_wrap.py`），
  对「裸 response_model / 裸 dict 的成功 JSON 响应」统一包壳，全局生效、改动面最小；不再逐端点改写 `ok()`。
  `GET /api/users/me` 需换字段语义（camelCase→snake_case），**单独重写**为规范 snake_case 合并视图。
- 实证实例：`MYSQL_HOST=127.0.0.1`、`DEBUG=true`、隔离端口 **8078**（托管 8000 测试隔离）。

---

## 1. 全站响应壳统一（幂等中间件）

**规则**：所有 `application/json` 响应统一为三层壳；**已是壳则跳过，绝不二次包裹（幂等边界）**。

| 条件 | 处理 | 结果 |
|---|---|---|
| 白名单前缀（`/docs /health /metrics /openapi.json ...`）或特殊内容类型（SSE 流 / 文件下载 / 图片 / 文本） | 原样透传 | 不包壳 |
| 2xx 且 body **已是壳**（`code`+`message`+`data` 三键齐备） | 幂等透传 | 单层壳 |
| 2xx 且 body 为**裸 DTO / 裸 dict** | 统一包壳 | `{code:0, message:"ok", data:<原体>}` |
| 非 2xx 且已是壳 | 幂等透传 | 不变 |
| 非 2xx 裸体（如 FastAPI `{"detail":...}`） | 按状态码映射壳化 | `{code:<码>, message:<detail>, data:null}` |

**幂等判定方法（关键，防误判）**：壳判定为「`code`+`message`+`data` **三键齐备**」，而非仅查 `code`。
因为 `/api/coding/challenges/{code}` 等业务 DTO 顶层自带 `code` 字段（题目代码），
若仅查 `code` 会被误判为已壳而**漏包**（实测纠正点，harden 边界）。
实测 `/api/coding/challenges/PY-SUM-TWO` 已正确包壳为 `{code:0,...data:{code:"PY-SUM-TWO",...}}`。

**幂等边界（写进契约，交 CDC 核验）**：
- 已 `ok()` 的端点（auth/me、progress/dashboard 等）仍为**单层壳**，`data` 为普通对象非嵌套壳。
- 全站响应统一后，`OK=106、BARE 仅剩 /health`（`/health` 属白名单，按设计不包壳）。

### 该中间件覆盖（原裸 DTO，现全部包壳）
`/api/recommend/*`（path/next/feedback）、`/api/mindmap/*`、`/api/interactive/quiz/*`、
`/api/vocab/*`、`/api/coding/*`、`/api/math/*`、`GET /api/users/me`、`GET /api/users/me/profile`、
`/api/series`（分页 `{items,page_meta}`）、以及历史审计 §2.2 列出的其它裸端点。

---

## 2. `GET /api/users/me` 新契约（snake_case，role 字符串枚举）

替换旧的裸 dict + camelCase 混合（`id / roles / tenantId / learningGoal / subjectPreferences`）。

**`data` 字段（全部 snake_case）**：
`user_id`(int) · `account`(str) · `username`(str) · `nickname`(str) · `role`(str: `student|teacher|manager|admin`) ·
`email` · `mobile` · `real_name` · `gender` · `avatar_url` ·
`learning_goal`(string[]) · `subject_preferences`(string[]，学科 code 列表) · `profile`(嵌套画像，snake_case)

**消费面**：12 个学生页 adminEntry 均 `EAPI.get("/api/users/me")` 后判 `u.role==="admin"||"manager"`；
`me.html` 读 `u.learning_goal` / `u.subject_preferences`。本次冻结已保证 `role` 为字符串、`learning_goal`/`subject_preferences` 为列表，消费逻辑结构回归通过（只读核对，不改 FE）。

### 真实 curl 示例（8078 实测）
```bash
curl -s http://127.0.0.1:8078/api/users/me -H "Authorization: Bearer <student>"
# HTTP 200  →
{
  "code": 0, "message": "ok",
  "data": {
    "user_id": 1, "account": "user000001", "username": "edu_user_000001",
    "nickname": "小柚子同学", "role": "student", "email": "user000001@edu.example.com",
    "mobile": "13900000001", "real_name": "杨怡骏", "gender": "female",
    "avatar_url": "https://cdn.example.com/avatars/x.png",
    "learning_goal": ["编程入门", "升学备考"],
    "subject_preferences": ["programming", "math"],
    "profile": { "...snake_case 画像...": "..." }
  }
}
```

---

## 3. `GET /api/interactive/quiz/next`（裸 DTO 包壳示例）
```bash
curl -s "http://127.0.0.1:8078/api/interactive/quiz/next?subject_code=math" -H "Authorization: Bearer <student>"
# HTTP 200 →
{
  "code": 0, "message": "ok",
  "data": {
    "question_id": null, "custom_code": "Q-MATH-SINGLE-SUM100",
    "subject_code": "math", "question_type": "SINGLE",
    "title": "1+2+3+…+99+100 = ?", "choices": [{"key":"A","text":"5000"},{"key":"B","text":"5050"}, {"key":"C","text":"4950"},{"key":"D","text":"5100"}],
    "items": [], "pairs": [], "hint": null,
    "explain_template": "高斯求和：和 = (首项+末项)×项数÷2 = (1+100)×100÷2 = 5050。"
  }
}
```
> 注意：`correct` 判分答案仍不下发（`exclude=True`，audit B3 已处理）。

---

## 4. `GET /api/series`（分页裸 DTO 包壳示例）
```bash
curl -s http://127.0.0.1:8078/api/series -H "Authorization: Bearer <student>"
# HTTP 200 →
{ "code": 0, "message": "ok",
  "data": { "items": [ { "id": 2628, "series_name": "信息学竞赛入门班·录播", ... } ], "page_meta": { ... } } }
```
> 课程域分页壳仍为 `{items, page_meta}`（audit §X4/§2.2 已知不一致），task115（C-B）负责分页 DTO 统一；
> task114 只保证它现在**被包进 `{code,message,data}.data`**，不做分页字段改名。

---

## 5. `GET /api/progress/dashboard`（DashboardOut 扩展 D4）
```bash
curl -s "http://127.0.0.1:8078/api/progress/dashboard?days=7" -H "Authorization: Bearer <student>"
# HTTP 200 →
{
  "code": 0, "message": "ok",
  "data": {
    "total_days": 1, "total_study_seconds": 6633,
    "total_questions_attempted": 7, "total_questions_correct": 3, "overall_correct_rate": 0.42857142857142855,
    "active_courses_count": 1, "latest_streak_days": 1,
    "recent_days": [ { "stat_date": "2026-09-03", "study_seconds": 0, "video_ticks": 0, "homework_submitted": 0,
                        "homework_correct_rate": null, "exam_submitted": 0, "exam_avg_score": null,
                        "questions_attempted": 0, "questions_correct": 0 }, ... ]
  }
}
```
**新增字段与数据源（DB 实证）**：
- `total_questions_attempted` / `total_questions_correct`：`quiz_answer_session`（每个作答一行，`is_correct` 判定）—— 实测 student(user_id=1) attempts=7 correct=3。
- `active_courses_count`：`student_cohort_rel` 中 `enroll_status='active'` 计数 —— 实测 =1。
- `overall_correct_rate`：attempts>0 时 = correct/attempts，否则 null。

---

## 6. 附带实测（GWT 断言）
```bash
curl -s http://127.0.0.1:8078/api/recommend/next?top_n=3 -H "Authorization: Bearer <student>"   # → code==0 包壳
curl -s http://127.0.0.1:8078/api/mindmap/subject/english -H "Authorization: Bearer <student>"   # → code==0 包壳
curl -s http://127.0.0.1:8078/api/users/me -H "Authorization: Bearer garbage.token"              # → HTTP 401 {code:"40101",...}
curl -s http://127.0.0.1:8078/api/nonexistent-xyz -H "Authorization: Bearer <student>"            # → HTTP 404 {code:"40400",...}
```

---

## 7. 验收要点（codex L1 / CDC 核验清单）
1. 全站 JSON 2xx 统一 `{code,message,data}`，无裸 DTO；断点 `code==0`。
2. **幂等**：已 `ok()` 端点（auth/me、dashboard 等）`data` 不为嵌套壳；`/api/coding/challenges/{code}` 因顶层 `code` 字段未漏包。
3. `users/me` snake_case 且含 `role` 字符串；12 学生页 adminEntry `u.role` 判定返回可用。
4. dashboard 含 `total_questions_attempted`、`active_courses_count`（来源 DB 实证）。
5. 回归：`interface_acceptance_final.py`（L2）+ 前端 vitest；`/docs` response_model 仍可推导（包壳在中间件层，不破坏 OpenAPI schema）。
6. 已知遗留（非本任务）：`/health` 为白名单裸体（按设计）；`/api/knowledge/partitions` 500 依赖外部向量库（不可达环境）；`POST /api/admin/rag/presets` 409 code 类型为字符串 `40900`（错误码类型历史遗留，task113 安全包范围）。