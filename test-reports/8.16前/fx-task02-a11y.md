# 无障碍审查报告 fx-task02（G2 管理端布局与权限）

- 审查时间：2026-08-13
- 审查对象：`src/app/(admin)/layout.tsx`（AdminLayout/AdminShell）、`src/lib/admin-guard.tsx`、`src/lib/admin-nav.ts`、`src/app/(admin)/admin/dashboard/page.tsx`
- 标准：WCAG 2.2 AA（含 2.1 / 2.2 中 AA 级条款）
- 实测环境：dev server `http://localhost:3000`（Next.js 16 + Tailwind v4 + shadcn/ui，真实后端 127.0.0.1:8000，admin/Admin@12345 真实登录）
- 工具：Playwright + axe-core 4.10.2（WCAG 2.x AA tag 全量扫描）+ canvas 颜色解析 + 手工键盘走查

## 审查范围

| 模块 | 页面/组件 | 覆盖维度 |
|---|---|---|
| 侧边栏导航 | 6 菜单（仪表盘/课程/题库/用户/RAG/MCP） | 列表语义、aria-current、图标/文字、对比度、键盘 |
| 移动端抽屉 | 打开/关闭按钮 + 遮罩 | aria-expanded/aria-controls、焦点管理、Escape |
| 顶栏 | 菜单按钮、面包屑、用户区、退出 | 按钮语义、aria-label、焦点 |
| 守卫重定向 | AdminGuard（未登录 / 非 admin） | toast aria-live 可达性、redirect 回跳 |
| dashboard 占位页 | `/admin/dashboard` | 标题层级、对比度（task03 组件仅提示） |

## 判定

**结论：FAIL**（存在 2 个 BLOCKER + 5 个 HIGH，任何 WCAG 2.2 AA 违规即 FAIL）

**违规统计：2 BLOCKER / 5 HIGH / 3 LOW（合计 10 项，其中 WCAG 违规 9 项）**

---

## 发现表

| # | 位置 file:line | 严重度 | 原则 | 问题 | 修复建议 |
|---|---|---|---|---|---|
| 1 | `src/app/(admin)/layout.tsx:73-79`（aside 无 inert/aria-hidden/visibility 处理） | **BLOCKER** | WCAG 2.4.3 Focus Order / 2.4.7 Focus Visible | 移动端（<md）抽屉关闭时 aside 用 `-translate-x-full` 移出屏幕，但 **8 个交互元素（logo 链接 + 关闭按钮 + 6 个菜单链接）仍留在 Tab 序列**。实测 375px 下连续 Tab：焦点依次落入 rect 为负（屏幕外）的元素（-236,16 / -244,80…-244,300），键盘用户焦点"消失"，且须连按 8 次 Tab 才能到达 DOM 靠后的"打开导航"按钮 | 抽屉关闭态给 aside 加 `inert`（或 `aria-hidden="true"` + 内层 `tabIndex={-1}` 控制），或用 `hidden`/`visibility` 真正移出可聚焦树；仅在 `mobileOpen` 时移除 inert |
| 2 | `src/app/(admin)/layout.tsx:91-99, 154-162` | **BLOCKER** | WCAG 2.4.7 Focus Visible | 点击"关闭导航"关闭抽屉后，**焦点停留在已随 aside 移出屏幕的关闭按钮上**（实测 focus=`BUTTON:关闭导航`，rect=-53,16，不可见）。下一次 Tab 又进入屏幕外元素，键盘用户迷失 | 关闭后把焦点归还到"打开导航"按钮：`onClick={() => { setMobileOpen(false); openBtnRef.current?.focus(); }}`，并配合 #1 的 inert 恢复 |
| 3 | `src/app/(admin)/layout.tsx:154-162, 91-99` | HIGH | WCAG 4.1.2 Name, Role, Value | "打开导航"/"关闭导航"按钮**缺 aria-expanded 与 aria-controls**（实测两按钮属性均为 null；打开后点击元素也无状态变化），读屏器无法获知抽屉开合状态 | `aria-expanded={mobileOpen}`、`aria-controls="admin-sidebar"`（aside 补 `id="admin-sidebar"`） |
| 4 | `src/app/(admin)/layout.tsx:70-201`（AdminShell 无键盘事件处理） | HIGH | WCAG 2.1.1 Keyboard / APG Drawer 模式 | 抽屉打开后 **Escape 无法关闭**（实测按下 Escape 后 aside 仍 visible，rect.right=256）。遮罩仅有 onClick，无键盘路径 | 抽屉打开时在 aside（或根 div）上绑定 `onKeyDown` 处理 `Escape → setMobileOpen(false)` + 焦点归还 |
| 5 | `src/app/(admin)/layout.tsx:70-201` | HIGH | WCAG 2.1.1 Keyboard / 2.4.3 Focus Order | 打开抽屉后**焦点不移入抽屉**（实测打开后 activeElement 仍为"打开导航"按钮；再 Tab 直接跳到顶栏"退出"按钮，绕过抽屉内容），键盘用户无法直接进入菜单 | 打开时聚焦抽屉内第一个元素（logo 链接或 nav 首项）；抽屉作为临时层建议配合 focus trap（或至少确保 Tab 可自然进入） |
| 6 | `src/app/(admin)/layout.tsx:102-131` | HIGH | WCAG 1.3.1 Info and Relationships | 导航 `<nav>` 的**直接子元素为 6 个 `<a>`，未使用 `<ul>/<li>` 列表结构**（实测 nav 子元素 `["A","A","A","A","A","A"]`，li 数 0），读屏器无法获得导航项列表分组语义；键盘上下方向键快速导航也不可用 | 改为 `nav > ul`，每项 `li` 内包 `Link`（`<ul className="space-y-1">` + `<li>` 包 `<Link>`） |
| 7 | `src/app/(admin)/layout.tsx:134-136` | HIGH | WCAG 1.4.3 Contrast (Minimum) | 侧边栏页脚 `© EduAgent · 管理控制台`：`text-slate-400`（lab 65.53）@11px on 白底，**实测对比度 2.63:1 < 4.5:1**（axe color-contrast serious 命中 `.px-1`） | 提升为 `text-slate-500`（4.76:1）或 `text-slate-600`（7.58:1） |
| 8 | `src/app/(admin)/layout.tsx:163-180` | LOW | WCAG 1.3.1 Info and Relationships | 页面存在两个 `navigation` landmark（aside 内 nav 无标签 + 顶栏面包屑 nav），aside 内 nav 未与面包屑区分 | 给 aside 内 nav 补 `aria-label="管理端菜单"` |
| 9 | `src/app/(admin)/layout.tsx:102-128` | LOW | WCAG 2.4.7 Focus Visible | 侧边栏链接无显式 `focus-visible` 类，焦点指示依赖浏览器默认 outline（实测 `outline: auto 0.67px`，可见但很细，且 Firefox 无 auto 双线时偏弱）；按钮已有 ring shadow 达标 | 给链接补 `focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none` 统一指示 |
| 10 | `src/app/(admin)/layout.tsx:184-186` | LOW | WCAG 1.1.1 Non-text Content | 顶栏头像字母（avatarText）无 `aria-hidden`，读屏器会读出无意义的单字符（如"超"） | 头像 span 加 `aria-hidden="true"`（昵称已有文字标签） |

### 说明（非 task02 违规，记录备查）

- `src/components/admin/MetricCards.tsx`（task03 组件，渲染于 dashboard 页）：角色分布标签 `text-slate-400 text-[11px]` 对比度 2.63:1，axe 命中 4 个节点 —— 属 task03 实现范围，建议 task03 审查时一并修复。
- 实测中发现登录后 `GlobalChatInjection`（全局注入组件）请求 `/api/chat/sessions` 若 401 会触发全局登出跳转（环境/会话问题，非 task02 布局缺陷）；真实 admin 会话下后端接口验证正常（curl 实测 token 有效）。不影响本报告结论。

---

## 实测记录

### 1. 守卫重定向流程（未登录访问 /admin/dashboard）— PASS

- 访问 `http://localhost:3000/admin/dashboard` → 约 1s 后跳转 `http://localhost:3000/login?redirect=%2Fadmin%2Fdashboard` ✓
- toast「请先登录」在 sonner 容器内弹出：
  - 容器：`<section aria-label="Notifications alt+T" aria-live="polite" aria-atomic="false" aria-relevant="additions text">`（sonner 源码 index.mjs 同源确认）✓
  - 实测容器 textContent 含「请先登录」→ **读屏器可读出，符合 WCAG 4.1.3 Status Messages** ✓
- 同机制验证 `/admin/users` → `/login?redirect=%2Fadmin%2Fusers` ✓
- console：守卫流程 **0 error / 0 warning** ✓

### 2. 侧边栏语义（桌面 1280px，admin 登录）— 部分 PASS

- `aside[aria-label="管理端导航"]` ✓；激活项 `aria-current="page"` ✓（仅"仪表盘"一项，路由切到 /admin/courses 时跟随切换，源码 `pathname === href` 逻辑正确）
- 菜单链接均有可见文字 + 图标（lucide，`aria-hidden` 由库处理），无纯图标无标签问题 ✓
- **FAIL：`nav` 无 `ul/li` 列表结构**（见发现 #6）
- 退出按钮有可见文字「退出」✓；面包屑 `nav[aria-label="面包屑"]` ✓；h1「仪表盘」存在且层级正确 ✓

### 3. 移动端抽屉（375×812，admin 登录）

| 检查项 | 结果 |
|---|---|
| 打开按钮 aria-label="打开导航" / 关闭按钮 aria-label="关闭导航" | PASS（均有 label） |
| aria-expanded / aria-controls | **FAIL**（均 null） |
| 点击打开 → 抽屉可见（aside.right=256）+ 遮罩出现（aria-hidden） | PASS |
| 打开后焦点移入抽屉 | **FAIL**（焦点停留打开按钮；Tab 跳到顶栏"退出"） |
| Escape 关闭 | **FAIL**（按下后抽屉仍打开） |
| 点击关闭 → 抽屉关闭 | PASS |
| 关闭后焦点归还 | **FAIL**（焦点停留在屏幕外关闭按钮） |
| 关闭态下 Tab 序列 | **FAIL**：Tab 第 4~11 次依次聚焦 8 个屏幕外元素（rect：logo -236,16；关闭按钮 -53,16；6 菜单 -244,80~-244,300），焦点不可见 |

### 4. 键盘与焦点可见性（桌面）

- Tab 顺序 = DOM 顺序：logo → 关闭导航(md:hidden) → 6 菜单 → 打开导航(md:hidden) → 退出 →（循环）✓（桌面宽度下 md:hidden 按钮 display:none 不参与）
- focus-visible：**全部交互元素 `:focus-visible` 命中**——链接 `outline: auto 0.67px`（浏览器默认 + 全局 `outline-ring/50` 着色），按钮 `focus-visible:ring-3 ring-ring/50` box-shadow ✓（强度见发现 #9）

### 5. axe-core 4.10.2 扫描（/admin/dashboard，WCAG 2.x AA tags）

- violations：**color-contrast ×6（serious）**——`.px-1`（sidebar footer）+ `div:nth-child(1) > p` + MetricCards 4 个角色标签（见发现 #7 与备查说明）
- incomplete：color-contrast（部分渐变/半透明背景无法自动判定，已人工用 canvas 解析复核）
- 其余规则（landmark、aria、heading、button-name、link-name 等）**全部通过**，无 label 缺失、无 aria 属性冲突、无 landmark 重复冲突

### 6. 对比度复核（canvas 解析 lab→sRGB，WCAG 2.2 AA）

| 元素 | 前景/背景 | 对比度 | 判定 |
|---|---|---|---|
| 侧边栏菜单文字（slate-600） | #475569 系 / 白 | 7.58:1 | PASS（≥4.5:1） |
| 激活菜单文字 | 白 / slate-800→indigo-700 渐变 | 7.90:1 | PASS |
| 激活菜单图标（白） | 同激活项 | 7.90:1 | PASS（≥3:1） |
| 非激活菜单图标（slate-500） | #64748b 系 / 白 | 4.76:1 | PASS（≥3:1） |
| 面包屑 / 顶栏文字（slate-500） | 白 | 4.76:1 | PASS |
| 退出按钮（slate-600） | 白 | 7.58:1 | PASS |
| 侧边栏页脚版权（slate-400 @11px） | 白 | **2.63:1** | **FAIL（需 ≥4.5:1）** |
| MetricCards 角色标签（slate-400 @11px，task03） | 白 | **2.63:1** | FAIL（task03 范围） |

### 7. 动效偏好

- 抽屉 transition 为 `duration-200`（200ms 位移），无自动播放/闪烁内容；Tailwind 动画均随 `prefers-reduced-motion` 由 tw-animate-css 处理 —— PASS

---

## 结论

**判定：FAIL** — 2 BLOCKER / 5 HIGH / 3 LOW（WCAG 2.2 AA 违规 9 项）。

**阻塞项（必须修正后才能宣称 AA 合规）：**
1. 移动端关闭态侧边栏 8 个交互元素残留 Tab 序列（2.4.3/2.4.7）→ 加 `inert` 或等价处理
2. 关闭抽屉后焦点停留在屏幕外按钮（2.4.7）→ 焦点归还"打开导航"按钮
3. 抽屉按钮缺 aria-expanded/aria-controls（4.1.2）→ 补齐
4. Escape 无法关闭抽屉（2.1.1）→ 补 Escape 键盘路径
5. 打开抽屉后焦点不移入（键盘路径断裂）→ 聚焦抽屉首元素
6. 导航缺 ul/li 列表语义（1.3.1）→ 重构为 `nav>ul>li>a`
7. 侧边栏页脚对比度 2.63:1（1.4.3）→ 升为 slate-500/600

**说明：** 桌面端体验整体良好（aria-current、focus-visible、对比度主体、守卫 toast aria-live 均达标）；全部问题集中在移动端抽屉的键盘/焦点管理和两处对比度。修复工作量小（单文件 layout.tsx + 样式类调整），建议按上表修复后复测。
