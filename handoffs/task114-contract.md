# 契约冻结单 C-A · task114 — 全站响应壳统一 + `/api/users/me` 新契约 + DashboardOut 扩展

> 状态：**FROZEN（冻结）** ｜ 域：后端契约 ｜ 编号：C-A
> 实证实例：`127.0.0.1:8000`（当前托管实况，DEBUG=true）、登录态 student `user000001`。
> 收口说明（客观、不夸大）：本契单归档的**实质契约变更大多已在历史 commit 落地**——
> C-A 响应壳原实现 `bdf85cd`（RespWrap 中间件 + users/me 重写 + DashboardOut 扩展）+ W2 批判 C1
> `664774b`（OpenAPI 响应壳上移到契约，docs<>runtime 统一）+ 本次 **curl 实测复验**。本次仅补契单归档。
> 全部"真实输出"证据来自本环境 live 8000 的真实 HTTP 抓包（`test-reports/_probe_114_115.py`，21 断言 PASS）。

***

## §0 验证约束（必读）

- 端口 **8000** 为当前托管实况实例（OpenAPI 253KB、`/health` 200 存活）。

- 所有请求带真实 `Bearer`（登录 `POST /api/auth/login` 得 `access_token`）；**禁用 DEBUG 虚拟管理员直读**。

- 全程用 Python `urllib` 直接抓包（不用 curl 二元，避免 `api` 脱敏干扰）；jq 等价断言见 §5。

- 交互式真实前缀核实：main.py 挂载 `prefix="/api/interactive/quiz"`。实测 `/api/interactive/quiz/types` → 200 包壳、
  `/api/quiz/next`（无 interactive 段）→ 404 —— **真实前缀为** **`/api/interactive/quiz`**，澄清了"`api` 被脱敏为 `n`"的疑雾（本环境无此脱敏，以 urllib 实测为准）。

***

## §1 全站响应壳统一（RespWrap 幂等中间件）

**权威规约**：所有命中中间件的 `application/json` 响应统一为三层壳 `{code, message, data}`；
**body 已是壳（`code`+`message`+`data`** **三键齐备）→ 原样透传，绝不二次包裹。**

| 条件                                                                                                 | 处理       | 结果                                        |
| -------------------------------------------------------------------------------------------------- | -------- | ----------------------------------------- |
| 白名单前缀（`/docs /health /metrics /openapi.json /favicon.ico`）或特殊内容类型（SSE / 文件 / 图片 / text/html/plain） | 原样透传     | 不包壳                                       |
| 2xx 且 body **已是壳**（三键齐备）                                                                           | 幂等透传     | 单层壳                                       |
| 2xx 且 body 为裸 DTO / 裸 dict                                                                         | 统一包壳     | `{code:0, message:"ok", data:<原体>}`       |
| 非 2xx 且已是壳                                                                                         | 幂等透传     | 不变                                        |
| 非 2xx 裸体                                                                                           | 按状态码映射壳化 | `{code:<码>, message:<detail>, data:null}` |

**幂等判定方法（关键防误判）**：壳判定用「三键齐备」而非「仅含 code」。因为 `/api/coding/challenges/{code}` 等业务 DTO
顶层自带 `code` 字段（题目代码），仅查 `code` 会被误判为已壳而**漏包**。实现见 `app/middleware/resp_wrap.py:127-133 _is_shell`。
实测 `/api/coding/challenges` → `{code:0,... data:{...}}` 正常包壳。

**幂等边界（写进契约，交 CDC 核验）**：

- 已 `ok()` 端点（`/api/auth/me`、`/api/progress/dashboard` 等）`data` 为普通对象**非嵌套壳**（实测 `auth/me` data 为对象，未二次包裹）。

- `/health` 属白名单，按设计不包壳（裸体）。

***

## §2 `GET /api/users/me` 新契约（snake\_case，role 字符串枚举）

替换旧裸 dict + camelCase 混合（`id/roles/tenantId/learningGoal/subjectPreferences`）。

**`data`** **字段（实测 student user\_id=1）**：

| 字段                                                         | 类型                 | 实测值                                                                                                                               | <br />  | <br />  | <br />   |
| ---------------------------------------------------------- | ------------------ | --------------------------------------------------------------------------------------------------------------------------------- | ------- | ------- | -------- |
| `user_id`                                                  | int                | `1`                                                                                                                               | <br />  | <br />  | <br />   |
| `account`                                                  | str                | `user000001`                                                                                                                      | <br />  | <br />  | <br />   |
| `username`                                                 | str                | `edu_user_000001`                                                                                                                 | <br />  | <br />  | <br />   |
| `nickname`                                                 | str                | `小柚子同学`                                                                                                                           | <br />  | <br />  | <br />   |
| `role`                                                     | str 枚举             | `student`（\`student                                                                                                               | teacher | manager | admin\`） |
| `email` / `mobile` / `real_name` / `gender` / `avatar_url` | str                | `user000001@edu.example.com` / `13900000001` / `杨怡骏` / `female` / `https://cdn.example.com/avatars/x.png`                         | <br />  | <br />  | <br />   |
| `learning_goal`                                            | string\[]          | `["编程入门","升学备考"]`                                                                                                                 | <br />  | <br />  | <br />   |
| `subject_preferences`                                      | string\[]（学科 code） | `["programming","math"]`                                                                                                          | <br />  | <br />  | <br />   |
| `profile`                                                  | 嵌套对象（snake\_case）  | 含 `learning_goals[]`、`subject_preferences[{preference_score,subject_code}]`、`grade_code`、`study_style`、`weekly_available_hours` 等 | <br />  | <br />  | <br />   |

**消费面**：实测 `edu-frontend/public` **11 个静态页**调用 `/api/users/me` 后判 `u.role`：achievements / chat /
community-post / community / course-detail / courses / dashboard / learning / me / my-cohorts / practice。
其中 `courses.html:740`：`if (u && (u.role === "admin" || u.role === "manager")) el.style.display = ""`（adminEntry 依赖 role）。
`me.html:4287/4289` 读 `u.learning_goal`/`u.subject_preferences`（双兼容 `|| camelCase` 兜底已含）。snake\_case 与前端消费逻辑结构回归通过（只读核对，未改 FE）。

***

## §3 交互式系壳化（真实前缀核实）

main.py 挂载：

- `quiz_router` → `/api/interactive/quiz`（`/next` `/types` `/wrong-book` …）

- `vocab_router` → `/api/vocab`（`/daily` `/recall` `/progress`）

- `coding_router` → `/api/coding`（`/challenges` …）

- `math_router` → `/api/math`（`/practice` `/step-check` `/explain`）

**实测全部包壳**（200 + `{code:0,...}`）：`/api/interactive/quiz/types`、`/api/interactive/quiz/next`、
`/api/vocab/daily`、`/api/vocab/progress`、`/api/coding/challenges`、`/api/math/practice`。
quiz `next` 的 `data` 中**无** **`correct`** **字段**（`exclude=True`，B3 服务端判分不回传答案），实测 keys 无 `correct`。

> 说明：若某交互式端点刻意保持裸（裸 DTO 特例域，如历史 audit §六.1），如实记"属裸 DTO 特例，C-A 不强制"；
> 本次抽查交互式四域**均已被 RespWrap 包壳**，无裸 DTO 特例残留，故 C-A 判定为"interactive 系壳化达成"。

***

## §4 `GET /api/progress/dashboard`（DashboardOut 扩展 D4）

实测 `?days=7` → `data` keys：`total_days / total_study_seconds / total_questions_attempted / total_questions_correct /
overall_correct_rate / active_courses_count / latest_streak_days / recent_days`。

- `total_questions_attempted=7`、`total_questions_correct=3`（`quiz_answer_session` 每作答一行）；

- `active_courses_count=2`（`student_cohort_rel` `enroll_status='active'` 计数，本次实测 2，为可变化 DB 值，仅断言"存在且 >=0"）。

***

## §5 真实 curl 清单（>=4 条，已用 urllib 实测，附 jq 等价断言）

> 每条的 HTTP+壳形状代码证据见 `test-reports/_probe_114_115.py`（登录态，21 断言 PASS）。

```
# ① users/me
GET /api/users/me   → 200 {"code":0,"message":"ok","data":{...}}
   jq 断言：.code==0 and .data.role=="student" and (.data.learning_goal|type)=="array"
            and (.data.subject_preferences|type)=="array" and [..keys[]|select(test("^[a-z_]+$"))]|length
   == keys 全部小写下划线（无 camelCase 残留）

# ② recommend/next
GET /api/recommend/next?top_n=2 → 200 {"code":0,...,"data":{"items":[{"item_code":"KP-PY-HTTP",...}],
                                   "strategy_weights":{...}}}
   jq 断言：.code==0 and (.data.items|type)=="array" and .data.items!=null

# ③ series 列表（分页裸 DTO 已包壳）
GET /api/series?page=1&page_size=2 → 200 {"code":0,...,"data":{"total":2628,"page":1,"page_size":2,"items":[...]}}
   jq 断言：.code==0 and .data.total==2628 and .data.page==1 and .data.page_size==2
            and (.data.items|type)=="array" and (.data|has("page_meta"))|not

# ④ progress/dashboard（DashboardOut 扩展）
GET /api/progress/dashboard?days=7 → 200 {"code":0,...,"data":{"total_questions_attempted":7,
                                   "total_questions_correct":3,"active_courses_count":2,...}}
   jq 断言：.code==0 and .data.total_questions_attempted>=0 and .data|has("active_courses_count")

# ⑤ 幂等对照（普通已 ok() 壳端点不应二次包裹）
GET /api/auth/me → 200 {"code":0,...,"data":{非壳对象}}
   jq 断言：.code==0 and (.data|has("code"))|not

# ⑥ 非 2xx 壳化
GET /api/users/me 带 garbage token → 401 {"code":"40101",...,"data":"sub_code=AUTH_TOKEN_INVALID"}
GET /api/nonexistent-xyz（正常 token）→ 404 {"code":"40400",...}
```

`_probe_114_115.py` 实证 21 断言 **PASS 0 FAIL**（含 ①～⑥ 全部）。

***

## §6 Middleware Chain

`Auth(get_current_user) → 业务 handler(裸 DTO / ok()) → RespWrapMiddleware 兜底
(2xx 裸体包壳 / 非 2xx 裸体壳化 / 已是壳幂等透传)`。

***

## §7 Files（实现载体，grep 行号证据）

| 文件                            | 位置                      | 说明                                                                                         |
| ----------------------------- | ----------------------- | ------------------------------------------------------------------------------------------ |
| `app/middleware/resp_wrap.py` | 全文（`_is_shell` 127-133） | RespWrap 幂等中间件：2xx 裸包壳 + 非 2xx 壳化 + SSE/白名单跳过                                              |
| `app/users/router.py`         | 39-69 `me`              | `GET /api/users/me` snake\_case 合并视图（role 字符串 + learning\_goal\[]/subject\_preferences\[]） |
| `app/progress/schemas.py`     | 88-95 `DashboardOut`    | `total_questions_attempted`/`total_questions_correct`/`active_courses_count`               |
| `app/progress/service.py`     | dashboard 实现            | 扩展字段数据源（quiz\_answer\_session / student\_cohort\_rel）                                      |
| `app/main.py`                 | include\_router 段       | 交互式挂载 `/api/interactive/quiz` `/api/vocab` `/api/coding` `/api/math`                       |

***

## §8 验收要点（CDC 核验清单）

1. 全站 JSON 2xx 统一 `{code,message,data}`，无裸 DTO；断点 `code==0`。
2. 幂等：已 `ok()` 端点 `data` 非嵌套壳；`/api/coding/challenges/{code}` 顶层 `code` 字段未致漏包。
3. `users/me` snake\_case 且 `role` 为字符串、`learning_goal`/`subject_preferences` 为 list；11 静态页 `u.role` 判定可用。
4. dashboard 含 `total_questions_attempted`、`active_courses_count`。
5. 交互式四域（quiz/vocab/coding/math）壳化实证通过；quiz `next` 不含判分答案 `correct`。
6. 已知遗留（非本任务）：`/health` 白名单裸体（按设计）；`POST /api/admin/rag/presets` 409 code 为字符串 `40900`（错误码类型历史遗留）。

