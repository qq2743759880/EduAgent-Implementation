# 完工报告：critique-task69 E2E 批判项（可行性评估 + 已有覆盖核查）

> 任务类型：task69 E2E 批判 4 项「可行性评估 + 现有覆盖核查」，严格 TT 纪律（独立执行 / 资产消费证据 / 三段式完工）。
> 日期：2026-09-05 ｜ 范围：仅前端 React（`edu-frontend/src`）+ 共享 `public/edu-api.js` 相关逻辑
> 硬性前提：`AGENTS.md` 明确「禁用 Playwright」，接口验收走 requests/curl/现有 pytest 契约测试真实 HTTP；前端行为用 vitest（jsdom）替代浏览器截图/交互。故本任务**不硬造 Playwright 用例**，改为对每项给出无 Playwright 的现实替代验收方案，并核查/补齐单测。

---

## 一、目标
对 `critique-backlog-tracker.md` §task69 的 4 条 E2E 批判项，逐项给出：
1. 当前代码实际状态（已实现 / 已有覆盖 / 缺口）
2. 不依赖 Playwright 的现实验收方案（具体到单测文件 / 断言 / 命令）
3. 是否已有测试覆盖（跑 vitest 取证）
并对「值得补」的缺口实现最小相关单测跑通；对「题型切换旧选项残留」的真实缺口做了最小修复 + 补测。

## 二、资产消费证据（本任务读取/核实并据此判定的资产）
- `.opencode/plans/critique-backlog-tracker.md` §task69（4 项权威清单与验收指标）
- `AGENTS.md`（禁用 Playwright / 前端 vitest 命令 / 前端静态页契约来源规则）
- 源码：`edu-frontend/src/lib/auth-client.ts`（zustand store：setAuth/hydrate/logout/localStorage keys `edu:auth:*`）、`api-client.ts`（拦截器/onApiUnauthorized/401 清理跳转）、`redirect.ts`（isSafeRedirect 正则）、`components/auth/LoginForm.tsx`、`components/admin/QuestionForm.tsx`、`components/admin/QuestionDetailEditor.tsx`、`components/learning/QuizPanel.tsx`
- 既有测试：`redirect.test.ts`、`api-client.test.ts`、`QuestionForm.test.tsx`、`admin/questions/[id]/page.test.tsx`、`admin-guard.test.tsx`
- 既有 Playwright 用例（不运行，仅作「原验收设想的意图蓝本」参考）：`e2e/01-auth-persistence.spec.ts`、`e2e/02-redirect-query.spec.ts`、`e2e/04-preview-consistency.spec.ts`
- vitest 配置：`vitest.config.mts`（jsdom、globals、`src/**/*.test.{ts,tsx}`）

## 三、逐项结论（4 项）

### 项1｜task42 批判① 登录态持久化 / 刷新 / 多标签 / 登出
- **代码现状（已实现）**：`auth-client.ts` store 用 `localStorage`（键 `edu:auth:token|refresh|me|tenant`）；`setAuth(persist:true)` 写库；`hydrate()` 客户端启动时恢复（`providers.tsx` useEffect 调一次）；`logout()` 清 4 键 + 置空 state；`api-client` 拦截器对业务接口 401 触发全局登出并跳 `?redirect=当前路径`，403 保守会话。
- **已有覆盖**：`api-client.test.ts` 覆盖「业务接口 401 触发全局回调 / 认证接口 401 不触发 / 断网 0 状态」，但**没有** store 层持久化/刷新/登出往返测试。
- **替代验收方案（已实现单测）**：`src/lib/auth-client.test.ts`（4 用例）——用真实 zustand store + jsdom localStorage 做存储往返：
  - setAuth → 四键写入 localStorage；
  - 模拟刷新（仅清内存态、留 localStorage）→ hydrate() 恢复 → `isAuthenticated()=true`；
  - 多标签共享 = localStorage 同源共享语义还原（jsdom 单环境无法真开标签，以「保留 localStorage 的 hydrate 恢复」代表新标签复用会话）；
  - logout({silent}) → 四键清空 + state 空 + `isAuthenticated()=false`。
- **缺口判定**：store 持久化当时无测试（现补齐）。

### 项2｜task42 批判② redirect 含 query 深层路由回跳（`/login?redirect=/admin/users?page=2`）
- **代码现状（已实现）**：`LoginForm` 从 `useSearchParams().get("redirect")` 取原始值，经 `isSafeRedirect` 校验后 `router.replace(redirect)`；`redirect` 是整条含 query 的字符串，query 天然保留。`redirect.ts` 正则 `^\/(?![/\\])[A-Za-z0-9?=&/%-_@+.~#]*$` 放行 `?`/`=`/`&`（既防协议相对，又允许带 query 站内路径）。
- **已有覆盖**：`redirect.test.ts`（8 用例）覆盖 isSafeRedirect 安全性（含 `/dashboard?tab=progress#section` 放行），但**没有** LoginForm 组件级「登录成功回跳 URL 含 query」断言。
- **替代验收方案（已实现单测）**：`src/components/auth/login-redirect.test.tsx`（3 用例）——mock `next/navigation` 路由 + `@/lib/api-client` http.post，真实 LoginForm 提交：
  - `redirect=/admin/users?page=2` → `router.replace("/admin/users?page=2")`（路径+query 完整保留）；
  - 无 redirect → `/dashboard`；
  - 非法 `//evil.com` → `/dashboard`（不拼接外部地址）。

### 项3｜task59 批判① admin QuestionDetailEditor 预览 vs 用户端 QuizPanel 渲染一致性
- **代码现状（存在真实差距）**：两组件**不共用渲染函数**。admin `QuestionDetailEditor` 的「预览」Tab 用自己的 JSX（选项为 bordered 行 + `chosen.has(key)` 高亮，判断为 √/× 行，题干/解析经 MarkdownView）；用户 `QuizPanel` 用 `AnswerBlock`（SINGLE/MULTIPLE 走 RadioGroup/Checkbox，JUDGE 对/错按钮，FILL 输入框）。二者数据模型也不同：题库 `QuestionDetail`（type_code 如 single_choice） vs P5 `QuestionOut`（mode 如 SINGLE）。Tab 标题文案「与用户端 QuizPanel 一致」但实现并非同一渲染函数。
- **已有覆盖**：`admin/questions/[id]/page.test.tsx` 只测**编辑** Tab（题型联动/解析必修/保存 payload），**没有**预览 Tab 渲染测试；也无与 QuizPanel 的对照。此批判项当时无覆盖。
- **替代验收方案（已实现单测）**：`src/components/learning/quiz-preview-parity.test.tsx`（2 用例，渲染级数据奇偶替代截图 diff）——同一道单选题（题干 + 选项 A/B + 正确答案 A）分别渲染 admin「预览」Tab 与用户 `QuizPanel`，断言两处均渲染相同题干文本 + 相同选项文本（Hello/World）+ 相同选项 key 字母（A/B），证明二者输出同一真实数据源（非硬编码）。
- **遗留（登记不改）**：完整「共用渲染函数」抽取因两份数据模型/交互形态差异较大（可编辑 vs 可作答），属较重重构，本轮不做（避免无关大幅改动）；视觉像素级一致性仍建议后端接战后由真实 HTTP 契约测试 + 后续渲染组件合并时一并收敛。当前以「同内容源奇偶」作为无 Playwright 的验收下限。

### 项4｜task59 批判② 题型切换边界（单选↔多选↔填空旧选项残留）
- **代码现状（存在真实缺口 → 已修复）**：`QuestionForm` 原 `onChange` 只 `patch("question_type", v)`，**不**清空旧 `correct_answer`，也**不**重置旧选项。真实 bug 链：单选标正确项 B → 切「填空」，`correct_answer` 仍为 "B" 且 `buildQuestionPayload` 对任意题型都带 options/correct_answer → 会以 `fill_blank` + `correct_answer="B"` 这种错构数据外传（残留）。
- **已有覆盖**：`QuestionForm.test.tsx` 原有 8 例仅覆盖纯函数/题型分发出现控件，**无**「切换清旧选项/旧答案」边界。
- **修复（最小改动）**：`QuestionForm.tsx` 新增纯函数 `applyTypeSwitch(prev, nextType)`（可单测），并把题型 select 的 onChange 从 `patch` 改为 `changeType`：
  - 旧答案格式随题型语义变化（单选 label / 多选 label / 判断"对"/"错" / 填空文本），一律清空 `correct_answer`；
  - 跨越「选择题↔非选择题」边界时重置为默认 4 空选项（防从填空切回单选带入残留选项内容）；
  - 单选↔多选互切保留已填选项（选项仍有效，仅答案语义切换）。
- **替代验收方案（已实现单测，+5 例）**：`QuestionForm.test.tsx`
  - 纯函数 4 例：单选→填空清答案；单选→填空→切回单选选项重置为 A-D 空；单选↔多选互切保留选项仅清答案；同题型/空值原样返回；
  - 组件 1 例：单选标答案 B → 切填空，填空答案输入框为空（无残留）。
- 补充：`QuestionDetailEditor`（另一管理端编辑器）choic↔choice 已有既有测试锁定「已填数据不丢」（意向保留），且其 `submitPayload()` 对非选择题 `options_json:null`（保存层不残留选项字节）；但切到填空时 `answer_text` 不清空属轻微残留风险——尊重既有测试锁定的行为，本轮不改（登记遗留）。

## 四、实证 vitest（本任务实跑）
| 命令 | 结果 |
|---|---|
| 基线（改动前）：`QuestionForm.test.tsx` + `admin/questions/[id]/page.test.tsx` | 13/13 PASS |
| 改动后 `QuestionForm.test.tsx` | 13/13 PASS |
| 新增 `auth-client.test.ts` | 4/4 PASS |
| 新增 `login-redirect.test.tsx` | 3/3 PASS |
| 新增 `quiz-preview-parity.test.tsx` | 2/2 PASS |
| 全量 `npx vitest run`（`cd edu-frontend`） | **79 文件 / 548 用例 全 PASS** |

新增用例合计 **14**（4+3+2+5），无回归。

## 五、批判承接核对（critique-backlog-tracker §task69 4 条）
| 清单项 | 完成证据 | 验收指标达成 |
|---|---|---|
| task42 批判① 登录态持久化/刷新/多标签/登出 | 代码已实现（localStorage+hydrate+logout）；补 `auth-client.test.ts` 4 例往返覆盖 | ✅ 无 Playwright 替代（jsdom 存储往返）达成 |
| task42 批判② redirect 含 query 深层回跳 | 代码已实现（整串 redirect 保留 + isSafeRedirect）；补 `login-redirect.test.tsx` 3 例 | ✅ 断言回跳 URL 完整含 `?page=2` 达成 |
| task59 批判① 预览 vs QuizPanel 一致性 | 确认无共享渲染（登记改动）；补 `quiz-preview-parity.test.tsx` 2 例渲染级奇偶 | ✅ 以「同内容源奇偶」替代截图 diff 达成（视觉全一致留遗留） |
| task59 批判② 题型切换旧选项残留 | 修复 `QuestionForm` 清晰旧答案/跨边界重置旧选项；补 5 例 | ✅ 切换无旧答案残留达成（单测锁定） |

> 说明：本任务为「可行性评估 + 现有覆盖核查」，并不追求把 4 条逐像素/逐交互打满；对「真实缺口且改动小」的项 4 做了代码修复，项 1/2/4 补齐单测，项 3 补渲染级奇偶并登记较重重构遗留。均以真实代码 + vitest 实证为准，未硬造 Playwright 用例。

## 六、遗留
1. **项3 深层**：`QuestionDetailEditor` 预览与 `QuizPanel` 未抽「共用渲染函数」，视觉像素级一致性仅由渲染级奇偶保障；建议后续（题库/答题数据模型对齐后）抽取 shared 展示组件，需另行派单。
2. **项4 次要**：`QuestionDetailEditor` 切换到非选择题时 `answer_text` 不自动清空（轻微残留），因既有测试锁定「已填数据不丢」未改；如需清空需同步改既有断言，登记为知悉项。
3. **项目硬禁 Playwright**：`e2e/*.spec.ts` 8 个文件仍在仓库（可视化蓝本），不参与运行；如促 CI 不可跑通，建议后续统一归档或标注 disabled（不在本任务范围）。