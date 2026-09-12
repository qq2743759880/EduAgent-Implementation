# H3-temp 完工报告：manager 导航例外入口灰显（过渡措施）

- 日期：2026-09-12 ｜ 执行：前端原型工程师（独立 agent，ZCode）
- 派单依据：`.ai-hub/plans/dispatch-plan-reshape-b.md` §一 D-H3 + §二 H3-temp 行（task109 GWT③ 签字口径：例外 4 处=users/mcp/dashboard 整页+rag collections 卡；例外处理=导航灰显+横幅/诚实空态）
- 产物：`edu-frontend/public/edu-guard.js`（唯一改动文件，+17 行纯新增，0 删改）
- commit：`fix(b)/H3-temp: ...`（hash 见末节）

## 一、改动内容（资产消费证据：edu-guard.js）

| 位置 | 改动 |
|---|---|
| 头部注释 | +5 行：[H3-temp] 口径说明（三页锁定/rag 不灰显/B3-impl 落地后由横幅口径取代） |
| 新函数 `grayManagerNav()` | +11 行：遍历 `a[href]`，取文件名（剥 query/hash/路径），命中 `{admin-users, admin-mcp, admin-dashboard}.html` → `pointer-events:none + opacity:.45 + title「仅 ADMIN 可用」`；try/catch 静默兜底 |
| `requireAdmin` 通过分支 | +1 行：`if (me.role === "manager") grayManagerNav();`——admin 角色不进入 |

守卫三段（无 token 跳登录 → auth/me 校验 role∈{admin,manager} → 失败跳登录）与 `runBoot` 数据注入路径**零改动**。

## 二、独立实证（node 沙箱加载真实文件，禁 Playwright，scratch 已清理）

18/18 断言全过（脚本对 `edu-frontend/public/edu-guard.js` 原文 eval，桩 window/document/EAPI/location）：

| 组 | 断言 | 结果 |
|---|---|---|
| A manager 过守卫（8 页导航形态） | users/mcp/dashboard 三链灰显（pointerEvents=none + opacity=.45 + title）；rag/courses/questions 不灰显；**bootAdmin 仍被调用**（守卫通过后数据注入不回退） | 7/7 |
| B admin 过守卫 | 三链均不灰显、无 title 注入；bootAdmin 正常 | 4/4 |
| C href 变体 | `?query` / `/绝对路径#hash` / `https://host/...` 均命中锁定 | 3/3 |
| D student | 不过守卫：跳 /dashboard.html + 横幅，不发灰显（else 分支未受影响） | 3/3 |
| E 无 token | 第一道判定不变：跳登录带 redirect | 1/1 |

另有 `node --check` 语法通过；真实页面落点核查：8 个 admin-*.html（不含 proto）均引 edu-guard.js（guard=1）且均含 4 处例外链接（nav 3 + brand→admin-dashboard）——**灰显零页面改动即全站生效**，manager 在任一 admin 页导航均看不到可点的例外入口。

## 三、口径边界

- admin-dashboard 对 manager 灰显 ✅（metrics 403 整页无数据，属例外 4 处之一）
- rag 页不灰显 ✅（manager 可大部分使用；collections 卡例外由卡内横幅/诚实空态处理，不在本措施范围）
- 拦截性质：仅导航层禁点（title 提示）；直入 URL 的兜底 = 各例外页既有 adminOnlyBanner 横幅（admin-users 现状已实现，H2a/P1-9 口径），本措施不与其冲突

## 四、硬性守则遵守

1. 禁 DB 直写 ✅（本任务零数据操作）
2. 最小改动 ✅：仅 edu-guard.js +17 行纯新增；未改任何页面/edu-api.js/后端/contracts；后端 8000 未重启
3. 禁 Playwright ✅（node 沙箱 + grep 核查）

## 五、三视角自检

- **用户视角**：manager 登录后在 8 个 admin 页任一处，导航中 用户管理/MCP 工具/仪表盘 立即变灰且不可点，悬停语义由 title 补充（opacity .45 与原型 S1 场景视觉一致）；admin 与普通用户完全无感。
- **实施者视角（B3-impl）**：灰显样式与 B3-proto 原型 S1 的 `.is-locked` 口径逐项一致（pointer-events:none+opacity:.45+title 同文案），B3-impl 落地横幅口径后仅需移除 requireAdmin 中 1 行调用即回收本过渡措施。
- **批判者视角**：①pointer-events:none 使 title 悬停提示在多数浏览器不可触发——已知取舍，灰显+锁定的视觉语义已足够，未为此加包裹层（避免超"一行级"规模）；②灰显不改变 URL 直入行为，直入兜底依赖页面横幅（admin-users 已有；mcp/dashboard 现状横幅口径已在 H2a 批判批覆盖，非本单范围，如缺由 B3-impl/后续批次收口）；③eval 沙箱断言覆盖了守卫全部四条分支（manager/admin/student/无 token），防"改 A 破 B"。

## 六、产出物

- commit：见 `git log --grep "fix(b)/H3-temp"`（本次提交 hash 见对话输出）
- 关联：B3-proto 原型 S1 场景（commit `bfcf463`）与本措施视觉/语义同口径
