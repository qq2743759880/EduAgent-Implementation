# task37 遗留前端 React 批判核查修复 — 完工报告（2 项）

- 任务: task37（前端 React 批判核查修复 2 项）· 执行者: Trae sub-agent · 日期: 2026-09-05

- 范围: task59 批判①（MarkdownView 硬编码字号） + task60 批判②（MutationCache 401/403 早退一致性）

- 载体: 前端 React 实现 `edu-frontend/src/`；权威清单 `.opencode/plans/critique-backlog-tracker.md` §task37

## 结论总览

**两项均为「已修复/已实现」状态，本次核查确认无残留、无需改动。** 未生产任何 diff（空 diff），仅完成独立实证取证留档。符合任务提示的「存在已修复情形——以真实源码为准，不为了改而改」。

***

## 资产消费证据（硬约束，必填）

| 资产文件（具名路径）                                                                    | 实际调用证据                                                                               | 锚点+内核词                                       |
| ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ | -------------------------------------------- |
| `e:\stu\project\stu\EduAgent实施手册\AGENTS.md`                                   | 读取全文，第 8/9/10 条「真实契约优先/静态页注入/admin 守卫」用于判断权威来源；第 4 条「静态页注入模式」确认 fe-html 与 React 双线并存 | 消费了 AGENTS.md 的「真实契约优先 / 统一 toast 语义」        |
| `e:\stu\project\stu\EduAgent实施手册\.opencode\plans\critique-backlog-tracker.md` | 读取 §task37 两条批判项，逐条核对「修复措施/落点/验收指标」                                                  | 消费了 tracker 的「task59 批判① / task60 批判②」三段式    |
| `edu-frontend/src/components/community/MarkdownView.tsx`                      | 全文件读取，确认无 `text-[15px]`，为语义类 token                                                   | 消费了「candy token 语义类」核查内核                     |
| `edu-frontend/src/lib/query-client.ts`                                        | 全文件读取，审计 globalQueryError / globalMutationError / createQueryClient                  | 消费了「MutationCache/QueryCache onError 契约」核查内核 |
| `edu-frontend/src/components/admin/EditUserDialog.tsx`                        | 全文件读取，确认组件级零 onError 补偿                                                              | 「组件级 onError 兜底一致性」核查内核                      |
| `edu-frontend/src/lib/query-client.test.ts` + `EditUserDialog.test.tsx`       | 全文件读取，评估覆盖是否达验收                                                                      | 「401/403 全局与组件级均正确 toast」验收内核                |
| `C:\Users\Administrator\.agents\skills\tt\templates\completion-report.md`     | 读取模板，按三段式 + 批判承接核对段撰写本报告                                                             | 消费了「完工报告三段式」方法论模板                            |

> 备注：`D:\trae-projects\project_memory.md` 该路径在当前工作区映射为 `D:\.ai-hub\memory\trae-projects\EduAgent\project_memory.md`（AGENTS.md 声明），其可约束事实（前端 3000 = fe-html 静态页 + React src 双线；契约权威在后端 schemas.py）已由 AGENTS.md 覆盖并读取，本条不重复拉取本地隐藏库外的冗余文件。

***

## 逐项核查结论

### 项目 1 — task59 批判①：MarkdownView text-\[15px] 硬编码字号

- **落点**：`edu-frontend/src/components/community/MarkdownView.tsx`

- **核查结果**：**已修复，无需改动。**

- 当前组件 class 使用**语义化 candy token**：`prose-sm max-w-none text-sm leading-7 text-foreground`、`[&_pre]:text-xs`、`[&_h1]:text-xl`、`[&_h2]:text-lg`、`[&_blockquote]:text-muted-foreground`、`[&_code]:text-muted`、`[&_a]:text-primary` 等——全为语义字号类（text-sm/text-xs/text-xl/text-lg）与语义色类，**无任何** **`text-[15px]`** **类硬编码任意值字号**。

- **实证**：

  - `git grep "text-\[15px\]" -- edu-frontend/` → 唯一命中是历史报告 `edu-frontend/test-reports/task48-test-report.md:62`（`| ExamPanel 105 | text-[15px] | +1 |` 表格里的历史取证记录），**源码 0 命中**。符合编排者预检「git grep text-\[15px] 已=0」。

- **结论**：验收指标 `grep text-[15px]=0`（以源码为准）已达成。不重复改。

### 项目 2 — task60 批判②：MutationCache 401/403 早退与组件级 onError 一致性

- **落点**：`edu-frontend/src/lib/query-client.ts` + `edu-frontend/src/components/admin/EditUserDialog.tsx`

- **核查结果**：**已修复/已统一，无需改动。**

- **全局 QueryCache onError（读操作）** `globalQueryError`：401/403 **早退静默**（console 记录），由 `api-client` 的 `onApiUnauthorized` 负责清 token + 跳登录/无权限守卫——避免读加载场景重复 toast 噪声。

- **全局 MutationCache onError（写操作）** `globalMutationError`：401/403 **不再早退**，`console.error` 后**统一 toast**（`toastApiError` 透传 message + detail）。

- **组件级 onError 一致性**：`EditUserDialog` **无任何组件级 onError 补偿**（源码无 onError 回调），说明注释明确「401/403 与其余状态码统一走全局 MutationCache onError → toast，本组件不再做任何 onError 补偿，避免双弹」。→ **全局与组件级零冲突、零漏透传、零双弹**。

- **与任务语义「401→跳登录壳、403→toast、其余→toast」核对**：401/403 的「跳登录/清 token」统一由 `api-client`（OnApiUnauthorized 壳）负责；MutationCache 对 401/403 额外 toast「本次写操作被拒」，与登出跳转职责不重叠、不成双弹。写操作 401/403 均有可见 toast（验收口径「401/403 在全局与组件级均正确 toast」）。语义一致。

- **测试覆盖**：`query-client.test.ts`（9 例）断言 mutation 401→toast 一次 / 403→toast 一次 / 403+detail 透传 / 409 非认证仍 toast；query 401/403 静默不 toast、500 toast；`createQueryClient` 端到端真实触发 mutation 401/403 各单次 toast。`EditUserDialog.test.tsx`（6 例）含「后端 40303 兜底拒绝→全局单次 toast 无双弹」「登录失效 401→全局单次 toast」。

- **结论**：验收指标（401/403 在全局与组件级均正确 toast + 测试覆盖）已达成，测试文件数与断言数已达要求。不重复改。

***

## 实证记录

| 检查         | 命令                                                                                         | 结果                                                                    |
| ---------- | ------------------------------------------------------------------------------------------ | --------------------------------------------------------------------- |
| 硬编码字号 grep | `git grep -n "text-\[15px\]" -- edu-frontend/`                                             | 源码 0 命中（唯一命中为历史报告 .md 取证记录 task48-test-report.md:62）                  |
| 单测         | `npx vitest run src/lib/query-client.test.ts src/components/admin/EditUserDialog.test.tsx` | **15/15 PASS**（query-client 9 + EditUserDialog 6；Test Files 2 passed） |
| 类型检查       | `npx tsc --noEmit`                                                                         | **退出 0，无错误**                                                          |
| git 状态     | `git status --short -- <3 目标文件>`                                                           | 空（无未提交改动，工作区干净）                                                       |

***

## 完工前自检（critique 三视角）

| 检查视角            | 发现                                                              | 处置      |
| --------------- | --------------------------------------------------------------- | ------- |
| 交互态（正常/空/错误/边界） | 无发现：Markdown 渲染用语义字号已统一；编辑弹窗 401/403 由全局 MutationCache 单次 toast | 无需修（已测） |
| 边界（输入/输出/权限/超时） | 无发现：全局与组件级错误透传已统一、无双弹；lastAdmin 红线仍走前端禁用+后端 40303 兜底            | 无需修（已测） |
| 错误反馈（用户/下游可见）   | 无发现：401 跳登录壳／403 与其余均 toast，read 场景 401/403 静默降噪（符合差异单②语义）      | 无需修（已测） |

> 结论：自检无发现，本批为「核查取证」性质，未新增代码即无新增风险面。

***

## GWT 逐条自查（对应当前 tracker 验收口径）

| 验收项（§task37 tracker）                                                       | 结果    | 证据                                                                                                                                                                    |
| -------------------------------------------------------------------------- | ----- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| task59 批判①：MarkdownView 替换 text-\[15px] 为 candy token；`grep text-[15px]=0` | ✅ 已存在 | `git grep text-\[15px\]` 源码 0；MarkdownView\.tsx 用 `prose-sm/text-sm/text-xs/text-xl` 语义类，无硬编码任意值                                                                      |
| task60 批判②：审计全局 MutationCache 与 EditUserDialog onError，统一透传；补测试            | ✅ 已实现 | query-client.ts `globalMutationError` 401/403 统一 toast、`globalQueryError` 读侧静默；EditUserDialog 组件级零 onError；`query-client.test.ts` 9 例 + `EditUserDialog.test.tsx` 6 例 |
| 401/403 在全局与组件级均正确表现                                                       | ✅     | 15 用例覆盖 mutation 401/403 toast 单次、query 401/403 静默、组件级无双弹                                                                                                             |
| 测试覆盖（vitest run 指定两文件）                                                     | ✅     | `npx vitest run ... q` → 15/15 PASS                                                                                                                                   |
| 类型安全                                                                       | ✅     | `npx tsc --noEmit` 退出 0                                                                                                                                               |

***

## 批判承接核对

| tracker 项                               | 完成证据                                                                                                                                                                                               |
| --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| task59 批判①（MarkdownView text-\[15px]）   | 已存在自取证：`MarkdownView.tsx` 全语义字号类（text-sm/prose-sm/text-xs/text-xl/text-lg）+ `git grep text-\[15px\]` 源码=0 ✅（复验，非本次改动）                                                                              |
| task60 批判②（MutationCache 401/403 早退一致性） | 已存在自取证：`query-client.ts` 全局 MutationCache onError 401/403 统一 toast（注释标注 task37 差异单②）；`EditUserDialog.tsx` 组件级零 onError；`query-client.test.ts`（9）+ `EditUserDialog.test.tsx`（6）双测 15/15 ✅（复验，非本次改动） |
| 无未完成项                                   | 本批两条批判项均核对通过，无 ❌                                                                                                                                                                                   |

***

## 遗留问题 / 待确认

1. **历史报告残留**：`edu-frontend/test-reports/task48-test-report.md:62` 仍有 `text-[15px]` 字样（为该历史报告的取证表格记录，非源码，不影响 `grep=0` 验收；属测试报告归档内容，不建议删除）。
2. 上述两批判项的 React 侧完成证据对应的原始 commit 集由更早批次（task69 FE baseline `592c926`）一次性入库——本批为复验确认，无新增 commit 需求；空 diff 符合「已修复不重复改」纪律。
3. 未发现需派新任务的缺口。

