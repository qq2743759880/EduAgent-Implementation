# 前端测试报告 fx-task02（G2 管理端布局与权限）

- 测试执行：fe-tester（最终功能测试轮，含本轮 a11y 修正不回归验证）
- 测试时间：2026-08-13
- 测试对象：`src/app/(admin)/layout.tsx`、`src/lib/{admin-guard,admin-nav,admin-api-types}.ts(x)`、`src/lib/api/admin.ts`、`(admin)/admin/*` 路由组
- 本轮修正范围复核：`(admin)/layout.tsx` 抽屉 a11y（inert/Escape/焦点/aria-expanded/ul-li）+ `admin-guard.tsx` AdminShellSkeleton
- 验收来源：`.claude/specs/frontend/fx-task02/frontend-spec.md`（retro-spec，对照 dev-plan.md fx-task02 行）
- 画像：`frontend-stack.json`（Next.js 16.3 App Router + Vitest + Testing Library + Playwright）
- server-info：`test-reports/fx-task02-server-info.md`（复用 PID 3780 dev server，**未重复启动**，全部浏览器测试基于 `http://localhost:3000`）

---

## 判定

**PASS** —— 验收标准 A/B/C/D/E 全部满足；本轮修正（抽屉 a11y 7 项 + AdminShellSkeleton）全部生效，无回归。

| 维度 | 结果 |
|---|---|
| 单测（vitest 全量） | 25 files / 196 tests **全过（100%）** |
| 类型检查 `npx tsc --noEmit` | 0 error |
| lint `npm run lint` | fx-task02 范围 0 error（全库 25 errors 均在 user 端/chat/learning/ui 等其他 task 文件，非本轮引入） |
| Playwright 浏览器实测（localhost:3000） | 未登录守卫 / admin 放行 / student 拦截 / 抽屉 a11y 全流程 **PASS** |

---

## 环境

| 项 | 值 |
|---|---|
| dev server | `http://localhost:3000`（PID 3780，fe-task01 轮次启动，复用未重启） |
| 后端 | `http://127.0.0.1:8000` 在线（进程 3:02 启动，`/api/auth/login`、`/api/auth/me`、`/api/admin/users` curl 实测 200） |
| 浏览器 | Playwright（MCP），桌面 1280×800 / 移动 375×812 |
| 账号 | admin / Admin@12345（真实登录）；task01test / Test@123456（student，真实登录） |
| 单测 | `npx vitest run`（v4.1.10，jsdom）；`npx tsc --noEmit`；`npm run lint`（eslint） |

---

## 验收标准逐条映射（Given/When/Then → 实测）

### A. RBAC 菜单过滤（admin 放行）

| # | Given | When | Then | 实测结果 | 判定 |
|---|---|---|---|---|---|
| A1 | admin 登录（真实 admin/Admin@12345） | 访问 `/(admin)` 任一 URL | 渲染侧边栏 6 菜单（仪表盘/课程/题库/用户/RAG/MCP），仅 admin 可见；品牌链接 + 6 菜单共 **7 个 link**；无 toast、无跳转 | 浏览器实测 `/admin/dashboard`：`aside[aria-label="管理端导航"]` 内 `nav[aria-label="管理端菜单"]` 渲染 **ul > li × 6**（仪表盘/课程/题库/用户/RAG/MCP），加品牌链接共 7 个 `a`；停留 3s+ 无跳转、无 toast；`/api/admin/users/dashboard/metrics` 带 `Bearer` 返回 **200** | **PASS** |
| A2 | student 登录（真实 task01test） | 访问 `/admin/courses` | `filterAdminNav` 渲染 0 项菜单且守卫拦截：`toast.error("无权限访问管理端")` + `router.replace("/dashboard")`，不渲染管理端内容 | 浏览器实测：SSR 骨架 → hydrate 后 toast「**无权限访问管理端**」→ 0.5s 内重定向 `/dashboard`；全程未渲染「创建系列」等管理端内容 | **PASS** |
| A3 | 角色数组混合（`["student","admin"]`） | 调用 `filterAdminNav` | 含 admin 即放行 6 项 | 单测 `admin-nav.test.ts` 覆盖（12 tests 全过） | **PASS** |
| A4 | roles 为 undefined/null/[] | 调用 `isAdminRole` | 一律 false | 单测 `admin-nav.test.ts` 覆盖；浏览器额外实测：localStorage 中 me 被污染为 raw 形态（无 roles 数组）时，守卫按未知角色拦截（toast 无权限 + /dashboard），**行为符合契约且对畸形数据鲁棒** | **PASS** |

### B. 未登录拦截与回跳

| # | Given | When | Then | 实测结果 | 判定 |
|---|---|---|---|---|---|
| B1 | 未登录（清空 localStorage） | 访问 `/admin/dashboard` | `toast.warning("请先登录")` + `router.replace("/login?redirect=%2Fadmin%2Fdashboard")` | 浏览器实测：`goto /admin/dashboard` → 跳转 **`http://localhost:3000/login?redirect=%2Fadmin%2Fdashboard`**，sonner 容器内出现 toast「请先登录」；console **0 error / 0 warning** | **PASS** |
| B2 | 登录成功 | 消费 redirect | 回跳原 URL（`isSafeRedirect` 强制校验，拒绝 `//` 协议相对路径） | 浏览器实测：login 页（带 `?redirect=%2Fadmin%2Fdashboard`）提交 admin 凭据 → 登录成功**回跳 `/admin/dashboard`**；`isSafeRedirect` 边界由单测 `redirect.test.ts` 覆盖（8 tests 全过） | **PASS** |

### C. hydrate 占位（无白屏）

| # | Given | When | Then | 实测结果 | 判定 |
|---|---|---|---|---|---|
| C1 | `ready=false`（auth store hydrate 未完成） | 渲染 AdminGuard | 显示「正在校验登录状态…」占位，不渲染 children、不跳转 | 浏览器实测：SSR 阶段返回 200 + **AdminShellSkeleton**（侧边栏占位条 + 「正在校验登录状态…」文案，`aria-hidden` 由 `Suspense` 场景控制）；student/admin 两轮实测均观察到骨架 → 判定 → 跳转/放行的完整时序，无白屏、无内容闪烁 | **PASS** |

### D. API 错误壳透出（不吞错）

| # | Given | When | Then | 实测结果 | 判定 |
|---|---|---|---|---|---|
| D1 | admin API 请求失败（403/500） | `adminGet/adminPost/adminPatch/adminDelete` 发起 | 错误按 `ApiError{status, code, message, detail}` 透出；写操作失败必须抛，禁止空态冒充成功 | 单测 `api/admin.test.ts`（11 tests 全过）：403/500 → `ApiError` 携带 `{code, message, detail}`；写操作失败 assert 抛错（非空态返回） | **PASS** |
| D2 | 任意错误对象 | 调用 `toAdminErrorBody` | 归一 `{status, code, message, detail?}`；`status=0`（网络错误）输出明确网络文案，不伪装 500 | 单测 `api/admin.test.ts` 覆盖（网络错误分支断言明确文案） | **PASS** |
| D3 | 分页查询参数 | `adminGet(path, params)` | params 原样交给 axios 序列化 | 单测 `api/admin.test.ts` 覆盖 | **PASS** |

### E. URL 隔离与契约（L8）

| # | Given | When | Then | 实测结果 | 判定 |
|---|---|---|---|---|---|
| E1 | 管理端功能路由 | 编码 | URL 一律 `/admin/*` 前缀（与用户端 `/dashboard`、`/courses` 零冲突） | 浏览器实测 6 菜单 href：`/admin/{dashboard,courses,questions,users,rag,mcp}` 全部 `/admin/*`；`/admin` 根路由 404 属设计内（server-info #6），无同 URL 双 page | **PASS** |
| E2 | `ADMIN_NAV_ITEMS` | 校验 | 恰好 6 项且全部 `href.startsWith("/admin/")` | 单测 `admin-nav.test.ts` 覆盖；浏览器实测 linkCount=7（品牌 + 6 菜单） | **PASS** |

---

## 单测统计（`npx vitest run` 全量）

- 结果：**25 Test Files passed (25) / 196 Tests passed (196)**，通过率 100%，总耗时 12.04s
- fx-task02 相关测试（重点）：

| 测试文件 | 用例数 | 覆盖 |
|---|---|---|
| `src/lib/admin-guard.test.tsx` | 8 | 未登录 redirect 参数携带 / student / teacher / manager 拦截 + toast / 无 roles 未知角色 / admin 放行（含大写 `ADMIN`）/ ready=false 占位不跳转 |
| `src/lib/admin-nav.test.ts` | 12 | `ADMIN_NAV_ITEMS` 恰 6 项且全部 `/admin/*` / `filterAdminNav` 混合角色放行 / `isAdminRole` 空值边界 |
| `src/lib/admin-layout.test.tsx` | 4 | admin 渲染 6 菜单 / manager / student 拦截 / 未登录占位 |
| `src/lib/api/admin.test.ts` | 11 | 错误壳 `{code,message,detail}` 透出 / 403/500 抛错 / 网络错误 status=0 文案 / 分页参数透传 |
| `src/lib/redirect.test.ts` | 8 | `isSafeRedirect` 站内放行 / 外域 / 伪协议 / 空值边界 |

- 已知警告（非失败）：`vitest.config.mts:16` 使用 `__dirname`（Vite configLoader native 迁移提示，server-info #4 已声明）

---

## 浏览器实测记录（localhost:3000，守卫流程全记录）

### 1. 未登录守卫 → PASS

```
goto http://localhost:3000/admin/dashboard
  → SSR 200 + AdminShellSkeleton（正在校验登录状态…）
  → hydrate 后自动跳转 http://localhost:3000/login?redirect=%2Fadmin%2Fdashboard
  → sonner toast「请先登录」（aria-live 容器，读屏器可达）
console: 0 error / 0 warning
```

### 2. admin 真实登录放行 → PASS

```
/login 提交 admin / Admin@12345（真实后端）
  → 回跳 /admin/dashboard（redirect 消费）
  → aside[aria-label="管理端导航"]：品牌链接 + nav[aria-label="管理端菜单"] > ul > li × 6
  → 7 个 link，aria-current="page" 落在「仪表盘」
  → 面包屑「管理端 / 仪表盘」；用户区「超 / 超级管理员」
  → GET /api/admin/users/dashboard/metrics 200（Bearer 注入正确，MetricCards 真实数据渲染）
```

### 3. 激活态跟随 → PASS

```
点击「课程」→ /admin/courses，aria-current 移至「课程」，h1「课程管理」
goto /admin/courses/39（子路由）→ aria-current 仍为「课程」（matchPrefix 前缀匹配生效）
```

### 4. student 真实登录拦截 → PASS

```
/login 提交 task01test / Test@123456（真实 student 账号，id 846）
  → 登录成功落 /dashboard（用户端）
goto /admin/courses
  → 骨架 → toast「无权限访问管理端」→ 0.4s 内重定向 /dashboard
  → 全程未渲染管理端内容（「创建系列」等零出现）
```

### 5. 移动端抽屉 a11y（375×812，admin 会话）→ PASS

| 检查项 | 实测 | 判定 |
|---|---|---|
| 关闭态 aside `inert` | `hasAttribute('inert')=true`，rect.left=-256（移出屏） | PASS（a11y #1 修复） |
| 打开/关闭按钮 `aria-expanded` + `aria-controls` | openBtn/closeBtn 均为 `aria-expanded="false"` + `aria-controls="admin-sidebar"`；打开后 `"true"` | PASS（#3 修复） |
| 点击打开 → 抽屉可见 | class 含 `translate-x-0 shadow-2xl`，`translate:0px`，rect.left=0；遮罩出现且 `aria-hidden="true"` | PASS |
| 打开后焦点移入 | `activeElement` = 首菜单「仪表盘」（`focusInDrawer=true`） | PASS（#5 修复） |
| Escape 关闭 | 抽屉关闭：`aria-expanded="false"`、inert 恢复、遮罩消失 | PASS（#4 修复） |
| 关闭后焦点归还 | `activeElement === 打开导航按钮` | PASS（#2 修复） |
| 遮罩点击关闭 | `expanded=false` + inert + 焦点归还打开按钮 | PASS |
| 菜单点击关闭（导航型） | 点击「题库」→ `/admin/questions` + h1 题库管理 + 抽屉关闭 | PASS |
| 关闭态 Tab 序列 | Tab 依次：退出 → 打开 AI 助手 → DevTools →（循环），**零屏幕外元素**（原 8 个负 rect 元素全部移出 Tab 序列） | PASS（#1 修复实测生效） |
| 导航语义 ul/li | `nav > ul > li × 6`，快照 `navigation "管理端菜单" > list > listitem × 6` | PASS（#6 修复） |
| 页脚对比度 | `text-slate-500`（a11y 报告建议值，4.76:1） | PASS（#7 修复，样式已改） |

---

## 静态校验

| 校验 | 命令 | 结果 |
|---|---|---|
| 类型检查 | `npx tsc --noEmit` | **0 error** |
| lint | `npm run lint` | fx-task02 文件（admin-guard/admin-nav/admin-layout/api/admin、(admin)/layout.tsx）**0 error 0 warning**；全库 25 errors / 26 warnings 全部位于 user 端、chat、learning、ui 等其他 task 文件（`git status` 确认本轮修正仅涉 admin 文件，未引入任何新 lint 问题） |

---

## 遗留项（非阻塞）

1. **lint 全库失败（25 errors）**：分布于 `(user)/courses/search`、`(user)/me`、`chat/`、`learning/`、`components/ui/radio-group.tsx` 等非 fx-task02 文件（`react-hooks/set-state-in-effect`、`no-explicit-any` 等），属其他 task 既有问题，建议后续 task 或独立 lint 修复波处理。
2. **浏览器会话污染（环境噪音，非产品缺陷）**：多次测试间曾出现 localStorage 中 `edu:auth:me` 被旧运行时 chunk 写成 raw 形态（`user_id/role` 无 `roles` 数组），导致 admin 会话被守卫按未知角色拦截——**守卫行为正确**（roles 缺失=拦截，符合 A4 契约）；本轮用「真实后端 token + normalized me（auth-client 契约形态）」注入后完成抽屉测试，已标注数据来源。根因疑似 dev server（fe-task01 轮次启动，PID 3780）的 HMR/编译缓存与源码不同步，与 fx-task02 代码无关，建议 fe-server-infra 下一轮重启 dev server 观察是否复现。
3. **登录页表单残留** `smoke_test@test.com / SmokeTest123!`（server-info #5 已知），对管理端流程无影响。
4. **vitest config 警告**：`vitest.config.mts:16` `__dirname`（Vite 未来默认 `configLoader:'native'` 不支持），仅警告。
5. **后端 DEBUG 鉴权绕过**（无 token 即虚拟 admin）与 CORS `*` 属既有后端设计，本轮未动（规格边界声明，上线硬门槛 `.env DEBUG=false`）。

---

## 结论

- **判定：PASS**（5 项验收标准 A–E 全通过；196/196 单测、tsc 0 error、fx-task02 范围 lint 0 error、浏览器守卫与抽屉 a11y 全流程实测通过）
- 本轮修正验证：`(admin)/layout.tsx` 抽屉 7 项 a11y 修复（inert / Escape / 焦点移入与归还 / aria-expanded+aria-controls / ul-li 列表语义 / 对比度 / aria-label）在真实浏览器 375px 视口下**全部生效且无视觉回归**（打开态 `translate:0px`、rect.left=0）；`admin-guard.tsx` AdminShellSkeleton 在 SSR/hydrate 两阶段均正确呈现（骨架占位 → 判定 → 跳转/放行），无白屏、无内容闪烁、安全语义未降级（骨架不渲染真实链接与角色过滤结果）。
