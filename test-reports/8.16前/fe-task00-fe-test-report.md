# 前端测试报告 fe-task00

> 任务：公共基础设施 + 全局设计系统（AppShell 抽取 / tokens 固化 / 校验命令 / 打靶沿用）
> 类型：最终功能测试（只测试 + 报告，未修改任何业务代码）
> 执行：fe-tester · 2026-08-13（GMT+8）
> 基线：frontend-stack.json（nextjs-16-app-router）· .claude/specs/frontend/fe-task00/frontend-spec.md + visual-acceptance.md · dev-plan.md ①-⑦ · test-reports/fe-task00-server-info.md

---

## 判定

**PASS**（fe-task00 范围全部验收通过；唯一非零为存量 lint error，按 v3 口径登记不改，不构成本 task 失败，详见遗留项 #1）

技术栈确认行：Next.js 16 + React 19 + Tailwind v4 + Zustand + TanStack Query + App Router（与画像 techStackConfirmLine、spec §平台、design-tokens.json platform 字段三者一致）

---

## 环境

| 项 | 值 |
|----|----|
| 工程目录 | `edu-frontend`（Next.js 16.3.0 / React 19.2.8 / Tailwind v4 / Vitest 4.1.10 / Playwright 1.62.1） |
| dev server | `http://localhost:3000`（npm run dev，由主编排器启动，PID 1908 运行中；未重复启动、未 kill） |
| 后端 | `127.0.0.1:8000` 运行中（真实 admin 登录链路可用） |
| 浏览器 | Playwright MCP · 1440×800 / 1280×800 / 375×667 |
| 登录账号 | admin / Admin@12345（实测可登录） |
| 基线核对 | server-info 端点探测 4×200 复验一致（/ /dashboard /login /admin/dashboard） |

---

## 验收标准逐条映射（Given/When/Then）

| # | 验收项（dev-plan ①-⑦） | 结果 | 证据 |
|---|-------------------------|------|------|
| ① | Vitest 基建核对：既有 `vitest.config.mts`/`src/test/setup.ts`/package.json `test: vitest run` 复用；首个组件测试 `AppShell.test.tsx` 跑通 | **PASS** | 基建文件在位（vitest.config.mts 19 行 jsdom+setup+@别名；setup.ts 56 行 jest-dom+next/link mock+matchMedia/ResizeObserver）；`npx vitest run` 全量 **29 文件 / 217 用例全绿**，AppShell.test.tsx 8 用例 + admin-guard.test.tsx 8 用例全绿（Duration 17.10s，日志 `test-reports/fe-task00-fe-test-vitest-run.log`） |
| ② | E2E / 打靶沿用既有 Playwright Core + 脚本化体系（不新建框架） | **PASS** | 未新建测试框架；本轮沿用 Playwright MCP 实测 localhost:3000（登录/两壳/抽屉/下拉全部浏览器实测）；⑦ 打靶主体属 be-task01，`.claude/specs/frontend/tokens/design-tokens.json` **存在**且 `platform="nextjs-16-app-router"` 正确（验收⑦确认项通过）；fe-task00 目录副本同步存在 |
| ③ | 校验命令 `npm run lint` + `npx tsc --noEmit` exit 0 | **部分 PASS** | `npx tsc --noEmit` **exit 0**（0 错误）；`npm run lint` 全量 exit 1（25 errors/25 warnings **全部位于 fe-task00 写路径之外**的存量/其他 task 文件，见静态校验表）；**fe-task00 写路径 8 文件 eslint exit 0**（`npx eslint <8 文件>` 0 输出）。按 dev-plan v3 口径「存量违规计入 fe-task07 基线，fe-task00 只登记不改」，fe-task00 范围 lint = 0 ✅ |
| ④ | AppShell 抽取 + 两壳视觉一致（12 项锚点 diff） | **PASS** | `src/components/layout/AppShell.tsx`（"use client" 纯展示壳，246 行）由两薄 layout 注入；浏览器实测两壳 12 项 DOM/class 抽查一致（品牌图标底 `from-primary-deep to-primary-strong`、激活态 `bg-gradient-to-r from-primary-deep to-primary-strong`、非激活 `text-sidebar-foreground hover:bg-sidebar-accent`、侧栏 `w-64 bg-sidebar border-sidebar-border`、顶栏 `h-14 px-4 md:px-6`、内容底 `bg-slate-100/70`、footer `text-3xs text-sidebar-foreground/60`、头像 `from-primary-deep to-primary`）；规格差异点正确：admin `contentClassName="p-4 md:p-6"`、user 默认无 padding；截图证据 `test-reports/screenshots/fe-task00/fe-tester-user-dashboard-1440.png`、`fe-tester-admin-dashboard-1440.png`；AppShell 无角色/守卫/登录特判/路由跳转逻辑（源码审计：不 import useAuthStore、不做角色判断） |
| ⑤ | tokens 固化 + 单源（globals.css + design-tokens.json 双写一致） | **PASS** | 契约 54 键（colors+typography.sizes+shadows+radius）**全部**存在于 globals.css（diff 无 only-in-contract）；关键值抽查：`--primary`=oklch(0.511 0.262 276.966)、`--ring`=oklch(0.585 0.233 277.117)、`--destructive`=oklch(0.586 0.253 17.585)、`--font-sans`=var(--font-geist-sans)（自引用修复）、`--font-heading` 同；`--text-sm-table/2xs/3xs/4xs` 四档落盘；`.dark {}` 块已删除；`@custom-variant dark` 保留为 **class 门控**（globals.css L7-13 注释明确「停用而非删除」+ 原因，符合 spec §5⑤ 保留标注分支）；全站 light-only 无 dark 验收项 |
| ⑥ | 全站禁用分功能多色与 arbitrary 色值（grep 0 违规） | **PASS** | visual-acceptance §4 五条规则逐一执行（node 精确文件级审计）：AppShell.tsx、(user)/layout.tsx、(admin)/layout.tsx、providers.tsx、query-client.ts、query-ssr.ts、auth-client.ts、AppShell.test.tsx **8 文件全部 CLEAN**（分功能多色 0、arbitrary 色值 0、arbitrary 字号 0、内联色值 0、渐变滥用 0）；语义字号 utility（text-3xs 等）正常使用 |
| ⑦ | 后端打靶沿用既有脚本模式（`*_hit.py` + `restart_uvicorn_*.py`） | **PASS** | 打靶主体属 be-task01（脚本模式已存在）；本 task 确认项：`.claude/specs/frontend/tokens/design-tokens.json` 存在（✅），后端 8000 运行中、真实数据可用（dashboard 指标 62 分钟/28 道/920 用户等实测渲染） |

---

## 单测统计（Vitest 全量）

```
Test Files  29 passed (29)
Tests       217 passed (217)
Start       14:45:46
Duration    17.10s (transform 3.58s, setup 28.28s, import 39.48s, tests 18.10s, environment 112.19s)
```

| 关键文件 | 用例数 | 结果 |
|----------|--------|------|
| `src/components/layout/AppShell.test.tsx`（验收①首个组件测试） | 8 | ✅ 全绿（渲染/激活态 matchPrefix/抽屉开关/Escape 焦点归还/关闭态 inert/桌面 md:hidden 不 inert） |
| `src/lib/admin-guard.test.tsx` | 8 | ✅ 全绿（未登录 302 带 redirect/student/teacher/manager 拦截/未知角色/admin 放行/角色大小写） |
| admin-layout.test.tsx（守卫+菜单过滤） | 4 | ✅ |
| admin-nav.test.ts（RBAC 菜单过滤） | 12 | ✅ |
| 其余 API/组件测试（community/achievement/admin/chat/learning 等） | 185 | ✅ |

> 环境提示（非失败）：vitest.config.mts:16 `__dirname` 在 configLoader:'native' 下计划弃用警告（server-info 已登记，建议后续改 `import.meta.dirname`）。

---

## 浏览器实测（Playwright · localhost:3000 · 真实 admin 登录）

### 回归 1：AppShell SSR inert 修复（本轮修正重点）

| 检查 | 结果 | 证据 |
|------|------|------|
| SSR 原始 HTML 无 inert | ✅ | `curl http://localhost:3000/dashboard` 中 `<aside id="app-sidebar" aria-label="主导航" class="...">` **无 inert 属性**（服务端初始 isDesktop=true → inert={false}） |
| 桌面端 1440 sidebar 无 inert、pointer-events auto | ✅ | `getAttribute('inert')=null`，`getComputedStyle().pointerEvents=auto` |
| 桌面端侧边栏可点击（inert 修复回归核心） | ✅ | 点击「课程中心」→ 成功跳转 /courses |
| 桌面端汉堡按钮 md:hidden（SSR/hydration 安全保留 DOM） | ✅ | openBtn className 含 `md:hidden`，desktop 不可交互 |
| 移动端 375 关闭态 inert 生效（移出 Tab 序与无障碍树） | ✅ | `hasAttribute('inert')=true`（用户端/管理端一致） |
| 移动端打开后 inert 移除 + translate-x-0 + 遮罩 | ✅ | inert=false、sidebar 含 `translate-x-0`、`.fixed.inset-0.z-30` 遮罩存在 |
| 打开聚焦首菜单项 | ✅ | 用户端「学习仪表盘」/ 管理端「仪表盘」自动聚焦 |
| Escape 关闭 + 焦点归还打开按钮 | ✅ | inert 恢复 true、aria-expanded=false、`focusedOnOpenBtn=true` |
| console error（全新导航） | ✅ | 1440 与 375 视口各 `goto /dashboard` 后 `all=false` 读 console：**0 error / 0 warning**（会话历史中的 12 条 hydration mismatch 在全新导航不复现，判定为 MCP 会话残留，风险登记见遗留项 #3） |

### 回归 2：用户下拉键盘可达（本轮修正重点，a11y HIGH 修复）

键盘全路径实测（1440 桌面）：

```
Tab×11 → BUTTON「超级管理员」（触发按钮，aria-haspopup=menu）✓
Enter  → aria-expanded=true，菜单 4 menuitem：返回仪表盘 / 个人中心 / 学习偏好 / 退出登录 ✓
Tab    → 焦点进入菜单首个 menuitem「返回仪表盘」（role=menuitem，inMenu=true）✓
Escape → aria-expanded=false，菜单恢复 invisible+pointer-events-none，焦点归还触发按钮（focusedOnTrigger=true）✓
```

- 菜单开关态样式实测：打开态稳定 `visibility:visible opacity:1`（className 经 twMerge 折叠 `invisible`→`visible`，过渡 150ms 完成）；关闭态恢复 `invisible` + `pointer-events-none`（脱离 hover 即隐藏，纯 CSS hover 能力保留）
- 点击外部（pointerdown）关闭：代码路径在 effect 中挂载（源码审计），行为与 Escape 一致

### 两壳视觉一致性抽查（AppShell 抽取验收）

| # | 对比点 | admin（实测） | user（实测） | 一致 |
|---|--------|---------------|--------------|------|
| 1 | 品牌图标底 | `from-primary-deep to-primary-strong` | 同 | ✅（无 sky） |
| 2 | 品牌文字 | `font-semibold tracking-wide text-sidebar-accent-foreground` | 同 | ✅ |
| 3 | 导航激活态 | `bg-gradient-to-r from-primary-deep to-primary-strong text-white shadow-sm` + aria-current=page | 同 | ✅ |
| 4 | 导航非激活态 | `text-sidebar-foreground hover:bg-sidebar-accent`；图标 `text-muted-foreground group-hover:text-primary` | 同 | ✅ |
| 5 | 侧边栏容器 | `w-64 bg-sidebar border-r border-sidebar-border` | 同 | ✅ |
| 6-7 | 顶栏 | `h-14 px-4 md:px-6`（+面包屑） | `h-14 px-4 md:px-6`（+问AI/用户下拉） | ✅ |
| 8 | 内容底色 | `bg-slate-100/70` | 同 | ✅ |
| 9 | 内容 padding | `p-4 md:p-6`（contentClassName 注入） | 无（user 默认，规格设计） | ✅ 符合规格 |
| 10 | 头像 | `from-primary-deep to-primary` | 同（用户下拉 avatar） | ✅ |
| 11 | footer 版权 | `text-3xs text-sidebar-foreground/60` | 同 | ✅ |
| 12 | 移动抽屉 | 375 实测：inert 关闭/打开移除/Escape 焦点归还 | 同（行为逐项一致） | ✅ |

管理端壳专项：6 导航（仪表盘/课程/题库/用户/RAG/MCP）、面包屑（管理端/仪表盘）、退出按钮、activeItem aria-current=page 均实测正确。

---

## 静态校验

| 校验 | 命令 | 结果 |
|------|------|------|
| 类型检查 | `npx tsc --noEmit` | ✅ **exit 0**（0 错误） |
| fe-task00 范围 lint | `npx eslint <AppShell.tsx AppShell.test.tsx (user)/layout.tsx (admin)/layout.tsx providers.tsx query-client.ts query-ssr.ts auth-client.ts>` | ✅ **exit 0**（0 error / 0 warning） |
| 全量 lint | `npm run lint` | ⚠️ exit 1（25 errors + 25 warnings，**全部在写路径之外**：learning/**、chat/**、ui/radio-group.tsx、lib/api/curriculum.ts、lib/api/learning.ts、me/page.tsx、courses/search/page.tsx、my-courses/** 等存量/其他 task 文件；react-hooks/set-state-in-effect、no-explicit-any 等）。v3 口径：存量违规计入 fe-task07 / 相应 task 基线，fe-task00 只登记不改 → 登记遗留项 #1 |
| grep 0 违规审计（验收⑥） | visual-acceptance §4 五规则 × 8 写路径文件 | ✅ 全部 **0 命中** |
| tokens 键集 diff（验收⑤） | 契约 54 键 vs globals.css 变量 | ✅ only-in-contract = 空；only-in-runtime 仅 `--color-*` 映射层 + `--font-sans/mono/heading`（Tailwind v4 @theme inline 标准结构，非契约键） |

---

## 遗留项（登记，不改）

1. **全量 `npm run lint` exit 1**（25 errors / 25 warnings）：全部位于 fe-task00 写路径之外（learning/chat/ui/radio-group/lib/api 等存量与其他 task 产物，主要为 react-hooks/set-state-in-effect、no-explicit-any）。按 dev-plan v3「存量违规计入 fe-task07 基线」口径，fe-task00 只登记不改；**不构成本 task 失败**。建议 fe-task07 / 各对应 task 收敛时一并清零，最终达成全仓 `npm run lint` exit 0。
2. **vitest.config.mts `__dirname` 弃用警告**（configLoader:'native' 计划默认化）：不影响当前通过；建议后续改 `import.meta.dirname`。
3. **会话历史 hydration mismatch 残留**（SSR inert `inert=""` vs 客户端 `inert={false}`）：本次全新导航（1440/375 双视口）**0 error 不复现**，判定为 Playwright MCP 会话历史残留（错误含本会话未访问的 /chat 页面）；已通过 curl 实证 SSR 输出无 inert。风险登记：若在极端多视口/路由切换场景复现，需 fe-a11y 复测跟进。
4. `@custom-variant dark` 保留为 class 门控（非删除）：注释已标注「停用而非删除 + 保留原因」，符合 spec §5⑤ 分支；全仓无 `.dark` 类启用逻辑。

---

## 测试范围说明

- 本轮只测试 + 报告，**未修改任何业务源码**；无新增测试文件（沿用既有 Vitest 体系）。
- 视觉像素级对比（对比度/断点截图矩阵/-hc/-200pct）归 fe-visual-auditor（已独立产出 `fe-task00-visual.md`）；本报告提供两壳 12 项 DOM/class 一致性证据 + 2 张 1440 截图佐证。
- 测试期间未重启 dev server（PID 1908 保持），清理职责归主编排器。
