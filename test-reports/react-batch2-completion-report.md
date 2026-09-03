# React 线批次 2 完工报告 — 用户端个人能力闭环契约对齐（C-A 壳 / correct / dim）

> 执行：子 agent ｜ 范围：`edu-frontend/src/app/(user)/` 6 页（U14 me / U4 dashboard / U13 achievements / U9 learning / U15 practice / U10 chat）
> 前置：C-A（task114 响应壳）已冻结。本批只改 `edu-frontend/`，`edu-agent/` 一律不动，未 commit。
> 禁止项核对：未触碰批1/批3路由、未重定义全局 `$`/`renderSides`、learning 题目/大纲未伪造、未 `git add .`。

---

## 1. 每页 C-A 壳审计结论（改前 / 改后）

审计口径：`Get-ChildItem -Recurse *.ts,*.tsx | Select-String -Pattern '\.data\.data|resp\.data|response\.data|\.code\b|Array\.isArray'`（需排除管理端 admin 与测试文件）。

**api-client 全局拦截器机制（前置确认）**：`edu-frontend/src/lib/api-client.ts` 成功路径拦截器对 `isEnvelope(body)`（`code`+`message`+`data` 三键齐备壳）且 `code===0` → 直接返回 `body.data`；壳但 `code!==0` → reject `ApiError`；裸形态 → 透传。所有页面经 `http.*` 调用，await 结果即**已解包的业务数据**，禁止再 `.data` 二次解包。

### U14 `/me`（me.ts / MeHeader / StatCards / StudentProfileForm）
- **改前问题（真实 C-A 残留）**：`lib/api/me.ts` 的 `MeHead` 接口仍是**旧 camelCase**（`id/roles/tenantId/learningGoal/subjectPreferences`），且 `components/me/MeHeader.tsx` 直接读 `data.avatar` / `data.learningGoal`（字符串）/ `data.subjectPreferences`。而 task114 C-A 冻结后 `GET /api/users/me`（`edu-agent/app/users/router.py:39-57` 实证）返回 **snake_case**：`user_id/account/username/nickname/role/email/mobile/real_name/gender/avatar_url/learning_goal[]/subject_preferences[]/profile`。→ 改后头像、学习目标、学科偏好会读到 undefined（功能回归）。
- **改后修复**：`MeHead` 接口重写为 C-A 权威 snake_case（`user_id` 必填、`learning_goal: string[]`、`subject_preferences: string[]`）；`MeHeader` 改读 `avatar_url`、`learning_goal.join("、")`（C-A 为数组）、`subject_preferences`。
- grep 残留核对：改前 `components/me/MeHeader.tsx` 命中 3 处 camelCase；改后该文件仅读取 snake_case，**零二次解包 / 零 `.code` / 零 `.data.data` 残留**。`me.ts` `getMe/getStudentProfile/getLearningSummary/updateProfile` 全部 `http.*` 直接返回业务体，无 `.data`。StatCards / StudentProfileForm 均无解壳残留。
- **dim 缺口如实披露（不 MOCK）**：`student_profile`（learner_identity_id / learning_goal_id / education_level_id / grade_id / industry_name / job_role_name / years_of_experience）无写入端点；`StudentProfileForm` 仅经 `PUT /me/profile` 提交可写字段（`nickname/school_name/grade_code`，实际仅存 school），其余字段保留回显 + 「展示回显」标注，表单不改写后端不支持的字段。

### U4 `/dashboard`（lib/api/dashboard.ts）
- **改前真实残留**：`getMySubjectPreferences` 降级源 `readMeSubjectPreferences` 仍读 `/api/users/me` 的 **camelCase `subjectPreferences`**（新契约已改 snake_case 顶层 `subject_preferences`）。主源 `/users/me/profile.subject_preferences` 已正确；降级分支靠 `profile.subject_preferences` 嵌套兜底，但顶层 camelCase 读取名已与 C-A 脱节（双源未收敛）。
- **改后修复**：`readMeSubjectPreferences` 收敛——优先读 C-A **snake_case 顶层 `subject_preferences`**（code 数组 → `preference_score=5`），再兼容历史 camelCase、再 `profile.subject_preferences` 嵌套。主源优先顺序不变。
- grep 残留：dashboard.ts 无 `.data`/`.code` 残留；雷达 1 组「我的能力」（后端无全班平均权威源，legend 自动隐藏）符合验收要点。

### U13 `/achievements`（lib/api/community.ts + achievement 组件）
- **改后结论：已对齐，无需改动**。`community.ts`（getMyBadges/getMyPoints/getRankings）全部 `http.*` 返回业务体，**零 `.data`/`.code` 残留**；角度一致性 `RANGE_SCOPE` 对齐 RankingScope，排行三态/积分/徽章消费正确。BadgeWall/PointOverview/PointLogList/RankingTabs 无解壳残留。
- grep 残留：仅 `PointLogList.tsx:28`、`BadgeWall.tsx:66` 为业务字段名（非解壳），无二次解包。

### U9 `/learning/[seriesId]/[sessionId]`（lib/api/learning.ts / study.ts）
- **改后结论：已对齐**。`learning.ts` 的 progress/quiz/vocab/mindmap 全部 `http.*` 返回业务体，无 `.data`/`.code`。`study.ts`（getStudyAccess/getStudyOutline）契约⑪ 门控——**题目/大纲在后端未落地前保持如实占位**（`LearningPlayClient` isError 回退报名列表 + 大纲用进度兜底标注），未伪造。事件防 500 确认：`submitVideoTicks` 传 `event_time` 语义为**本地时间字符串（无时区）**，落库避免后端时区解析 500；空 ticks 提前返回 `{saved_count:0}`。
- 主导航勾选：本批 U9 仅做 C-A progress 壳核对 + tick-batch 无时区确认，未接契⑪ 题面。

### U15 `/practice/[mode]`（QuizSession / WrongBookPanel / PracticeCenterClient）
- **correct 移除核对（改后通过）**：前端**不读题面 `correct`**——判分只走 `POST /api/interactive/quiz/submit`，消费 `SubmitAnswerOut.is_correct / correct_answer / explain_content / score`（`QuizSession.tsx:331-360` 即时判分横幅）。`QuestionOut` 无 `correct` 字段引用。
- **错题本分页核对（改后通过）**：`listWrongBook` 返回裸 `WrongBookPage {items,total,page,page_size}`，`WrongBookPanel` 从 `q.data?.items ?? []`、`q.data?.total` 正确取 `items`。
- vocab daily/recall/progress 真实；Math/Coding 占位在 `PracticeCenterClient` 为 Minimal 入口，不伪造（CandyStatRow 数据缺失显「—」）。
- grep 残留：QuizSession/WrongBookPanel 无二次解包。

### U10 `/chat`（lib/api/chat.ts）
- **改后结论：已对齐（本批补单测锁定）**。
  - **token 事件 = `delta`**（chat.ts `case "delta"` 读 `payload.delta` 累加 `finalContent`，兼容 content/answer 兜底）；`sseEventNameToKind` 把 `token` 也映射到 `delta`——**不依赖已弃用 `token` 字段**。
  - **done 解嵌套壳**：`case "message_end"` 兼容 `{code,message,data:{session_id,message_id,degraded_reason,...}}` 壳形态（`raw.data` 为对象则取 `raw.data`）。
  - **error 事件分支**：`case "error"` → throw `Error(payload.message)` → `opts.onError`。
  - **history 裸数组 + `*_json`**：`getChatHistory` 对**裸数组** `Array.isArray` 校验 + 逐条 `rag_docs_json`→sources、`mcp_tool_calls_json`→tool_calls。
- grep 残留：chat.ts 使用 axios 拦截器（非流式）走 `http.*`；SSE 走 fetch 手动解析（绕过 axios 拦截器，属正确设计，done 内嵌壳需手动解，实现了）。

---

## 2. practice correct 移除 / chat delta·done·error 消费核对（汇总）

| 核对点 | 结论 |
|---|---|
| practice 判分只走 submit | ✅ 不读题面 `correct`，消费 `submit` 响应 `is_correct/correct_answer/explain_content` |
| 错题本裸 `{items}` + status 过滤 + 分页 | ✅ `WrongBookPanel` 取 `data.items`/`data.total`，`only_not_mastered` 过滤 + `Pagination` 分页 |
| quiz submit 兜底（question_type/custom_code） | ✅ `submitAnswer` 兜底 `custom_code=q-{id}`、`question_type=SINGLE`（防 422，learning.ts:248-252） |
| chat token=delta | ✅ 只认 `delta` 累加，不依赖 token |
| chat done 解 `{code:0,data}` | ✅ `message_end` 解嵌套壳透出 message_id/session_id/degraded_reason |
| chat error 分支 | ✅ error 事件 → throw → `onError` |
| chat history 裸数组 + `*_json` | ✅ `getChatHistory` 数组校验 + 双向 `_json` 解析 |

---

## 3. me / dashboard dim 缺口的如实披露说明

- **me**：`student_profile` 维字段（learner_identity_id / learning_goal_id / education_level_id / grade_id / industry_name / job_role_name / years_of_experience）**无写入端点**；保存仅提交 `PUT /api/users/me/profile` 可写字段（school_name）。表单保留回显 + 「展示回显」标注，**不伪造后端不支持的写入**。
- **dashboard**：雷达「我的能力」为 1 组（后端无「全班平均」权威源，legend 自动隐藏）；`overall_correct_rate null` → 空文案「暂无数据」。正确率无伪造。
- 均在 handoff 标注口径下如实披露，无 MOCK 硬数据。

---

## 4. typecheck(src) + vitest 输出摘要

- **`npx tsc --noEmit`**：`src/` **0 错误**。仅预存 `e2e/*.spec.ts` + `e2e/helpers.ts` Playwright 错误（与本批无关，按任务允许忽略）。
- **`npx vitest run`**：**72 文件 493 用例全绿（493/493）**。其中本批新增：`chat.test.ts` 11→14（+3 SSE）、`dashboard.test.ts` 38（+1 C-A 双源收敛）、me 相关 4 文件 56/56。

### 受影响单测文件全绿名单
`src/lib/api/chat.test.ts`(14) · `src/lib/api/dashboard.test.ts`(38) · `src/components/me/MeHeader.test.tsx`(2) · `src/app/(user)/me/page.test.tsx`(2)。

---

## 5. 新增单测文件名与断言

- **`src/lib/api/chat.test.ts`（+3 用例）**：
  1. `chatStream SSE：delta 事件累加 content（token 字段已弃用）` — 断言 deltas=`["你好","，小柚"]`、`msg.content="你好，小柚"`（锁定 delta 累加）。
  2. `chatStream SSE：done 事件解嵌套壳 {code,message,data} → 透出 message_id/session_id` — 断言 `session_id="s_9"`、`message_id="m99"`（锁定 done 解壳）。
  3. `chatStream SSE：error 事件分支 → onError（message 透出），不产出 done` — 断言 `message="生成失败"` 且 `doneCalled` 未调用。
- **`src/lib/api/dashboard.test.ts`（+1 用例）**：
  - `getMySubjectPreferences：C-A 对齐 → /me 顶层 subject_preferences（snake_case code 数组）优先` — 断言主源无字段时降级 `/me` 顶层 snake_case → `[{subject_code, preference_score:5}]`（锁定双源收敛）。
- **同步更新**：`MeHeader.test.tsx`/`me/page.test.tsx` 的 `MeHead` mock 改为 C-A snake_case（`user_id/learning_goal[]/subject_preferences[]`），断言文字不变（昵称/学习目标/偏好标签仍渲染）。

---

## 6. 资产消费证据

| 资产类型 | 名称 | 调用/读取结果 |
|---|---|---|
| Skill | `frontend-browser-testing` | 真实加载；按其「状态矩阵覆盖」补 SSE 三态与壳对齐单测；交互/错误/空/加载矩阵已有；禁 Playwright 遵守 |
| Skill | `security` | 真实加载；semgrep 1.175.0 + gitleaks 已装并实扫；semgrep(ts/js) 对 4 个改动源码文件 0 发现；gitleaks 全仓 9 处为历史遗留（docs/html 等，非本批）；本批 8 改动文件 grep 无 AKIA/私钥/硬编码 token/secret |
| Skill | `review-bugbot` | 真实加载；**子代理启动工具在本会话不可用**，改为按 review 方法论对 uncommitted diff 手动审查 → 无发现（改前/改后 diff 见 §1/§2，逻辑与安全均健康） |
| 文档 | `react-line-replan-v2.md` §三批次2/§四、`task114-contract.md`、`AGENTS.md`、`_frontend_real_api.txt`、后端 `users/router.py` | 读取用于定位 C-A snake_case 权威契约，修正 MeHead/MeHeader/dashboard 双源 |

**security/review-bugbot 自检发现**：本批改动本身无「错误处理缺乏 / 解壳残留 / 日志泄露敏感信息 / 信任客户端回包」问题（read 客户端无写入面、SSE 错误透出 user-facing message、React 转义防 XSS）。
**review-bugbot 自检发现**：无 bugs（人工 review 无 issues）。

---

## 7. 改动文件清单（7 个，均 `edu-frontend/`）

`src/app/(user)/me/page.test.tsx` · `src/components/me/MeHeader.test.tsx` · `src/components/me/MeHeader.tsx` · `src/lib/api/chat.test.ts` · `src/lib/api/dashboard.test.ts` · `src/lib/api/dashboard.ts` · `src/lib/api/me.ts`