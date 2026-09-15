# T3-B 完成报告 —— 前端可见缺陷五连修（盲测 T3 批 B，fe-html 域）

> 修复工程师：独立单写者（`edu-agent/scripts/eval/t3b.lock` 持有）· 工作区：`E:\stu\project\stu\EduAgent实施手册` · 完工回执 2026-09-15
> 范围来源：`kickoff-T3B-frontend-visible-fixes.md`（B-G1~B-G5 + 回归 B-V1~V3）
> 文件归属（仅限本次）：`edu-frontend/public/{dashboard,courses,community,me,login-register}.html`、本报告、`edu-agent/scripts/eval/t3b_probe_pins.py`（只读探针，保留可复跑）
> 守则遵守：禁 Playwright；禁改 `edu-api.js`、`edu-guard.js`、`contracts/**`、`edu-agent/app/**`（后端只读）；禁新增后端契约/端点；取参一律 `EAPI.pageId(name)`；`chat.html` 本批未碰

---

## 0. 结论

五个 G 项全部闭环，逐项 GWT 实证通过；回归 B-V1（check-demo 绿 9/9，⑧ WARN 为部署前置项非本批）、B-V2（五页+根路由 curl 全 200）、B-V3（node vm 内联脚本语法 5/5 通过）。

| 项 | 主题 | 风险 | 状态 | GWT 摘要 |
|---|---|---|---|---|
| B-G1 | dashboard.html 死壳 | P1 页面不可用 | ✅ | 补 `/edu-api.js` 注入，接线 IIFE 恢复执行 |
| B-G2 | courses.html XP 假数据 | P2 数据欺骗 | ✅ | Hero 三卡接 `gamification/me/points` + `progress/dashboard`，实测 351 积分/Lv.1/打卡 0 天 |
| B-G3 | courses.html 规格文字 | P3 | ✅ | title/doc-badge/subtitle/demo-note 全清，JS 过时注释修正 |
| B-G4 | community.html 置顶重复 | P2 | ✅ | 三层根因实证；静态演示清零 + renderPosts 按 id 去重；数据层建议单列 |
| B-G5 | me/login-register 规格文字 | P3 | ✅ | me 档案 sub + login-register title/endpoint 标签/失败壳横幅全清 |
| B-V1 | 回归 check-demo | — | ✅ | 绿 9/9（⑥ 登录链路 PASS，⑧ WARN=DEBUG 虚拟管理员=部署前置项） |
| B-V2 | 五页 curl 200 | — | ✅ | dashboard/courses/community/me/login-register + `/` 全 200 |
| B-V3 | JS 语法 | — | ✅ | 5 文件全部内联 `<script>` vm 编译通过 |

---

## B-G1（P1 页面不可用）：dashboard.html 死壳修复

**现状**：整页 **0 处** `<script src="/edu-api.js">` 引入，接线 IIFE 首行 `if(!window.EAPI) return;` 静默退出 → 页面渲染静态壳后所有真实数据面板停留在骨架/空态。

**修改**（`dashboard.html`）：`</div><!-- /.glayout -->` 后、主接线 IIFE 前补 `<script src="/edu-api.js"></script>`（教训 4 注入模式）。

**GWT**：✅ 渲染路径代码走查——`/edu-api.js` 在 IIFE 之前加载；✅ 页面含 `EAPI.store.getToken()` 静默降级分支；✅ 五页 curl 200（B-V2）。

---

## B-G2（P2 数据欺骗）：courses.html Hero XP 假数据接真

**现状**：Hero 三张 stat-card 硬编码「连续打卡 **7** 天 / Lv.5 / **120 XP** / 累计 **1,280** XP」，且 `xpFill` 进度条由假动画 `setTimeout(…"62%")` 驱动。

**curl 实测**（user000001，2026-09-15）：
- `GET /api/gamification/me/points?page=1&page_size=1` → `{total_points:351, level_no:1, level_title:"萌新", level_progress_pct:70.2, next_level_min:500, logs_total:32}`
- `GET /api/progress/dashboard?days=14` → `{latest_streak_days:0, active_courses_count:2, total_study_seconds:6664}`

**修改**（`courses.html`）：
1. Hero 三卡加 id 占位（`heroStreak`/`heroLevel`/`heroXp`/`heroTotalXp`/`xpFill`），初始显示「–」不造数；
2. 新增 `loadHero()`：登录态（`EAPI.store.getToken()`）下并发请求 points + dashboard，成功回填（积分 `toLocaleString`、进度条按 `level_progress_pct` 限幅 0-100%），失败静默保持占位；
3. 删除假动画 `setTimeout(…"62%")`。

**GWT**：✅ 无任何 `120 XP / 1,280 / Lv.5 / 62%` 残留（grep 0 处）；✅ `loadHero` 数据源为真实端点且带登录态守卫；✅ 卡片 `xp-badge` 仅在后端字段存在时渲染（curl 实测列表项无 xp 字段 → 不渲染假徽章，原有行为保留）。

---

## B-G3（P3）：courses.html 规格文字清除

**修改**（`courses.html`）：
- `<title>`「效果图（task44 契约② HTML 审核版 v4 · 两级导航 + 学中玩风格 + 水平分页）」→「课程中心 · EduAgent」
- 删除 `doc-badge` 元素及其 CSS（`.doc-badge`）、`demo-note` 大段规格说明及其 CSS（`.demo-note`）
- `subtitle` 规格句 →「按学科与方向浏览课程，支持关键词搜索、价格筛选与排序」
- JS 头部注释「纯前端演示…React 实现阶段将真实请求」→ 现态「真实请求 GET /api/series（task103 接真，无演示兜底）」

**GWT**：✅ grep `doc-badge/demo-note/契约②/task44 效果图` 用户可见处 0 残留；✅ 页面可开（B-V2）。

---

## B-G4（P2）：community.html 置顶帖重复渲染

### 根因结论（三层，均实证）

**① 数据层（主根因，DB 实证）**：`community_post` 表存在 **14 条**同标题「👋 欢迎来到 EduAgent 学习社区！」置顶种子数据（id=1,4,8,12,16,20,24,28,32,36,40,44,48,74，均 `is_pinned=1`，浏览数各异）——重复插入而非单条公告。可复跑探针：`edu-agent/scripts/eval/t3b_probe_pins.py`。

**② 后端分页行为（禁改后端）**：`list_posts` 使用 `ORDER BY P.is_pinned DESC … LIMIT %s OFFSET %s`，置顶帖**并入每页**；14 条置顶 > page_size=10 → 第 1 页 10/10 全为同名置顶、第 2 页开头 4 条仍同名置顶。curl 实证：

```text
PAGE 1 | ids=[48,1,74,44,40,36,32,28,24,20]    pinned 10/10（title 分布：欢迎来到×10）
PAGE 2 | ids=[16,12,8,4,63,49,77,73,67,51]     pinned 4/4 同名（16,12,8,4）
同一 post_id 跨页重复: 无（LIMIT/OFFSET 保证）
```

即：**同一帖 id 不跨页重复**（后端无行膨胀），视觉「重复渲染」= 14 条不同 id 的同名置顶在同一/相邻页连续出现 + 页面原有静态演示帖叠加。

**③ 前端叠加源（已清零）**：`#boards` 硬编码 5 条静态演示帖 + 演示脚本 IIFE（`buildOk()` 等）无条件渲染演示列表，与真实列表叠加放大重复观感。

### 修改（`community.html`，前端仅限）
1. **静态演示清零**：`#boards`/`#pager` 置空容器；删除 5 条硬编码演示帖、`demo-note` footer、演示脚本 IIFE（`BoardsHtml/buildOk/buildLoading/buildEmpty/buildError` 及演示 chips 绑定）；
2. **按 id 去重**：`renderPosts` 入口按 `post_id` 过滤，同一帖 id 只渲染 1 次（代码注释标注根因与 curl 证据）；
3. 顺带清理 Trae inspect 注入污染（`.mine`/`#postNewDesktop` 的 `transform:matrix` 内联样式）与演示数字「我的帖子 3」→ 占位「–」（真实值由 `mine_total_posts` 回填）。

**GWT**：✅ curl 证据附上（同 id 不跨页、跨页同标题置顶=数据层）；✅ 渲染路径代码走查：同 id 去重逻辑存在（`seen/uniq`）；✅ 报告写明根因结论（前端叠加已修 + 数据层根因待数据侧）。

### 数据层建议（本批禁改后端/数据，不执行）
将 14 条同名置顶保留 1 条（如 id=1），其余 13 条 `is_pinned=0`（或删除），即可根治「首屏连排同名置顶」；同时建议社区发帖/种子脚本防重复插入。此操作需管理员/编排者授权后在 DB 层执行。

---

## B-G5（P3）：me.html / login-register.html 规格文字清理

**修改**：
- `me.html`：学员档案 `sub`「…学习目标 · 保存走 PUT /api/users/me/profile」→ 去端点尾巴；此前已清 title/数据概览/订单/收藏副标题（task54→「个人中心 · EduAgent」等）。
- `login-register.html`：
  - `<title>`「task42 原型 · /login + /register 认证页 + / 根路由」→「登录注册 · EduAgent」
  - 登录/注册 label 的 `<span class="endpoint">POST /api/auth/login|register</span>` 及 `.endpoint` CSS 删除
  - 登录失败横幅「失败壳 `"40111" · 401` — 认证类失败原地渲染…」→「请检查后重试，或切换到注册页创建新账号」
  - 注册冲突横幅「失败壳 `"40912" · 409` — 展示后端 message…」→「可尝试直接登录，或更换账号/邮箱后重试」
  - `showLoginBanner/showRegBanner` 移除 `li-banner-code`/`rg-conflict-code` 写入（元素已删，防 null 引用）

**GWT**：✅ 用户可见处 grep `/api/|task\d+|失败壳|契约|效果图` 0 残留；✅ JS 无对已删元素的引用（vm 编译 + 调用方多余参数无害）；✅ 五页 200。

---

## 回归验证（B-V1/V2/V3）

| 验证 | 结果 |
|---|---|
| B-V1 check-demo.mjs | 绿 9/9（①~⑦⑨ PASS；⑧ WARN=DEBUG 虚拟管理员探测=部署前置项 `settings.DEBUG=false`，非本批范围） |
| B-V2 五页+根路由 | `dashboard/courses/community/me/login-register.html` + `/` 全 HTTP 200 |
| B-V3 JS 语法 | node `vm.Script` 编译 5 文件全部内联 `<script>`：OK（0 fail） |

---

## 文件改动清单

| 文件 | 变更 |
|---|---|
| `edu-frontend/public/dashboard.html` | B-G1：补 `/edu-api.js` 注入 |
| `edu-frontend/public/courses.html` | B-G2：Hero 接真 + loadHero；B-G3：规格文字清除（title/doc-badge/subtitle/demo-note + JS 注释） |
| `edu-frontend/public/community.html` | B-G4：静态演示清零 + renderPosts 按 id 去重 + 注入污染清理 |
| `edu-frontend/public/me.html` | B-G5：档案 sub 规格文字清除 |
| `edu-frontend/public/login-register.html` | B-G5：title/endpoint 标签/失败壳横幅/JS 错误码引用清理 |
| `edu-agent/scripts/eval/t3b_probe_pins.py` | 只读探针（B-G4 数据层证据，可复跑） |
| `test-reports/T3B-completion-report.md` | 本报告 |

## 遗留事项
1. **数据层**：14 条同名置顶种子（community_post id 1/4/8/…/74）建议保留 1 条、其余 13 条取消置顶（需授权，DB 层执行，本批未碰后端与数据）。
2. **部署前置**：check-demo ⑧ WARN——`settings.DEBUG=true` 虚拟管理员后门，上线前必须 `DEBUG=false` 并重启后端（既有部署项，非本批引入）。
