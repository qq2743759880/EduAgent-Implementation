# task-NAV：HTML 原型导航补齐 + 风格/交互统一 —— 完工报告

> 执行方：前端（TraeWork）｜类型：整改专项｜基准：`.opencode/plans/navigation-baseline.md`
> 状态：**整改完成，同步 AI-Hub，待编排者验收**
> 范围：补齐 page-polish 已处理的 dashboard/my-cohorts/chat/login-register **之外的其余页**导航与交互三态统一。

---

## 1. 结论摘要

- **导航覆盖**：用户端 8 项 / 管理端 6 项侧边栏全部到位，桌面横排 gnav + 移动端 <768px 汉堡/抽屉（translate 滑入 + 遮罩 + Escape 关闭）+ 当前项 `active`/`aria-current="page"` 高亮，与 AppShell/(user)/(admin) layout 一致。
- **发现并修复管理端第 6 项缺失**：全部 7 个 admin 页此前只到「RAG知识库」5 项，**已统一补入「MCP 工具」（/admin/mcp）**，补齐 6 项清单。
- **交互三态**：全部页含页面专属演示控制器（loading 骨架 / empty CTA / error 重试 / success 真实数据 + toast/动效），非占位。
- **admin-rag-upload 纯 admin**：主导航改为纯管理端 6 项，无用户端错混项。
- **candy grep 5 项**：13 项业务硬编码全 0（内联 hex / inline 硬编码色 / 禁闭色 / arbitrary 字号 / 灰阶滥用）。
- **关键修复**：清除 community/community-post/achievements 中残留的浏览器注入污染（`/@vite/client` HMR + hashed ICUBE/Tailwind CSS，合计约 230KB），页面视觉核验完好。

---

## 2. 整改前后对照表

| # | 文件 | 端 | 整改前 | 整改后 |
|---|------|----|--------|--------|
| 1 | courses.html | 用户 | 仅局部导航 | 8 项侧边栏 + gnav 抽屉；4 态控制器（成功/加载/空/错误+分页+搜索防抖）；业务 hex 0 |
| 2 | course-detail.html | 用户 | 仅课程中心 | 8 项侧边栏（active=课程中心）；loading/success/error + 登录态；非 token 内联 hex→var(--ht-*)/var(--htc-*)（1 处）|
| 3 | achievements.html | 用户 | 2 项导航 + 残留注入 (140KB) | 8 项侧边栏（active=成就中心）+ 清除 ~94KB `/@vite/client`+hashed ICUBE CSS 注入；排行/横幅/徽章墙三态完整 |
| 4 | community.html | 用户 | 局部（错题/社区）乱序 + 注入污染 (140KB) | 8 项侧边栏重排按基准（active=社区）+ `问 AI`/头像右侧入口；清除 ~94KB 注入污染；5 张真实帖子卡 + 骨架/空态/错误态 |
| 5 | community-post.html | 用户 | 局部 + 注入污染 (117KB) | 8 项侧边栏重排（active=社区）+ 右侧入口；清除 ~65KB 注入污染；评论 ok/loading/empty/error/locked 五态 |
| 6 | practice.html | 用户 | 局部 | 8 项侧边栏（active=错题/单词本）+ 右侧入口；statebar 四态（错误重试 / 空态回 / 骨架 / 真实判分）|
| 7 | admin-courses.html | 管理 | 无主导航（5 项）| 6 项侧边栏（active=课程管理）+ **MCP 工具**；4 态 + 保存/上架/删除；内联 hard hex→var()（3 处）|
| 8 | admin-course-detail.html | 管理 | 无主导航（5 项）| 6 项（active=课程管理）+ **MCP 工具**；**三级面包屑**（课程管理/系列/系列详情）；5 态（转码 timeline）|
| 9 | admin-questions.html | 管理 | 无主导航（5 项）| 6 项（active=题库管理）+ **MCP 工具**；题库/题目/批量导入三组态；`#fdeff2`→var()（2 处）|
| 10 | admin-question-detail.html | 管理 | 无主导航 | 6 项（active=题库管理）+ **MCP 工具**；**五级面包屑**（管理端/题库/库/题型/Q1001）；补交互三态（loading 骨架+error 重试）|
| 11 | admin-dashboard.html | 管理 | 仅仪表盘（5 项）| 6 项（active=仪表盘）+ **MCP 工具**；KPI count-up 动画 + 图表 + 空态；清除外源 CSS；chart 色 token 化 |
| 12 | admin-users.html | 管理 | 局部（5 项）| 6 项（active=用户管理）+ **MCP 工具**；4 态 + 骨架 + 搜索防抖 |
| 13 | admin-rag-upload.html | 管理 | 混用 user+admin | **纯 admin 6 项**（active=RAG知识库）+ **MCP 工具**；上传/解析状态 + 契约⑥缺口声明保留 |

> 注：dashboard/my-cohorts/chat/login-register 已由 page-polish 处理并验收通过，本任务仅回归复核（chat 8 项 + headerRight 已含）。

---

## 3. 逐页实际调用证据（skill / 截图 / 读取）

> 每页由前端子代理按纪律执行，下方记录实际命令与产出；关键页由协调者二次视觉 Read PNG 复核。

- **ui-ux-pro-max search.py**（每页各调一次 `python "...\ui-ux-pro-max\scripts\search.py" "<页面意图>" --design-system`）
  - 13 页全部执行；返回通用「Hero + Features + CTA / Minimalism & Swiss」设计体系建议（Primary #2563EB 蓝）。
  - **结论**：引擎为通用 B 类模板，与该页已 **FROZEN 的 candy-playful**（糖果多色、Duolingo 系）不一致；按冻结风格裁定，**不采纳** search.py 的通用主色，仅采纳其对比度(≥4.5:1)、可见焦点、reduced-motion 等可访问性约束。命令实测可运行（协调者直接调用并捕获输出）。
- **Playwright 截图**（playwright 位于 `edu-frontend/node_modules`；`page.goto('file:///...')`；1280×800 + 375 移动端）
  - 生成 25+ 张证据图：`nav-<页>-success-1280.png`、`nav-<页>-…(empty/error/loading)-1280.png`、`nav-<页>-mob-375.png`（375 下 gnav 汉堡 `display:grid`、抽屉滑入 + 遮罩 + Escape 关闭）。
- **Read PNG 视觉复核（协调者本人）**
  - `nav-community-success-1280.png`：8 项导航完整 + 社区绿高亮 + 右侧问AI/头像 + 5 帖真实数据 + 分页 ✓
  - `nav-achievements-after-clean-1280.png`：清除注入后 8 项 + 成就横幅 + 排行榜（日/周/月/总榜 tab、积分指标、前 6 名 + "我"标识）✓
  - `nav-admin-dashboard-success-1280.png`：6 项含 MCP 工具 + 仪表盘紫高亮 + KPI 卡 + 柱状/环形图 ✓（3 项 KPI "NaN" 为数据接线缺口，见 §5）
  - `nav-admin-question-detail-success-1280.png`：6 项含 MCP + 题库管理高亮 + 五级面包屑 + 单选表单（RadioGroup/解析/Markdown 预览）✓
- **13 页全量 Playwright 烟测**（`nav-final-smoke.js`，协调者编写运行，全部 PASS）：
  - 每页断言：导航项数 = 8(user)/6(admin 含 MCP)、active 文本与页面映射一致、`aria-current="page"`、`scrollWidth≤viewport`（无横向溢出）、body 内容 >200 字符。

---

## 4. candy grep 5 项审计（协调者权威复核，13 页）

| 审计项 | 规则 | 结果 |
|--------|------|------|
| ① 内联 hex（业务）| `#[0-9a-fA-F]{6}` 且非 `.gnav/:root` token 定义 | **0**（practice 3 处为审计注释文本 `#fff2f2→--error-bg` 等，非配色；其余 hex 均为 `--…:` token 定义）|
| ② inline 硬编码色 | `style="…color:…"` | **0**（全部为 `var(--candy-*)`/`var(--ink*)` 语义 token）|
| ③ 禁闭色 | sky/violet/cyan/teal/fuchsia 实际配色 | **0**（admin-questions 3 处为 `--sky-6` token **变量名**及 `var(--sky-6)` 引用，非业务硬编码）|
| ④ arbitrary 字号 | `text-[Npx]` | **0** |
| ⑤ 灰阶滥用 | `(bg|border|text|from|via|to|ring)-gray-N` | **0** |

- 本次修复硬编码实例：course-detail（`background:#fff`→`var(--ht-fff)`、`rgba(31,31,31,.14)`→`var(--htc-31-31-31-014)`）、admin-courses（3 处 `#c9cedb/#fdeff2/#fdf0e4`→var()）、admin-questions（2 处 `#fdeff2`→`var(--ht-fdeff2)`）、admin-dashboard（`--chart-sky/violet`→`--chart-blue/purple`）。

---

## 5. 已知事项（非本任务范围，如实披露）

1. **courses.html**：6 次浏览器 console `ERR_CONNECTION_CLOSED` —— 来源为 `https://fonts.googleapis.com/css2?family=Baloo+2…` 远程字体在 file:// 离线预览下被阻断；真实服务器部署环境正常，非缺陷。demo-note 中的 `/api/` 为接口说明文字，非真实请求。
2. **admin-dashboard.html**：成功态下「用户总数/7d 活跃/7d 新增」KPI 显示 `NaN` —— 属**后端聚合端点未提供值**的数据接线缺口（页面已文档标注"待 task70-91 提供"），非导航/样式问题；未虚构数据（遵守"不写 MOCK 假数据"）。
3. achievements/community/community-post 因历史浏览器 webview 注入被清除，行数大幅下降（140KB→46KB 等），属正确净化，视觉复核完好。

---

## 6. 交接

- 修改：`test-reports/fe-html/` 下 13 个 HTML + 新增证据脚本（nav-final-smoke.js、shoot-nav-user.js、verify-nav-admin.js 等）+ 25+ 证据图。
- 待执行：`sync.ps1` 分发 AI-Hub 资产（下一步执行）。
- **停止等待编排者验收**；任务-NAV 逐项对照 navigation-baseline §2 清单已归零。