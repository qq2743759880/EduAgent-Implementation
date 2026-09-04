# 无障碍审查报告 fe-task00（公共基础设施 + 全局设计系统）

- 审查时间：2026-08-13 14:15（GMT+8）
- 审查 agent：fe-a11y-auditor
- 审查对象：
  - `edu-frontend/src/components/layout/AppShell.tsx`（新，共享壳 + 抽屉 a11y）
  - `edu-frontend/src/app/(user)/layout.tsx`（改薄：8 导航 + 问AI/用户下拉 + footer）
  - `edu-frontend/src/app/(admin)/layout.tsx`（改薄：6 导航 + 面包屑 + 退出）
  - `edu-frontend/src/lib/auth-client.ts:351-377`（403 toast 策略）
  - `edu-frontend/src/app/globals.css`（tokens 落盘：primary/ring/destructive/muted-foreground/字号/阴影）
  - `edu-frontend/src/app/providers.tsx`（Toaster aria-live 载体）
- 标准：WCAG 2.2 AA（2.1.1 / 2.4.3 / 2.4.7 / 1.3.1 / 1.4.3 / 1.4.11 / 4.1.2 / 4.1.3 / 2.5.8 / 2.3.3）
- 实测环境：dev server `http://localhost:3000`（复用 fe-task00-server-info，PID 1908 未动）；真实后端 127.0.0.1:8000；admin/Admin@12345 真实登录
- 工具：Playwright（键盘/焦点/Tab 序/命中测试）+ axe-core 4.x（WCAG 2.x AA tags）+ canvas 颜色解析（oklch→sRGB 对比度）+ 静态源码审查

## 判定

**结论：FAIL**（存在 1 个 BLOCKER，任何 BLOCKER 即 FAIL）

**违规统计：1 BLOCKER / 2 HIGH / 1 LOW（合计 4 项，均系 WCAG 2.2 AA 违规）**

**阻塞项（必须修正后才能宣称 AA 合规）：**
1. 桌面端（≥768px）用户壳 SSR 初次加载后侧边栏残留 `inert`（hydration mismatch 未修补）→ 导航全部不可点击、不可 Tab 聚焦（WCAG 2.1.1 / 2.4.3 + 功能瘫痪）

---

## 发现表

| # | 位置 file:line | 严重度 | 原则 | 问题 | 修复建议 |
|---|---|---|---|---|---|
| 1 | `AppShell.tsx:81-83,131`（`isDesktop` 初始值 + `inert={!isDesktop && !mobileOpen}`） | **BLOCKER** | WCAG 2.1.1 Keyboard / 2.4.3 Focus Order | **桌面端用户壳 SSR 初次加载后侧边栏整体 inert**。SSR 无法求值 `window.matchMedia` → `isDesktop=false` → 服务端渲染 `inert=""`；客户端在 ≥768px 视口 hydration 时 `isDesktop=true` → React 期望移除 inert → **hydration mismatch（每页一次 console error）**，React 不修补 → DOM 残留 `inert=""`。实测 1440px 硬加载 `/chat`：`aside.inert=true`，Tab 序完全跳过 8 个导航链接与 footer「退出登录」（首个可聚焦元素是顶栏「问 AI」）；`elementFromPoint` 命中根 div（非链接）；对「课程中心」派发点击后 URL 仍为 `/chat`（不导航）。**侧边栏可见但完全不可交互**。管理端壳不受影响（AdminGuard 先渲染 Skeleton，真实 AppShell 客户端挂载，无 SSR mismatch）。移动端（<768px）服务端/客户端一致（均 inert）→ 无 mismatch、抽屉正常 | 将 `isDesktop` 初始值改为 `true`（桌面优先，与 SSR 一致）：SSR/桌面客户端均渲染无 inert → 无 mismatch、无 console error；移动端由 matchMedia effect 修正为 false → inert 正常生效。或对 `inert` 使用 `suppressHydrationWarning` + effect 驱动 |
| 2 | `(user)/layout.tsx:88-139`（问AI + 用户下拉纯 CSS hover 菜单） | HIGH | WCAG 2.1.1 Keyboard / 2.4.7 Focus Visible / 4.1.2 Name, Role, Value | 用户下拉（返回仪表盘/个人中心/学习偏好/退出登录）**仅 hover 展开，无键盘打开路径**（按钮无 onClick 切换、无 `aria-expanded`/`aria-haspopup`）；且菜单未展开时（`opacity-0 pointer-events-none`）**4 个菜单项仍以 tabIndex=0 留在 Tab 序**。实测 375px 与 1440px Tab 均依次落入 rect(111~1167, 138~262) 的不可见菜单项，键盘用户焦点「消失」在透明内容上；移动端按钮可访问名称仅为头像首字符「超」（昵称 `hidden md:inline`） | ① 菜单项在收起态加 `inert`/`hidden`（不可聚焦）；② 按钮补 `aria-expanded`/`aria-haspopup` 并用 Base UI Dropdown/Popover 提供键盘开合；③ 头像按钮补 `aria-label={nickname}`。注：frontend-spec §边界 明确「纯 CSS hover 菜单保持现状」属已登记延后项，本报告仍按 WCAG 判定违规 |
| 3 | `(admin)/admin/dashboard/page.tsx`（「平台运营总览 · 数据来自 GET /api/admin/users/dashboard/metrics」`text-sm text-slate-500`，axe `div:nth-child(1) > p`） | HIGH | WCAG 1.4.3 Contrast (Minimum) | `text-slate-500`（#64748b）14px 常规文字落在页面底色 `bg-slate-100/70`（≈#f5f8fb）上 **实测 4.47:1 < 4.5:1**（axe color-contrast serious；白底上同色 4.76:1 达标）。属 fx-task03 dashboard 页面内容（非 fe-task00 写路径），但 `slate-500 on slate-100/70` 这一组合的风险源于 fe-task00 的 `--muted-foreground=slate-500` 决策在页面底色下的边际失效 | 该段落改用 `text-slate-600`（≥7:1）或 `text-secondary-foreground`；若作为 token 级收敛（fe-task07），建议页面底色上的次级文字统一避免 slate-500，正文至少 slate-600 |
| 4 | `(user)/chat` 页 ChatPanel 输入区（`.text-muted-foreground/80`，axe 命中） | LOW | WCAG 1.4.3 Contrast (Minimum) | `text-muted-foreground/80`（slate-500 80% 透明 ≈ #77828f）对比度实测约 3.9:1 < 4.5:1。属 fx-task04 组件（非 fe-task00 写路径），仅记录备查 | 由 chat 页（fx-task04）/ fe-task07 收敛：muted 文字避免再叠 80% 透明度，或升档 |

### 非违规观察（记录备查，不计入违规数）

- **hydration mismatch console error**（与 #1 同根因）：每页面一次「A tree hydrated but some attributes…」错误（`inert=""` vs `inert={false}`），修复 #1 后自动消除。
- axe `incomplete: color-contrast`（渐变/backdrop-blur 背景无法自动判定）——已用 canvas 逐点解析复核，无隐藏违规。

---

## 实测记录

### 1. 守卫与登录流 — PASS

- 未登录访问 `/dashboard` → 约 1s 跳转 `/login?redirect=%2Fdashboard` ✓
- admin/Admin@12345 登录 → 成功 → 重定向 ✓；登录页表单控件均有可访问名称（`textbox "输入账号，或邮箱（含 @）"` / 密码 `"6 位以上"` / `checkbox "记住我"` / `button "显示密码"` / `button "登录"`）✓
- 登录页 isAuthGate 品牌条 `link "返回 EduAgent 首页"`（aria-label 传参）✓

### 2. 用户壳（/dashboard、/chat，登录态）— 语义 PASS / 桌面键盘 FAIL

- `aside` role `complementary` + `aria-label="主导航"` ✓；`nav` 内 `ul/li` 列表结构（fx-task02 #6 已修复）✓
- **恰好 8 个导航项**，激活项 `aria-current="page"` ✓（/dashboard → 学习仪表盘）
- 顶栏「问 AI」为带可见文字的 Link（可访问名称「问 AI」）✓；footer「退出登录」按钮有可见文字 ✓
- `lang="zh-CN"` ✓；`title` 唯一且描述内容（「AI 学习助手 · EduAgent」等）✓；H1 存在、无跳级 ✓
- **FAIL（#1）**：桌面 1440px 硬加载 `/chat` → `aside.inert=true`（残留），Tab 序从「问 AI」开始完全绕过侧边栏，侧边栏链接点击不导航（详见发现 #1）

### 3. 管理端壳（/admin/dashboard）— PASS

- `complementary "管理端导航"` + `nav` 6 项（`ul/li`）✓；面包屑 `nav[aria-label="面包屑"]` ✓；H1「仪表盘」✓
- 桌面 1440px：`aside.inert=false`（AppShell 客户端挂载，无 mismatch）✓；Tab 序 = DOM 序（品牌 → 仪表盘 → 课程 → 题库 → 用户 → RAG → MCP → 退出 → 内容）✓
- 移动 375px：抽屉打开 → 焦点移入首个菜单项「仪表盘」、`aria-expanded=true`、inert 移除 ✓；Escape → 关闭、焦点归还「打开导航」✓；关闭态 inert=true、屏外 ✓

### 4. 移动抽屉焦点管理（375px，用户壳）— PASS

| 检查项 | 结果 |
|---|---|
| 打开按钮 `aria-label="打开导航"` + `aria-expanded` + `aria-controls="app-sidebar"` | PASS（源码 + 实测属性一致） |
| 关闭按钮同理（`aria-label="关闭导航"`） | PASS |
| 关闭态 aside `inert` + `-translate-x-full`（屏外） | PASS（DOM `inert=true`，right=0） |
| 点击/回车打开 → inert 移除 + `translate-x-0` + 遮罩 `aria-hidden` | PASS（实测 translate=0px、right=256、`elementFromPoint` 命中链接、overlay 出现） |
| 打开后焦点移入首个菜单项 | PASS（activeElement = `学习仪表盘` link） |
| Escape 关闭 + 焦点归还打开按钮 | PASS（activeLabel=「打开导航」、inert 恢复） |
| 关闭态 Tab 序跳过侧边栏 | PASS（移动端正确；桌面端跳过是 #1 的 bug） |

> 注：会话漂移阶段曾测得打开态 translate=-100%（视觉未开），经干净会话 + CSS 探针复核（`.translate-x-0` 与 `.-translate-x-full` 并存时前者按样式表顺序生效 → 0px）判定为 MCP 会话伪影，非代码缺陷。

### 5. 键盘可达性与焦点可见性 — 部分 PASS

- 桌面管理壳 Tab 全序：`focus-visible` 全部命中——链接 `ring-2 ring-ring`（indigo-500，#6165ff，白底 4.58:1 ≥3:1）、按钮 `ring-3 ring-foreground` ✓；无 `outline` 残留冲突 ✓
- 汉堡按钮 32×32、导航项高约 40px、退出按钮 ≥28px → 全部 ≥24×24 CSS px（WCAG 2.5.8 AA）✓
- **FAIL（#2）**：用户下拉 4 个菜单项在收起态仍可 Tab 聚焦（不可见）——见发现 #2

### 6. axe-core 扫描（WCAG 2.x AA tags）

| 页面 | 违规 |
|---|---|
| /admin/dashboard（桌面） | `color-contrast` ×1（`div:nth-child(1) > p`，dashboard 段落，见 #3） |
| /chat（桌面） | `color-contrast` ×1（chat 输入区 `.text-muted-foreground/80`，见 #4） |
| /chat（移动抽屉打开态） | 同上 ×1 |
| 其余规则（landmark / aria / button-name / link-name / heading / label） | **全部通过**，无重复 landmark、无缺失 label、无 aria 冲突 |

### 7. 对比度复核（canvas oklch→sRGB，WCAG 2.2 AA）

| 元素 / token | sRGB | 对比度 | 判定 |
|---|---|---|---|
| 侧边栏非激活导航（slate-900 on 白） | #0F172A | 17.83:1 | PASS |
| 激活导航白字 on slate-800→indigo-700 渐变（最浅端 indigo-700） | #432DD7 | **8.09:1** | PASS（≥4.5；深端 14.62:1） |
| 侧边栏 footer 版权（text-3xs = 11px，slate-900@60% on 白） | #6F7480 | **4.68:1** | PASS（fx-task02 #7 的 2.63:1 已修复） |
| 品牌标题（slate-800 on 白） | #1D293D | 14.62:1 | PASS |
| 面包屑 muted-foreground（slate-500 on 白） | #62748E | 4.76:1 | PASS（≥4.5） |
| 顶栏昵称 / 退出按钮 | — | 14.62 / 17.83:1 | PASS |
| **--primary indigo-600 + 白字** | #4F39F6 | **6.46:1** | PASS（spec 问：达标） |
| --primary-strong indigo-700 + 白字 | #432DD7 | 8.09:1 | PASS |
| --destructive rose-600 on 白（text-destructive） | #EC003F | **4.53:1** | PASS（≥4.5，临界） |
| --ring indigo-500 on 白（焦点环，非文本指示） | #615FFF | 4.58:1 | PASS（≥3:1） |
| --muted-foreground slate-500 on 白 | #62748E | 4.76:1 | PASS |
| 主区 h1（slate-900 on slate-100/70） | #0F172A | 16.73:1 | PASS |
| 主区段落 slate-500 on slate-100/70 | #62748E | **4.47:1** | **FAIL（#3，0.03 差）** |

### 8. 403 toast 可达性 — PASS（静态 + 容器实测）

- sonner `<Toaster>` 容器：`aria-live="polite"` / `aria-atomic="false"` / `aria-relevant="additions text"`（实测 DOM）→ 满足 WCAG 4.1.3 Status Messages ✓
- `auth-client.ts:374` 403 分支 `toast.error("无权限", { description: "当前账号无权访问该资源" })` + `console.error`，不 logout 不跳转（D4 契约）→ 无权限提示可被读屏器读出 ✓；AdminGuard「请先登录 / 无权限访问管理端」同载体 ✓

### 9. 动效偏好

- 抽屉 transition `duration-200`；`globals.css:136-145` `prefers-reduced-motion: reduce` 全局禁用动画/过渡 ✓（WCAG 2.3.3）；无自动播放内容 ✓

---

## 结论

**判定：FAIL** — 1 BLOCKER / 2 HIGH / 1 LOW（WCAG 2.2 AA 违规 4 项）。

**好消息**：fx-task02 的全部 7 个阻塞/高优项中，抽屉焦点管理（打开移入/关闭归还/Escape/inert/aria-expanded/aria-controls）、导航 `ul/li` 语义、footer 对比度（2.63→4.68:1）、`aria-current`、焦点环均已在 AppShell 达成并通过实机复验；token 对比度整体达标（primary 6.46:1、ring 4.58:1、destructive 4.53:1）；移动端抽屉两壳行为一致且无 console 错误；403 toast aria-live 可达。

**核心问题**：`isDesktop` 初始值在 SSR 与桌面客户端不一致，导致用户壳桌面端 hydration mismatch 后侧边栏残留 `inert` —— 桌面端导航在硬加载后整体不可交互（不可点、不可 Tab），是必须优先修复的功能级 BLOCKER。修复极小（初始值改 `true` 或 effect 驱动 inert），建议修复后复测桌面端 `/dashboard`、`/chat`、`/courses` 等用户壳路由。

**次要项**：用户下拉 hover-only 菜单为已登记延后项（键盘不可开 + 不可见可聚焦项）；dashboard 段落 4.47:1 与 chat 输入区 muted/80 为页面级对比度边际违规（分别归 fx-task03/fx-task04，token 收敛归 fe-task07）。
