# task114-115 契单收口完工报告（C-A + C-B）

> 日期：2026-09-04 ｜ 执行角色：契约冻结执行 agent ｜ 工作目录：`e:\stu\project\stu\EduAgent实施手册`
> 原则：trust-but-verify，契约以真实 HTTP 抓包为准，不采信旧注释/旧报告。
> 实证实例：`127.0.0.1:8000`（live 实况）+ 契约单测（SSE 错误注入不破坏性打 live）。

---

## 1. 现状核验证据表（实质变更均在历史 commit 已落地）

| 契单项 | 契约要求 | 实测证据（8000） | commit / 载体 | 状态 |
|---|---|---|---|---|
| C-A：全站响应壳 | `{code,message,data}` + 幂等（三键齐备不二次包裹） | 21 断言 PASS；`auth/me` data 非嵌套壳（幂等） | `bdf85cd` RespWrap + W2 C1 `664774b` | ✅ 已落地 |
| C-A：users/me | snake_case + role 字符串 + learning_goal[]/subject_preferences[] | role=`student`、两列表均 list、无 camelCase keys | `app/users/router.py` | ✅ 已落地 |
| C-A：DashboardOut | `total_questions_attempted`/`active_courses_count` | 实测 attempts=7、active=2 | `app/progress/schemas.py` | ✅ 已落地 |
| C-A：interactive 壳化 | quiz/vocab/coding/math 包壳 | 六端点全 200 包壳；quiz next 无 `correct` | RespWrap | ✅ 已落地 |
| C-B：分页统一 | `{total,page,page_size,items}` 且 **无 page_meta** | series?page=1&page_size=2 → total=2628/page=1/items 数组/无 page_meta | `155b4b0` + `35b94fe` | ✅ 已落地 |
| C-B：SSE 两段式错误 | 连接前→同步 HTTP；建连后→`event:error{code,message}` | 401 实测非 SSE；token 段/落库段 error 由 `test_chat_stream_error.py` 注入实证 | `65b31a2` `chat/router.py` | ✅ 已落地 |
| C-B：token=delta | token 事件字段为 `delta` | 契约单测 (a) 累加 delta 通过 | `chat/router.py` | ✅ 已落地 |

**无任何法律缺口 → 无需最小修复、未改任何产品代码。**

---

## 2. 缺口与最小修复

- 探测脚本初版 1 处 FAIL 实为**脚本自身参数 bug**（`*req()` 把 Content-Type 传进 `expect`），非后端缺口；修正解包后 **21 断言 PASS 0 FAIL**。
- SSE 第二段 `error` 事件在 live 8000 **不稳定注入 LLM 故障**（避免污染实况/触发下游副作用），如实登记"未强制破坏性触发"，
  改用既有 W2 C3 契约单测 `tests/test_chat_stream_error.py`（httpx ASGITransport + monkeypatch）作为代码行为证据 —— 29 passed。

---

## 3. 契单产出

| 路径 | 内容 |
|---|---|
| `handoffs/task114-contract.md` | C-A 冻结单：壳规约+幂等、users/me snake_case 字段表、DashboardOut 扩展、interactive 壳化（真实前缀 `/api/interactive/quiz`）、6 条真实 curl+jq 断言、11 静态页消费方、载体文件表 |
| `handoffs/task115-contract.md` | C-B 冻结单：分页权威 `{total,page,page_size,items}`、page_meta **C2 已移除/不再二轨**、SSE 两段式（三段）错误模型、token=delta、401 实测 curl、error 事件单测证据、消费方核对 |

> 旧草案 `.ai-hub/plans/handoffs/task114-contract.md`（端口 8078、分页仍含 page_meta 兼容期）已过时，本手册 `handoffs/` 契单为准并作废旧草案语义。

---

## 4. GWT 实证

- 真实抓包脚本：`test-reports/_probe_114_115.py`（登录 student → 21 断言，覆盖 C-A/C-B 全部目标端点）。
  关键断言：`NO page_meta`、`role=="student"`、`total==2628>=0`、`dashboard 扩展字段`、`SSE 第一段=401 非 SSE` —— 全 PASS。
- 契约单测：`pytest tests/test_chat_stream_error.py tests/test_contract_task116.py tests/test_contract_task113.py` → **29 passed**（10.1s）。
- 未跑 30min 全量（遵守任务约束）。

---

## 5. 资产消费证据（读了什么、自检发现/纠正）

- 契单模板：`handoffs/task116-contract.md`（章节结构 §0 验证约束/§1 Route Spec/§错误码/§Middleware/§Files/§验收要点 参照）。
- 旧草案：`.ai-hub/plans/handoffs/task114-contract.md`、`task115-contract.md` —— 发现其 terminal 过时（端口 8078、page_meta 兼容期已被 C2 移除），未采信。
- 后端实现：`app/middleware/resp_wrap.py`（幂等三键判定 127-133）、`app/users/router.py`（me 39-69）、`app/progress/schemas.py`（88-95）、
  `app/domains/course/schemas.py`（41-47/100-106）、`app/chat/router.py`（89-129、256-364）、`app/main.py`（路由挂载）。
- 前端消费方：`public/*.html` grep —— 11 页调 `/api/users/me`、`courses.html:740` role adminEntry、
  `courses.html:573-575`/`admin-courses.html:658-684` 已读外层 triple、全 `public` `page_meta` 0 处。
- **interactive 真实前缀抓包纠正**：任务背景提示"某些 IDE 把 `api` 脱敏成 `n`、真实前缀疑似 `/api/quiz`"。
  用 urllib 直接请求实测：`/api/interactive/quiz/types`→200 包壳、`/api/quiz/next`→404，**确认真实前缀为 `/api/interactive/quiz`**
  （main.py 挂载亦证），彻底澄清脱敏疑雾 —— 契单 §0/§3 如实记载。
- 幂等边界澄清：`/api/coding/challenges/{code}` 顶层自带 `code` 字段，须「三键齐备」判定壳避免漏包（实测包壳正常）。

---

## 6. 结论

**task114/115 契单收口完成**：C-A（响应壳统一 + users/me 新契约 + DashboardOut）与 C-B（分页统一无 page_meta + SSE 两段式 error）
实质变更均已由历史 commit（`bdf85cd`/`664774b`/`155b4b0`+`35b94fe`/`65b31a2`）落地，本次通过 live 8000 真实抓包（21 断言 PASS）
与契约单测（29 passed）复验冻结，契单归档至 `handoffs/task114-contract.md`、`handoffs/task115-contract.md`。
**未改动任何产品代码、未 commit。** 唯一新增为契单两篇 + 探测脚本 `test-reports/_probe_114_115.py`（脚本工具，可复跑）。