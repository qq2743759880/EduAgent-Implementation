# 视觉审查报告 fe-task00

> 任务：公共基础设施 + 全局设计系统（AppShell 抽取 / tokens 固化 / 两壳视觉一致）
> 审查类型：Web 前端视觉审查（fe-visual-auditor）
> 审查时间：2026-08-13（GMT+8）
> 审查方式：规格驱动 + 计算样式实测（无参考图，非像素级复刻；本模型不支持读图，视觉判定以浏览器实测计算样式 + 几何测量为准）

## 环境

- 画像：frontend-stack.json → `nextjs-16-app-router`（Next.js 16.3 + React 19 + Tailwind v4 + shadcn/Base UI）
- 启动方式：复用 `test-reports/fe-task00-server-info.md`（dev :3000 localhost，startedByInfra=false，未自行启动；curl /login = 200）
- 后端：127.0.0.1:8000 运行中（admin/Admin@12345 登录成功）
- baseUrl：http://localhost:3000（server-info 指定 localhost 非 127.0.0.1，因 origin 校验）
- 工程目录：edu-frontend
- 浏览器：Playwright（headless Chromium），viewport 375/768/1024/1280/1440
- 截图目录：test-reports/screenshots/fe-task00/

## 截图清单（20 张）

| 截图 | 页面/状态 | 关键验证点 |
|---|---|---|
| login-1440.png / login-375.png | /login（登录品牌条） | 无 AppShell 残留、品牌条、375 无溢出 |
| dashboard-1440.png | /dashboard 用户壳 1440 | 8 导航、激活态、两壳基准 |
| dashboard-1280.png / dashboard-768.png / dashboard-767.png | 用户壳 1280/768（固定）/767（抽屉态） | 断点切换、无溢出 |
| dashboard-375.png | 用户壳 375 | 抽屉关闭态、无溢出 |
| dashboard-1440-hc.png / dashboard-1440-200pct.png | 用户壳 高对比 / 200% 缩放 | 对比度、无水平滚动 |
| user-drawer-375.png / user-drawer-closed-375.png | 用户抽屉 打开 / Escape 关闭 | 滑入、遮罩、焦点管理 |
| user-menu-open-1024.png | 用户下拉（CSS hover，强制显示截图） | 用户下拉可见 |
| admin-dashboard-1440.png / admin-dashboard-1280.png / admin-dashboard-768.png | 管理端壳 1440/1280/768 | 6 菜单、面包屑、内容 padding |
| admin-dashboard-375.png | 管理端壳 375 | 抽屉关闭态、无溢出 |
| admin-dashboard-1440-hc.png / admin-dashboard-1440-200pct.png | 管理端 高对比 / 200% 缩放 | 对比度、无水平滚动 |
| admin-drawer-375.png | 管理端抽屉 打开 | 滑入、遮罩、焦点管理 |
| admin-block-student-1440.png | student 直连 /admin/courses 拦截后 | 403 拦截 + 会话保留 |

> 说明：本模型不支持读取 PNG 图像，截图作为证据存档；所有视觉判定（颜色/字体/间距/渐变/几何）均通过 Playwright evaluate 读取浏览器真实计算样式（getComputedStyle / getBoundingClientRect）完成，同为真实渲染结果，非代码静态推断。

## 两壳 12 项 diff 对比（user vs admin 实测计算样式）

> 实测方式：admin 登录态分别访问 /dashboard 与 /admin/dashboard，读取 `#app-sidebar`、品牌区、导航、顶栏、main、footer、头像的 getComputedStyle 与 rect。

| # | 对比点 | 用户端 /dashboard（实测） | 管理端 /admin/dashboard（实测） | 一致 |
|---|---|---|---|---|
| 1 | 品牌区图标底 | `bg-gradient-to-br from-primary-deep to-primary-strong`；渲染 `linear-gradient(to right bottom, lab(16.13 -0.32 -14.67)=slate-800 → lab(32.45 49.22 -84.67)=indigo-700)`；32×32px、radius 14px | 完全相同（渐变起止 lab 值一致） | ✅ 收敛达成（sky 已消除） |
| 2 | 品牌区文字 | `text-sidebar-accent-foreground`；color=lab(16.13)=slate-800、font-weight 600、letter-spacing 0.4px | 完全相同 | ✅ |
| 3 | 导航激活态 | `bg-gradient-to-r from-primary-deep to-primary-strong text-white shadow-sm rounded-xl px-3 py-2.5`；渐变同 #1、text white、radius 14px、box-shadow rgba(0,0,0,0.1) 0 1px 3px + 0 1px 2px、padding 10px 12px | 完全相同 | ✅ 收敛达成（indigo-600→indigo-500 已消除） |
| 4 | 导航非激活态 | `text-sidebar-foreground hover:bg-sidebar-accent`；color=lab(7.79)=slate-900、bg none；图标 `text-muted-foreground group-hover:text-primary`=lab(48.09)=slate-500 | 完全相同 | ✅ |
| 5 | 侧边栏容器 | `w-64 bg-sidebar border-sidebar-border`；256px、bg lab(100 0 0)=纯白、border-right solid | 完全相同 | ✅ 纯白收敛（bg-white/90 半透明已消除） |
| 6 | 顶栏高度 | `h-14` = 56px | 56px | ✅ 收敛达成（h-16 → h-14） |
| 7 | 顶栏样式 | `sticky top-0 z-20 h-14 px-4 md:px-6 border-b border-border bg-background/80 backdrop-blur`；实测 sticky、z-20、bg oklab(1/0.8)、blur 8px、px 24px(≥768) | 完全相同 | ✅ 收敛达成（md:px-8 → md:px-6） |
| 8 | 内容底色 | `pageClassName="bg-slate-100/70"`；bg oklab(0.968 0.0026 0.0065/0.7)=slate-100/70 | 相同（AppShell 缺省值，admin 未覆盖） | ✅ 收敛达成（slate-50/70 → slate-100/70） |
| 9 | 内容 padding | main padding=0px（user 不传 contentClassName，**规格判据允许差异**） | main padding=24px（`contentClassName="p-4 md:p-6"`） | ✅ 符合验收判据（admin 传、user 默认无） |
| 10 | 头像/图标渐变 | `bg-gradient-to-br from-primary-deep to-primary`；lab(16.13)→lab(38.40 52.61 -92.39)=slate-800→indigo-600、28px、text white、radius 全圆 | 完全相同 | ✅ 收敛达成（sky 已消除） |
| 11 | footer 版权 | `text-3xs text-sidebar-foreground/60`；font-size 11px、color oklab(0.208/0.6)=slate-900/60 | 完全相同 | ✅ 收敛达成（text-slate-400 → sidebar-foreground/60） |
| 12 | 移动端抽屉 | 打开：translate 0px/left 0 + `shadow-drawer` + 遮罩 `bg-slate-900/30` + inert 移除 + 焦点入首菜单(/dashboard)；Escape：inert 恢复 + 焦点归还「打开导航」 | 打开：translate 0px/left 0 + shadow-drawer + 遮罩 + inert 移除 + 焦点入首菜单(/admin/dashboard)；Escape：同 | ✅ 行为一致 |

**结论：12 项全部一致（#9 padding 差异为规格判据内的预期差异），两壳 AppShell 抽取达成「管理端基准 = 全站唯一视觉语言」目标。**

> 注：headless 下 CSS transition（duration 0.2s）在无持续帧时不推进（getAnimations currentTime 停滞），强制 rAF 后 translate 正常到达 0px；此为 headless 渲染伪影，非应用 bug（真实浏览器连续帧下过渡正常）。

## tokens 生效验证（验收⑤，grep + 运行时）

| 检查项 | 契约值（design-tokens.json / visual-acceptance §3） | globals.css 实测 | 运行时实测（computed） | 判定 |
|---|---|---|---|---|
| --primary | oklch(0.511 0.262 276.966) = indigo-600 | ✅ globals.css:84 | lab(38.4% 52.6 -92.4)（indigo-600 等效） | ✅ |
| --ring | oklch(0.585 0.233 277.117) = indigo-500 | ✅ globals.css:106 | lab(48.3% 38.3 -82.0) | ✅ |
| --destructive | oklch(0.586 0.253 17.585) = rose-600 | ✅ globals.css:98 | lab(49.2% 81.6 36.0) | ✅ |
| --primary-strong / -deep | oklch(0.457 0.24 277.023) / oklch(0.279 0.041 260.031) | ✅ :87-88 | 品牌/激活渐变实际渲染使用 | ✅ |
| --font-sans 自引用修复 | var(--font-geist-sans) 非 var(--font-sans) | ✅ globals.css:18 | body font-family = "Geist, Geist Fallback"（**非 Times New Roman**） | ✅ |
| --font-heading | var(--font-geist-sans) | ✅ globals.css:20 | — | ✅ |
| dark 处置 | 无 .dark 启用逻辑（light-only） | ✅ `@custom-variant dark` 保留为 class 门控 + 注释声明（design-options §4 允许） | html 无 .dark class，dark:* 永不生效 | ✅ |
| 字号 --text-3xs | 0.6875rem = 11px | ✅ globals.css:63 | footer 实测 font-size 11px | ✅ |
| 圆角 --radius-xl | calc(0.625rem*1.4) = 14px | ✅ globals.css:71 | 品牌图标/激活导航 radius 14px | ✅ |

**变量名全集**：`grep -oE '\-\-[a-z0-9-]+'`（契约 JSON vs globals.css）—— globals.css `@theme inline` + `:root` 已包含契约 colors/typography/radius/spacing/shadows 全部新增变量（primary-strong/deep/soft/soft-foreground/border、success、warning、text-sm-table/2xs/3xs/4xs、shadow-card/drawer、font-heading），无缺失。

## 发现分类

### [规格违背]（必须修正）

无。

### [浏览器行为错误]（必须修正）

无。

- 抽屉/顶栏/遮罩/焦点/Escape 全部符合 AppShell 契约（visual-acceptance #12 + 回归点）。
- 登录页 isAuthGate：/login 无 `#app-sidebar` 残留、品牌条存在、375 无溢出 ✅。
- student 直连 admin：访问 /admin/courses → toast「无权限访问管理端」+ 重定向 /dashboard + **会话保留**（未登出，返回 /dashboard 仍登录）✅ 403 策略正确。
- admin 未登录 302：localStorage.clear 后访问受保护页 → /login?redirect=…（login 页已实测重定向行为）✅。
- 布局溢出：所有 viewport（375/768/767/1280/1440）scrollWidth ≤ clientWidth，无水平溢出；-hc 与 -200pct（zoom 200% 等效 720 视口）同样无水平滚动 ✅。

### [内容/文案]（建议修正）

- 无（本轮壳层无内容缺陷）。

### [主观建议]（不强制）

1. `user-menu-open-1024` 用户下拉为纯 CSS `group-hover`（现状保留），headless 下需强制显示才能截图；真实浏览器 hover 正常，但建议 fe-a11y 复核 hover 菜单的键盘可达性（非本轮范围）。
2. 管理端 dashboard 页面数据（metrics）为演示/打靶数据（用户总数 930、7d 活跃 0 等），与品牌页无视觉问题，仅提示数据语义由业务 task 负责。
3. 全仓存量 sky/violet/cyan/teal 分功能多色（dashboard 图标底 sky-50/violet-50、courses/community 渐变 from-indigo-600 via-violet-600 to-sky-600、my-courses tone sky）——**非 fe-task00 写路径**（grep 命中均为业务页面），按规格计入 fe-task07 基线收敛，本轮登记不改。

## 判定

- 结论：**PASS**
- 阻塞项：无
- 两壳一致性结论：**一致（12/12 项达成，含 1 项规格判据内预期差异）**
- 截图数量：20 张（test-reports/screenshots/fe-task00/）
- 报告路径：test-reports/fe-task00-visual.md

## 机器可读结论（供评测自动断言）

```json
{"taskId": "fe-task00", "result": "PASS", "blockers": []}
```
